"""Offline string-candidate export from a PyInstaller Python 3.14 launcher.

The original executable is never started or modified. This module extracts
*actual* str constants from the frozen UI modules; a literal is not proof of
an on-screen label, so its provenance is stored in a separate review report.
"""
from __future__ import annotations

import argparse
import json
import marshal
from pathlib import Path
import re
import tempfile
import types
import os
import zlib

from cn_generator_core import (
    MAX_DICTIONARY_BYTES, load_translations, read_carchive,
    require_runtime, sha256,
)

MAX_PYZ_BYTES = 128 * 1024 * 1024
MAX_MODULE_BYTES = 16 * 1024 * 1024
MAX_LABELS = 10000
UI_PREFIX = "ichalaunch.ui."
EXTRA_UI_MODULES = frozenset(("ichalaunch.app",))

# Deliberately conservative: never normalize text that is emitted as a key.
# Avoid exporting obvious implementation artifacts; uncertain strings that
# survive are still only candidates, never automatically safe patch targets.
RESOURCE = re.compile(r"(?i)\.(png|jpg|jpeg|svg|ico|gif|webp|dll|exe|py|pyc|json|ini|toml|xml|txt|zip|7z|mpq|ttf|woff2?)$")
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
HEXLIKE = re.compile(r"^[0-9a-fA-F]{24,}$")
PLACEHOLDER = re.compile(r"^\{[^{}]+\}$")


def likely_ui_literal(value: str) -> bool:
    if not 2 <= len(value) <= 512 or value != value.strip():
        return False
    if any(ord(c) < 32 for c in value) or "\x00" in value:
        return False
    if not re.search("[A-Za-z]", value):
        return False
    if value.startswith(("/", "\\\\", "./", "../", "http:", "https:")):
        return False
    if "://" in value or "\\\\" in value or "/" in value and " " not in value:
        return False
    if RESOURCE.search(value) or HEXLIKE.fullmatch(value) or PLACEHOLDER.fullmatch(value):
        return False
    if value.startswith(("--", "<", "{", "[")) or value.endswith(("=", ":=")):
        return False
    if IDENTIFIER.fullmatch(value):
        return False
    if value.count("{") != value.count("}") or value.count("(") != value.count(")"):
        return False
    return True


def _walk_codes(code: types.CodeType, path: str):
    yield path, code
    for constant in code.co_consts:
        if isinstance(constant, types.CodeType):
            yield from _walk_codes(constant, path + "." + constant.co_name)


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, (tuple, list, frozenset)):
        for item in value:
            yield from _strings(item)


def read_ui_constants(source: Path) -> tuple[dict[str, set[str]], dict]:
    require_runtime()
    blob = source.read_bytes()
    start, cookie, entries = read_carchive(blob)
    archives = [e for e in entries if e["name"] == "PYZ.pyz" and e["kind"] == b"z"]
    if len(archives) != 1:
        raise ValueError("Expected a single PYZ.pyz in the supported CArchive")
    archive = archives[0]["blob"]
    if archives[0]["compressed"]:
        archive = zlib.decompress(archive)
    if len(archive) > MAX_PYZ_BYTES or archive[:4] != b"PYZ\x00":
        raise ValueError("Invalid or oversized PYZ archive")
    toc_offset = int.from_bytes(archive[8:12], "big")
    if toc_offset < 12 or toc_offset >= len(archive):
        raise ValueError("Invalid PYZ TOC bounds")
    toc = marshal.loads(archive[toc_offset:], allow_code=False)
    if not isinstance(toc, (dict, list)):
        raise ValueError("Unsupported PYZ TOC")
    rows = toc.items() if isinstance(toc, dict) else toc
    candidates = {}
    checked = 0
    errors = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            raise ValueError("Invalid PYZ TOC row")
        name, position = row
        if not isinstance(name, str) or not (name.startswith(UI_PREFIX) or name in EXTRA_UI_MODULES):
            continue
        checked += 1
        if not isinstance(position, (list, tuple)) or len(position) != 3:
            errors.append(name + ": invalid module position")
            continue
        _type, offset, length = position
        if (not isinstance(offset, int) or not isinstance(length, int)
                or length <= 0 or length > MAX_MODULE_BYTES
                or offset < 12 or offset + length > toc_offset):
            errors.append(name + ": invalid module bounds")
            continue
        try:
            raw = zlib.decompress(archive[offset:offset + length])
            if len(raw) > MAX_MODULE_BYTES:
                raise ValueError("module expanded beyond limit")
            code = marshal.loads(raw, allow_code=True)
            if not isinstance(code, types.CodeType):
                raise ValueError("module entry is not CodeType")
            for qualname, subcode in _walk_codes(code, name):
                for const in subcode.co_consts:
                    if isinstance(const, types.CodeType):
                        continue
                    for text in _strings(const):
                        if likely_ui_literal(text):
                            candidates.setdefault(text, set()).add(qualname)
        except (ValueError, TypeError, EOFError, zlib.error) as exc:
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    if errors:
        raise ValueError(f"{len(errors)} UI modules failed to decode (first: {errors[0]})")
    if not candidates or len(candidates) > MAX_LABELS:
        raise ValueError(f"Unreasonable UI candidate count: {len(candidates)}")
    return candidates, {
        "source_sha256": sha256(blob),
        "source_size": len(blob),
        "ui_modules_examined": checked,
        "ui_modules_failed": 0,
        "raw_literal_candidates": len(candidates),
        "target_executed": False,
        "note": "Raw Python literals from UI modules, NOT guaranteed visible or safe to replace.",
    }


def _read_previous(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    # Untranslated values are allowed in the export and must remain intact.
    return load_translations(path)


def export_strings(source: Path, output: Path, *, merge: bool = True) -> dict:
    if source.resolve() == output.resolve():
        raise ValueError("Cannot overwrite the original executable")
    literals, stats = read_ui_constants(source)
    old = _read_previous(output) if merge else {}
    if not merge and output.exists():
        raise FileExistsError(f"Output exists: {output}")
    # Keep the original source verbatim, including case, punctuation and spaces.
    result = dict(old)
    new_items = 0
    for phrase in sorted(literals, key=lambda s: (s.casefold(), s)):
        if phrase not in result:
            result[phrase] = ""
            new_items += 1
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if len(serialized.encode("utf-8")) > MAX_DICTIONARY_BYTES:
        raise ValueError("Export would exceed generator dictionary size limit")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".cn-export-", dir=output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(serialized)
            f.flush()
            os.fsync(f.fileno())
        # After successful extraction and serialization, replace the
        # destination atomically; failed scans preserve the old dictionary.
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    stats.update({
        "output": str(output),
        "kept_existing": len(old),
        "new_empty_entries": new_items,
        "total_entries": len(result),
        "nonempty_translations": sum(bool(x) for x in result.values()),
        "coverage": "static UI literals only; does not imply working translation hooks",
    })
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exe", type=Path)
    parser.add_argument("--out", type=Path, default=Path("zh_CN.json"))
    parser.add_argument("--no-merge", action="store_true", help="Reject an existing output file")
    args = parser.parse_args()
    print(json.dumps(export_strings(args.exe, args.out, merge=not args.no_merge),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
