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
MAX_DICTIONARY_BYTES = 2 * 1024 * 1024

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

# Only these static SETTINGS widget labels are eligible for in-widget translation.
# This is deliberately NOT a global setText hook: state_lbl and other status
# labels can be read back as business-state values by the original app.
_CN_SETTINGS_UI_KEYS = frozenset((
    "Settings",
    "Game client",
    "Game location",
    "AddOns folder",
    "Existing install",
    "Install…",
    "Browse…",
    "Verify",
    "Reset Client Link",
    "Save",
    "1.12 Vanilla  -  the original 2006 visual experience",
    "1.14 Classic  -  classic gameplay with today's graphics",
    "HD textures for the 1.14 client  -  sharper art, a large extra download",
    "PLAY starts the selected client.",
    "Avoid Program Files / Desktop / Downloads / Documents.",
    "Used to reinstall the client. Clears the saved WoW folder so PLAY becomes INSTALL and you can choose a new location. Does not delete files on disk.",
    "Reset to default",
    "Use {game folder}\\Interface\\AddOns",
    "Updates",
    "Automatically Check For Updates On Startup",
    "Privacy",
    "GitHub API",
    "Personal access token (optional)",
    "Saved automatically when you leave the field or click Save",
    "Maintenance",
    "Clear Cache",
    "Redo Setup",
    "Check Game Permissions",
    "Defaults to Interface\\AddOns under the game folder when you set or change the game path. Override only if your addons live elsewhere.",
    "Download and install the 1.14 client (about 11 GB) into a folder you choose.",
    "Compare game files to the published RavenCraft client. You can check hashes and restore any that do not match.",
    "Unlink the saved WoW folder so you can INSTALL to a new location. Does not delete files on disk.",
    "Prompt to fix addon folder / .toc name mismatches",
    "Enforce Addon Dependencies",
    "Prompt when SuperWoW and Nampower settings disagree",
    "Prompt to switch to recommended addon forks",
    "Allow Vanilla Tweaks on unrecognized clients (advanced)",
    "Send crash and error reports to the maintainer",
    "Reset launcher settings, cached scan data, and saved preferences. Does not delete game or addon files on disk.",
    "Created by Ichabaddie with significant contributions from Valheru and Mynie. Icon by Subtilizer.",
))


def _cn_patch_widget(cls, draw_method, translations, reader_name="text"):
    if getattr(cls, "_raven_cn_patched", False):
        return
    draw = getattr(cls, draw_method)
    text = getattr(cls, reader_name)

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

    setattr(cls, reader_name, _cn_text)
    setattr(cls, draw_method, _cn_draw)
    cls._raven_cn_patched = True


def _cn_patch_glue_combo(module):
    """Paint-only localized combo text; keep Qt model DisplayRole untouched."""
    cls = getattr(module, "GlueComboBox", None)
    if cls is None or getattr(cls, "_raven_cn_combo_patched", False):
        return
    from PySide6.QtWidgets import QStyledItemDelegate

    # The original combo draws its closed-state caption with
    # self.currentText() inside paintEvent. The old result is still returned
    # everywhere else (including business filter/routing code).
    _cn_patch_widget(cls, "paintEvent", _CN_TRANSLATIONS,
                     reader_name="currentText")
    old_init = cls.__init__

    class _CnComboDisplayDelegate(QStyledItemDelegate):
        # Original popup model/index is never changed. Qt calls
        # initStyleOption() during delegate painting and supplies the actual
        # DisplayRole label. Override only the presentation string.
        def initStyleOption(self, option, index):
            super().initStyleOption(option, index)
            original = option.text
            translated = _CN_TRANSLATIONS.get(original)
            if translated and translated != original:
                option.text = translated
                _cn_log("combo-popup-applied", "addons", original)

    def init_translated(self, *args, **kwargs):
        old_init(self, *args, **kwargs)
        view = self.view()
        # An upstream non-standard delegate may provide additional rendering
        # semantics; do not silently override it.
        previous = view.itemDelegate()
        if previous is not None and type(previous) is not QStyledItemDelegate:
            _cn_log("combo-delegate-skipped", "addons", type(previous).__name__)
            return
        delegate = _CnComboDisplayDelegate(view)
        self._raven_cn_delegate = delegate
        view.setItemDelegate(delegate)
        _cn_log("combo-ready", "addons")

    cls.__init__ = init_translated
    cls._raven_cn_combo_patched = True


def _cn_patch_settings_page(module):
    page_cls = getattr(module, "SettingsPage", None)
    if page_cls is None or getattr(page_cls, "_raven_cn_settings_patched", False):
        return
    # Only inspect Qt widgets owned by SettingsPage; do not modify MainWindow
    # status labels, addons pages, navigation routing or text input contents.
    from PySide6.QtWidgets import QWidget, QLabel, QAbstractButton
    # Several SETTINGS captions/buttons are custom-painted QWidget children,
    # not QLabel / QAbstractButton. They still expose Qt-compatible text()
    # and setText() APIs. Reject editable inputs even if their text collides.
    safe_custom_types = frozenset((
        "GradientLabel", "GluePanelButton", "ThemeRadioButton", "ThemeCheckBox"
    ))

    init = page_cls.__init__
    eligible_settings = set(_CN_SETTINGS_UI_KEYS) | _cn_static_literals(init.__code__)

    # The Discord/privacy captions are NOT constants in SettingsPage.__init__.
    # They are defined at MODULE scope and passed through named globals.
    # Read precisely those UI caption globals rather than admitting arbitrary
    # module strings (which also include configuration/internal state keys).
    for name in ("_DISCORD_PARENT_LABEL", "_DISCORD_CHILD_LABEL"):
        caption = getattr(module, name, None)
        if isinstance(caption, str):
            eligible_settings.add(caption)
    fields = getattr(module, "BROADCAST_FIELD_LABELS", None)
    if isinstance(fields, dict):
        eligible_settings.update(
            value for value in fields.values() if isinstance(value, str))

    def _cn_translate_static(self):
        if getattr(self, "_raven_cn_scanning", False):
            return
        self._raven_cn_scanning = True
        try:
            for widget in self.findChildren(QWidget):
                if not (isinstance(widget, (QLabel, QAbstractButton))
                        or type(widget).__name__ in safe_custom_types):
                    continue
                identifier = getattr(widget, "objectName", lambda: "")()
                if isinstance(identifier, str) and any(
                        x in identifier.casefold()
                        for x in ("status", "progress", "loading", "path", "state")):
                    continue
                try:
                    reader = getattr(widget, "text", None)
                    writer = getattr(widget, "setText", None)
                    if not callable(reader) or not callable(writer):
                        _cn_log("unsupported-control", "settings", type(widget).__name__)
                        continue
                    original = reader()
                    if (isinstance(original, str) and original in eligible_settings
                            and original not in _CN_NEVER_REPLACE):
                        new = _CN_TRANSLATIONS.get(original)
                        if new and new != original:
                            writer(new)
                            _cn_log("applied", "settings", original)
                    get_tip = getattr(widget, "toolTip", None)
                    set_tip = getattr(widget, "setToolTip", None)
                    if callable(get_tip) and callable(set_tip):
                        tip = get_tip()
                        if isinstance(tip, str) and tip in eligible_settings:
                            new = _CN_TRANSLATIONS.get(tip)
                            if new and new != tip:
                                set_tip(new)
                                _cn_log("tooltip-applied", "settings", tip)
                except RuntimeError:
                    continue
        except Exception as exc:
            _cn_log("adapter-error", "settings", type(exc).__name__)
        finally:
            self._raven_cn_scanning = False

    def _cn_settings_init(self, *args, **kwargs):
        init(self, *args, **kwargs)
        _cn_translate_static(self)

    page_cls.__init__ = _cn_settings_init

    # Refresh operations recreate/reset some labels. Translate only known
    # static literal values immediately after the original method finishes.
    for method_name in ("showEvent", "refresh", "_refresh_game_client",
                        "_sync_discord_character_row"):
        old_method = getattr(page_cls, method_name, None)
        if old_method is None:
            continue

        def _cn_after_refresh(self, *args, _original=old_method, **kwargs):
            result = _original(self, *args, **kwargs)
            _cn_translate_static(self)
            return result

        setattr(page_cls, method_name, _cn_after_refresh)
    page_cls._raven_cn_settings_patched = True
    _cn_log("adapter-ready", "settings")



# Runtime diagnostics deliberately contain only translation keys and adapter
# metadata, never user input, account data, game paths or arbitrary label text.
_CN_DIAG_SEEN = set()


def _cn_log(kind, page, key=""):
    tag = (kind, page, key)
    if tag in _CN_DIAG_SEEN:
        return
    _CN_DIAG_SEEN.add(tag)
    try:
        import json as _cn_json
        import os as _cn_os
        from pathlib import Path as _cn_Path
        folder = _cn_Path(_cn_os.environ.get("LOCALAPPDATA")
                          or _cn_os.environ.get("TEMP") or ".") / "RavenLaunch-CN"
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / "translation-coverage.jsonl").open("a", encoding="utf-8") as f:
            f.write(_cn_json.dumps({"event": kind, "page": page, "source": key},
                                   ensure_ascii=False) + "\n")
    except OSError:
        pass


_CN_PAGE_CLASSES = {
    "ichalaunch.ui.pages.home": "HomePage",
    "ichalaunch.ui.pages.client": "ClientPage",
    "ichalaunch.ui.pages.addons": "AddonsPage",
    "ichalaunch.ui.pages.addons_114": "Raven114AddonsPanel",
}
_CN_SAFE_CONTROL_NAMES = frozenset((
    "GradientLabel", "GluePanelButton", "ThemeButton",
    "ThemeRadioButton", "ThemeCheckBox", "TitleLockup"
))
_CN_NEVER_REPLACE = frozenset((
    "HOME", "ADDONS", "CLIENT", "SETTINGS", "PLAY", "UPDATE", "INSTALL",
    "READY", "CHECKING", "INSTALLING", "DOWNLOADING"
))


def _cn_static_literals(code):
    """Collect static strings, including nested UI construction closures.

    Do not execute code objects. Only use these strings as candidates for
    page-scoped display controls, never for modifying business-state values.
    """
    import types as _cn_types
    result = set()
    def visit(value):
        if isinstance(value, str):
            result.add(value)
        elif isinstance(value, _cn_types.CodeType):
            for item in value.co_consts:
                visit(item)
        elif isinstance(value, (tuple, frozenset)):
            for item in value:
                visit(item)
    visit(code)
    return result


def _cn_client_ui_literals(cls):
    """Limit CLIENT's extra literals to UI construction and render methods."""
    result = set()
    candidates = ("_add_", "_build_", "_create_", "_refresh_", "refresh",
                  "_sync_", "_update_", "show")
    excluded = ("_sync_status_host", "set_check_status", "set_checking",
                "set_updates", "clear_pending_update", "_sync_game_lock_actions")
    for name, method in vars(cls).items():
        if name in excluded or not name.startswith(candidates):
            continue
        if hasattr(method, "__code__"):
            result.update(_cn_static_literals(method.__code__))
    return result


def _cn_patch_page(module_name, module):
    from PySide6.QtWidgets import QWidget, QLabel, QAbstractButton

    class_name = _CN_PAGE_CLASSES[module_name]
    page_cls = getattr(module, class_name, None)
    if page_cls is None:
        _cn_log("adapter-missing", module_name, class_name)
        return
    if getattr(page_cls, "_raven_cn_page_patched", False):
        return
    original_init = page_cls.__init__
    eligible = _cn_static_literals(original_init.__code__)
    # Only static strings appearing in the page's own UI constructor, not
    # arbitrary translated strings collected elsewhere in the PYZ archive.
    eligible_methods = {
        "ichalaunch.ui.pages.home": ("refresh", "_fill_whats_new"),
        "ichalaunch.ui.pages.client": (
            "_add_presets_page", "refresh_from_settings", "refresh_plan",
            "_refresh_patch9_banner"),
        "ichalaunch.ui.pages.addons_114": ("_build_rows",),
    }
    for name in eligible_methods.get(module_name, ()):
        method = getattr(page_cls, name, None)
        if hasattr(method, "__code__"):
            eligible.update(_cn_static_literals(method.__code__))
    if module_name == "ichalaunch.ui.pages.client":
        eligible.update(_cn_client_ui_literals(page_cls))
    page_id = module_name.rsplit(".", 1)[-1]

    def translate_visible(self):
        if getattr(self, "_raven_cn_scanning", False):
            return
        self._raven_cn_scanning = True
        try:
            for widget in self.findChildren(QWidget):
                if not (isinstance(widget, (QLabel, QAbstractButton))
                        or type(widget).__name__ in _CN_SAFE_CONTROL_NAMES):
                    continue
                identifier = getattr(widget, "objectName", lambda: "")()
                if isinstance(identifier, str) and any(
                        unsafe in identifier.casefold()
                        for unsafe in ("status", "progress", "loading", "path", "state")):
                    continue
                # CLIENT sidebar categories act as navigation values. Keep
                # the underlying Qt text untouched; GluePanelButton receives
                # its translation only during native paintEvent.
                if (module_name == "ichalaunch.ui.pages.client"
                        and type(widget).__name__ == "GluePanelButton"):
                    continue
                get_text = getattr(widget, "text", None)
                set_text = getattr(widget, "setText", None)
                if not callable(get_text) or not callable(set_text):
                    _cn_log("unsupported-control", page_id, type(widget).__name__)
                if callable(get_text) and callable(set_text):
                    original = get_text()
                    if (isinstance(original, str) and original in eligible
                            and original not in _CN_NEVER_REPLACE):
                        translated = _CN_TRANSLATIONS.get(original)
                        if translated and translated != original:
                            set_text(translated)
                            _cn_log("applied", page_id, original)
                # Tooltips are presentation-only. Keep text() business state
                # untouched and translate only literal constructor strings.
                get_tip = getattr(widget, "toolTip", None)
                set_tip = getattr(widget, "setToolTip", None)
                if callable(get_tip) and callable(set_tip):
                    tip = get_tip()
                    if isinstance(tip, str) and tip in eligible:
                        translated = _CN_TRANSLATIONS.get(tip)
                        if translated and translated != tip:
                            set_tip(translated)
                            _cn_log("tooltip-applied", page_id, tip)
        except Exception as exc:
            _cn_log("adapter-error", page_id, type(exc).__name__)
        finally:
            self._raven_cn_scanning = False

    def init_translated(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        translate_visible(self)
    page_cls.__init__ = init_translated

    refresh_methods = {
        "ichalaunch.ui.pages.client": (
            "refresh_from_settings", "refresh_plan", "_refresh_patch9_banner"),
        "ichalaunch.ui.pages.addons_114": ("_build_rows", "refresh_status"),
    }
    methods = ("showEvent", "refresh") + refresh_methods.get(module_name, ())
    for method_name in methods:
        previous = getattr(page_cls, method_name, None)
        if not callable(previous):
            continue
        def refresh_translated(self, *args, _original=previous, **kwargs):
            result = _original(self, *args, **kwargs)
            translate_visible(self)
            return result
        setattr(page_cls, method_name, refresh_translated)
    page_cls._raven_cn_page_patched = True
    _cn_log("adapter-ready", page_id)

def _cn_patch_loaded(name, module):
    try:
        if name == "ichalaunch.ui.main_window":
            cls = getattr(module, "NavTabButton", None)
            if cls is not None:
                _cn_patch_widget(cls, "paintEvent", _CN_TRANSLATIONS)
        elif name == "ichalaunch.ui.widgets.glue_panel_button":
            cls = getattr(module, "GluePanelButton", None)
            if cls is not None:
                # Keep navigation state in English; only the custom QPainter
                # call sees the localized QLabel-like text.
                _cn_patch_widget(cls, "paintEvent", _CN_TRANSLATIONS)
                _cn_log("paint-adapter-ready", "client", "GluePanelButton")
        elif name == "ichalaunch.ui.widgets.glue_combo":
            _cn_patch_glue_combo(module)
        elif name == "ichalaunch.ui.pages.settings":
            _cn_patch_settings_page(module)
        elif name in _CN_PAGE_CLASSES:
            _cn_patch_page(name, module)
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
        _cn_log("adapter-error", name, type(exc).__name__)
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
    _targets = frozenset(("ichalaunch.ui.main_window", "ichalaunch.ui.widgets.launch_button", "ichalaunch.core.self_update", "ichalaunch.ui.pages.settings", "ichalaunch.ui.widgets.glue_combo", "ichalaunch.ui.widgets.glue_panel_button", *tuple(_CN_PAGE_CLASSES)))

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
_cn_log("session-start", "bootstrap", _CN_SOURCE_EXE_SHA256[:12])
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
    try:
        value = json.loads(dictionary.read_text(encoding="utf-8-sig"),
                           object_pairs_hook=_unique_json_object)
    except json.JSONDecodeError as exc:
        raw = dictionary.read_text(encoding="utf-8-sig")
        lines = raw.splitlines()
        bad_line = lines[exc.lineno - 1] if exc.lineno <= len(lines) else ""
        left = max(0, exc.colno - 46)
        right = min(len(bad_line), exc.colno + 34)
        snippet = bad_line[left:right]
        message = "\n".join((
            f"词库 JSON 格式错误：{dictionary.name}",
            f"第 {exc.lineno} 行，第 {exc.colno} 列",
            exc.msg,
            f"附近内容：{snippet}",
            "如果包含 Windows 路径，请将每个反斜杠写成两个；"
            "或删除不需要翻译的路径词条。原词库未被修改。",
        ))
        raise ValueError(message) from exc
    if not isinstance(value, dict):
        raise ValueError("Translation dictionary must be a flat JSON object")
    checked = {}
    for source, translated in value.items():
        if not isinstance(source, str) or not source.strip() or len(source) > 512:
            raise ValueError("Invalid English source label")
        if not isinstance(translated, str) or len(translated) > 512:
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
    # Blank translations from exported zh_CN.json mean "keep original".
    translations = {key: value for key, value in translations.items() if value.strip()}
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
