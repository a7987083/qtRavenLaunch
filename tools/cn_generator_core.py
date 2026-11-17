"""Offline PyInstaller launcher localization generator (CPython 3.14).

Preserve the original bootloader, bundled dependencies and PYZ. Replace only
its top-level run script with a tiny import hook + original code object.
Never launches the target. No vendor-version SHA allowlist.
"""
from __future__ import annotations
import hashlib
import json
import marshal
import os
from pathlib import Path
import struct
import sys
import tempfile
import types
import zlib

MAGIC = b"MEI\x0c\x0b\x0a\x0b\x0e"
COOKIE = struct.Struct("!8sIIII64s")
ENTRY = struct.Struct("!IIIIBc")
MAX_SIZE = 512 * 1024 * 1024
MAX_SCRIPT = 8 * 1024 * 1024
MAX_DICTIONARY_BYTES = 256 * 1024

# Patch only the display value inside Python custom paint routines; the
# underlying QWidget.text() remains English for game state and routing.
TRANSLATIONS = {
    "HOME": "主页",
    "ADDONS": "插件",
    "CLIENT": "客户端",
    "SETTINGS": "设置",
    "PLAY": "开始游戏",
    "INSTALL": "安装",
    "UPDATE": "更新",
}

# The code runs *inside the newly generated EXE*, not in the generator.
# Hook PyInstaller's existing import machinery without importing Qt before
# the original run.py has initialized its environment. Fail open if a widget
# API changes: original English UI should still work.
BOOTSTRAP_SOURCE = r'''
import sys as _cn_sys
import importlib.util as _cn_util

# Check official-launcher self-updates against the *source* EXE digest.
# Hashing the localized output would always look like an official hotfix.
_CN_SOURCE_EXE_SHA256 = "__RAVEN_SOURCE_EXE_SHA256__"

_CN_TRANSLATIONS = __RAVEN_CN_DICTIONARY__


def _cn_patch_widget(cls, draw_method, translations):
    if getattr(cls, "_raven_cn_patched", False):
        return
    draw = getattr(cls, draw_method)
    text = getattr(cls, "text")

    def _cn_text(self):
        value = text(self)
        if getattr(self, "_raven_cn_paint_depth", 0):
            return translations.get(value, value)
        return value

    def _cn_draw(self, *args, **kwargs):
        depth = getattr(self, "_raven_cn_paint_depth", 0)
        self._raven_cn_paint_depth = depth + 1
        try:
            return draw(self, *args, **kwargs)
        finally:
            self._raven_cn_paint_depth = depth

    cls.text = _cn_text
    setattr(cls, draw_method, _cn_draw)
    cls._raven_cn_patched = True


def _cn_patch_loaded(name, module):
    try:
        if name == "ichalaunch.ui.main_window":
            cls = getattr(module, "NavTabButton", None)
            if cls is not None:
                _cn_patch_widget(cls, "paintEvent", _CN_TRANSLATIONS)
        elif name == "ichalaunch.core.self_update":
            original_sha = getattr(module, "_running_launcher_sha256", None)
            if not callable(original_sha):
                raise RuntimeError("self_update._running_launcher_sha256 unavailable")
            # Do NOT turn off update checks: a newer upstream version (or
            # a true upstream same-version hotfix) must still be offered.
            # For comparing a release pin, use the original vendor EXE hash,
            # because this generated EXE necessarily has a different hash.
            def _cn_source_launcher_sha256(*args, **kwargs):
                return _CN_SOURCE_EXE_SHA256
            module._running_launcher_sha256 = _cn_source_launcher_sha256
        elif name == "ichalaunch.ui.widgets.launch_button":
            cls = getattr(module, "LaunchButton", None)
            if cls is not None:
                _cn_patch_widget(cls, "_paint_label", _CN_TRANSLATIONS)
    except Exception as exc:
        # A localization issue must not prevent users from launching the game.
        print("RavenLaunch CN: widget adapter unavailable:", exc, file=_cn_sys.stderr)


class _CnLoader:
    def __init__(self, loader, fullname):
        self._loader = loader
        self._fullname = fullname

    def create_module(self, spec):
        create = getattr(self._loader, "create_module", None)
        return create(spec) if create else None

    def exec_module(self, module):
        self._loader.exec_module(module)
        _cn_patch_loaded(self._fullname, module)

    def __getattr__(self, name):
        return getattr(self._loader, name)


class _CnFinder:
    _targets = frozenset(("ichalaunch.ui.main_window", "ichalaunch.ui.widgets.launch_button", "ichalaunch.core.self_update"))

    def find_spec(self, fullname, path=None, target=None):
        if fullname not in self._targets:
            return None
        # Delegate to original PyInstaller importer; avoid recursive find_spec.
        index = _cn_sys.meta_path.index(self)
        _cn_sys.meta_path.pop(index)
        try:
            spec = _cn_util.find_spec(fullname)
        finally:
            _cn_sys.meta_path.insert(index, self)
        if spec is not None and spec.loader is not None:
            spec.loader = _CnLoader(spec.loader, fullname)
        return spec


_cn_sys.meta_path.insert(0, _CnFinder())
exec(_RAVEN_ORIGINAL_RUN_CODE_)
'''


def default_dictionary_path() -> Path:
    # PyInstaller --onefile extracts bundled data to _MEIPASS.
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return root / "translations" / "zh_CN.json"


def _unique_json_object(pairs):
    value = {}
    for key, translation in pairs:
        if key in value:
            raise ValueError(f"Duplicate translation key: {key!r}")
        value[key] = translation
    return value


def load_translations(path: Path | None = None) -> dict[str, str]:
    """Flat UTF-8 JSON: one English phrase mapped to one translated phrase."""
    dictionary = path if path is not None else default_dictionary_path()
    if dictionary.stat().st_size > MAX_DICTIONARY_BYTES:
        raise ValueError("Translation dictionary too large")
    value = json.loads(dictionary.read_text(encoding="utf-8-sig"),
                       object_pairs_hook=_unique_json_object)
    if not isinstance(value, dict):
        raise ValueError("Translation dictionary must be a flat JSON object")
    checked = {}
    for source, translated in value.items():
        if not isinstance(source, str) or not source.strip() or len(source) > 512:
            raise ValueError("Invalid English source label")
        if not isinstance(translated, str) or not translated.strip() or len(translated) > 512:
            raise ValueError(f"Invalid translation for {source!r}")
        checked[source] = translated
    return checked


def require_runtime():
    if sys.version_info[:2] != (3, 14):
        raise RuntimeError(f"Generator needs CPython 3.14; got {sys.version.split()[0]}")


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def read_carchive(data):
    if len(data) > MAX_SIZE or data[:2] != b"MZ":
        raise ValueError("Not a supported Windows PE executable or too large")
    index = data.rfind(MAGIC)
    if index < 0 or index + COOKIE.size != len(data):
        raise ValueError("PyInstaller 88-byte cookie missing at EOF")
    cookie = COOKIE.unpack_from(data, index)
    _, size, toc_off, toc_len, pyver, python_dll = cookie
    if pyver != 314:
        raise ValueError(f"This generator engine requires Python 3.14 frozen code (found {pyver}); no vendor-version whitelist")
    start = index + COOKIE.size - size
    a, b = start + toc_off, start + toc_off + toc_len
    if start < 0 or a < start or b != index:
        raise ValueError("Invalid PyInstaller archive layout")
    entries = []
    cursor = a
    while cursor < b:
        if cursor + ENTRY.size > b:
            raise ValueError("Truncated TOC")
        size_e, offset, compressed_size, raw_size, compressed, kind = ENTRY.unpack_from(data, cursor)
        if size_e <= ENTRY.size or cursor + size_e > b or offset + compressed_size > toc_off:
            raise ValueError("Invalid PyInstaller entry bounds")
        name = data[cursor + ENTRY.size:cursor + size_e].rstrip(b"\0").decode("utf-8", "strict")
        blob = data[start + offset:start + offset + compressed_size]
        entries.append({"name": name, "namebytes": data[cursor + ENTRY.size:cursor + size_e],
                        "kind": kind, "compressed": compressed, "raw_size": raw_size,
                        "blob": blob})
        cursor += size_e
    if not entries or cursor != b:
        raise ValueError("No archive entries")
    return start, cookie, entries


def decode_script(entry):
    if entry["raw_size"] > MAX_SCRIPT:
        raise ValueError("Entry script too large")
    blob = entry["blob"]
    raw = zlib.decompress(blob) if entry["compressed"] else blob
    if len(raw) != entry["raw_size"]:
        raise ValueError("Script decompression size mismatch")
    code = marshal.loads(raw, allow_code=True)
    if not isinstance(code, types.CodeType):
        raise ValueError("Entry is not CPython code")
    return code


def make_bootstrap(original, source_sha256, translations=None):
    # Store the unchanged original run CodeType as an embedded constant.
    # This avoids redistributing its bytecode as a separate file or importing it.
    if len(source_sha256) != 64 or any(c not in "0123456789abcdef" for c in source_sha256):
        raise ValueError("Invalid original-source digest")
    if translations is None:
        translations = load_translations()
    source = BOOTSTRAP_SOURCE.replace("__RAVEN_SOURCE_EXE_SHA256__", source_sha256)
    marker = "__RAVEN_CN_DICTIONARY__"
    if source.count(marker) != 1:
        raise ValueError("Missing bootstrap dictionary marker")
    source = source.replace(marker, repr(translations))
    source = source.replace("exec(_RAVEN_ORIGINAL_RUN_CODE_)",
                                      "exec('__RAVEN_ORIGINAL_RUN_CODE__')")
    wrapped = compile(source, "<raven-cn-bootstrap>", "exec")
    constants = list(wrapped.co_consts)
    if constants.count("__RAVEN_ORIGINAL_RUN_CODE__") != 1:
        raise ValueError("Code bootstrap marker not unique")
    constants[constants.index("__RAVEN_ORIGINAL_RUN_CODE__")] = original
    wrapped = wrapped.replace(co_consts=tuple(constants))
    return marshal.dumps(wrapped)


def assemble(prefix, cookie, entries):
    parts, toc_parts, offset = [], [], 0
    for item in entries:
        blob = item["blob"]
        size = ENTRY.size + len(item["namebytes"])
        toc_parts.append(ENTRY.pack(size, offset, len(blob), item["raw_size"],
                                    item["compressed"], item["kind"]) + item["namebytes"])
        parts.append(blob)
        offset += len(blob)
    payload = b"".join(parts)
    toc = b"".join(toc_parts)
    _, _, _, _, version, dll = cookie
    footer = COOKIE.pack(MAGIC, len(payload) + len(toc) + COOKIE.size,
                         len(payload), len(toc), version, dll)
    return prefix + payload + toc + footer


def generate(source: Path, destination: Path, dictionary_path: Path | None = None):
    require_runtime()
    if source.resolve() == destination.resolve():
        raise ValueError("Output must not overwrite the official EXE")
    if destination.exists():
        raise FileExistsError(f"Output already exists: {destination}")
    original = source.read_bytes()
    start, cookie, entries = read_carchive(original)
    targets = [entry for entry in entries if entry["name"] == "run" and entry["kind"] == b"s"]
    if len(targets) != 1:
        raise ValueError("Target has no unique supported 'run' launcher entry")
    script = targets[0]
    script_code = decode_script(script)
    required = {"ichalaunch", "main"}
    if not required.issubset(script_code.co_names):
        raise ValueError("Launcher does not have the expected IchaLaunch Python entry")
    patched = make_bootstrap(script_code, sha256(original), load_translations(dictionary_path))
    script["blob"] = zlib.compress(patched, level=9) if script["compressed"] else patched
    script["raw_size"] = len(patched)
    result = assemble(original[:start], cookie, entries)
    # Validate all archive entries round-trip and actual embedded code object.
    _, _, check_entries = read_carchive(result)
    new_script = next(e for e in check_entries if e["name"] == "run" and e["kind"] == b"s")
    loaded = decode_script(new_script)
    if loaded.co_filename != "<raven-cn-bootstrap>":
        raise AssertionError("Patched entry script missing")
    changes = [name for name in ("run",)]
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=destination.parent, prefix=".raven-cn-")
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(result)
            output.flush()
            os.fsync(output.fileno())
        if destination.exists():
            raise FileExistsError(destination)
        os.replace(tmp, destination)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return {"source_sha256": sha256(original), "output_sha256": sha256(result),
            "source_bytes": len(original), "output_bytes": len(result),
            "carchive_entries": len(entries), "modified_entries": changes,
            "original_unchanged": source.read_bytes() == original,
            "static_verified": True, "windows_gui_tested": False,
            "source_digest_used_for_updater_comparison": True}


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("--out", type=Path, default=Path("IchaLaunch-CN.exe"))
    p.add_argument("--dictionary", type=Path, help="Optional custom zh_CN.json")
    args = p.parse_args()
    print(json.dumps(generate(args.source, args.out, args.dictionary), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
