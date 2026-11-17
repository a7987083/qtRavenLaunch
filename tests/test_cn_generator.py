"""Python 3.14 synthetic archive tests for B-mode generator."""
import marshal
import types
from unittest.mock import patch
from pathlib import Path
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from cn_generator_core import (COOKIE, ENTRY, MAGIC, BOOTSTRAP_SOURCE,
                               read_carchive, decode_script, generate, sha256, make_bootstrap, load_translations)


def fixture():
    code = compile('import ichalaunch\nfrom ichalaunch.app import main\nmain()\n',
                   'run.py', 'exec')
    raw = marshal.dumps(code)
    payload = zlib.compress(raw)
    name = b'run\x00'
    toc = ENTRY.pack(ENTRY.size + len(name), 0, len(payload), len(raw), 1, b's') + name
    cookie = COOKIE.pack(MAGIC, len(payload) + len(toc) + COOKIE.size,
                         len(payload), len(toc), 314,
                         b'python314.dll'.ljust(64, b'\x00'))
    return b'MZ' + b'\0' * 32 + payload + toc + cookie


class GeneratorTests(unittest.TestCase):
    def test_core_repack_and_embedded_original_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / 'launcher.exe', Path(tmp) / 'cn.exe'
            binary = fixture()
            src.write_bytes(binary)
            output = generate(src, dst)
            self.assertTrue(output['static_verified'])
            self.assertEqual(src.read_bytes(), binary)
            self.assertNotEqual(sha256(dst.read_bytes()), sha256(binary))
            _prefix, _footer, entries = read_carchive(dst.read_bytes())
            script = decode_script(entries[0])
            self.assertEqual(script.co_filename, '<raven-cn-bootstrap>')
            original = [c for c in script.co_consts if hasattr(c, 'co_code')]
            self.assertTrue(any('ichalaunch' in c.co_names for c in original))

    def test_self_update_uses_original_source_sha_without_disabling_updater(self):
        original_source_sha = 'a' * 64
        code = compile('pass', 'synthetic-run.py', 'exec')
        bootstrap = marshal.loads(make_bootstrap(code, original_source_sha))
        ns = {}
        try:
            exec(bootstrap, ns)
            updater = types.SimpleNamespace(_running_launcher_sha256=lambda: 'b' * 64)
            ns['_cn_patch_loaded']('ichalaunch.core.self_update', updater)
            self.assertEqual(updater._running_launcher_sha256(), original_source_sha)
            # Existing official release comparisons are intentionally untouched.
            self.assertFalse(hasattr(updater, 'update_should_offer'))
        finally:
            sys.meta_path[:] = [f for f in sys.meta_path
                                if not isinstance(f, ns.get('_CnFinder', type(None)))]

    def test_invalid_source_digest_rejected(self):
        code = compile('pass', 'synthetic-run.py', 'exec')
        with self.assertRaises(ValueError):
            make_bootstrap(code, 'invalid-hash')

    def test_external_dictionary_embedded_without_changing_business_status(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "custom.json"
            src.write_text('{"HOME":"主界面","PLAY":"启动"}',
                           encoding="utf-8")
            translations = load_translations(src)
            original = compile('pass', 'synthetic-run.py', 'exec')
            bootstrap = marshal.loads(make_bootstrap(original, 'a' * 64, translations))
            ns = {}
            try:
                exec(bootstrap, ns)
                self.assertEqual(ns["_CN_TRANSLATIONS"]["HOME"], "主界面")
                self.assertEqual(ns["_CN_TRANSLATIONS"]["PLAY"], "启动")
                self.assertNotIn("SETTINGS", ns["_CN_TRANSLATIONS"])
                self.assertTrue(callable(ns["_cn_patch_widget"]))
            finally:
                sys.meta_path[:] = [finder for finder in sys.meta_path
                                    if not isinstance(finder, ns.get('_CnFinder', type(None)))]

    def test_translation_dictionary_rejects_nonflat_structure(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "bad.json"
            src.write_text('{"HOME":{"value":"主页"}}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Invalid translation"):
                load_translations(src)

    def test_flat_dictionary_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "duplicates.json"
            src.write_text('{"HOME":"主页","HOME":"首页"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate translation key"):
                load_translations(src)

    def test_flat_dictionary_no_schema_or_sections(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "simple.json"
            src.write_text('{"HOME":"主页","PLAY":"开始游戏"}', encoding="utf-8")
            self.assertEqual(load_translations(src), {"HOME": "主页", "PLAY": "开始游戏"})

    def test_settings_static_labels_and_refresh_only(self):
        """Translate original-case strings in custom and standard SETTINGS Qt widgets."""
        class QWidget:
            def __init__(self, value=""):
                self.value = value
            def text(self):
                return self.value
            def setText(self, value):
                self.value = value

        class QLabel(QWidget):
            pass

        class QAbstractButton(QWidget):
            pass

        class GluePanelButton(QWidget):
            pass

        class GradientLabel(QWidget):
            pass

        class QLineEdit(QWidget):
            pass

        class FakeSettingsPage:
            def __init__(self):
                self.title = GradientLabel("Settings")
                self.section = QLabel("Game client")
                self.action = GluePanelButton("Browse…")
                self.save = QAbstractButton("Save")
                self.status = QLabel("UPDATE")
                self.input = QLineEdit("Game client")
                self.children = [self.title, self.section, self.action,
                                 self.save, self.status, self.input]
            def findChildren(self, cls):
                return [w for w in self.children if isinstance(w, cls)]
            def refresh(self):
                self.section.setText("Game location")

        translations = {
            "Settings": "设置", "Game client": "游戏客户端",
            "Game location": "游戏目录", "Browse…": "浏览…",
            "Save": "保存", "UPDATE": "更新"
        }
        bootstrap = marshal.loads(
            make_bootstrap(compile('pass', 'synthetic-run.py', 'exec'),
                           'a' * 64, translations))
        fake_pyside = types.ModuleType("PySide6")
        fake_widgets = types.ModuleType("PySide6.QtWidgets")
        fake_widgets.QWidget = QWidget
        fake_widgets.QLabel = QLabel
        fake_widgets.QAbstractButton = QAbstractButton
        fake_pyside.QtWidgets = fake_widgets
        ns = {}
        with patch.dict(sys.modules, {"PySide6": fake_pyside,
                                      "PySide6.QtWidgets": fake_widgets}):
            try:
                exec(bootstrap, ns)
                page_module = types.SimpleNamespace(SettingsPage=FakeSettingsPage)
                ns["_cn_patch_loaded"]("ichalaunch.ui.pages.settings", page_module)
                page = FakeSettingsPage()
                self.assertEqual(page.title.text(), "设置")
                self.assertEqual(page.section.text(), "游戏客户端")
                self.assertEqual(page.action.text(), "浏览…")
                self.assertEqual(page.save.text(), "保存")
                self.assertEqual(page.input.text(), "Game client")
                self.assertEqual(page.status.text(), "UPDATE")
                page.refresh()
                self.assertEqual(page.section.text(), "游戏目录")
                self.assertEqual(page.status.text(), "UPDATE")
                self.assertTrue(FakeSettingsPage._raven_cn_settings_patched)
            finally:
                sys.meta_path[:] = [finder for finder in sys.meta_path
                                    if not isinstance(finder, ns.get('_CnFinder', type(None)))]

    def test_invalid_json_escape_reports_exact_location(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "zh_CN.json"
            # One literal backslash followed by G is not a valid JSON escape.
            bad = '{"HOME": "C:' + chr(92) + 'Games"}'
            source.write_text(bad, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "第 1 行，第"):
                load_translations(source)
            self.assertEqual(source.read_text(encoding="utf-8"), bad)

    def test_settings_exact_addons_hint_is_safe_static_label(self):
        original_text = (r"Defaults to Interface\AddOns under the game folder "
                         "when you set or change the game path. "
                         "Override only if your addons live elsewhere.")
        code = compile('pass', 'run.py', 'exec')
        bootstrap = marshal.loads(make_bootstrap(code, 'a' * 64,
                                  {original_text: "默认使用游戏目录下的插件文件夹。"}))
        class QWidget:
            pass
        class QLabel(QWidget):
            def __init__(self, text):
                self.caption = text
            def text(self):
                return self.caption
            def setText(self, value):
                self.caption = value
        class QAbstractButton(QWidget):
            pass
        class FakeSettingsPage:
            def __init__(self):
                self.hint = QLabel(original_text)
            def findChildren(self, widget_type):
                return [self.hint] if isinstance(self.hint, widget_type) else []
        qt = types.ModuleType("PySide6")
        widgets = types.ModuleType("PySide6.QtWidgets")
        widgets.QWidget, widgets.QLabel, widgets.QAbstractButton = QWidget, QLabel, QAbstractButton
        qt.QtWidgets = widgets
        ns = {}
        with patch.dict(sys.modules, {"PySide6": qt, "PySide6.QtWidgets": widgets}):
            try:
                exec(bootstrap, ns)
                ns["_cn_patch_loaded"]("ichalaunch.ui.pages.settings",
                                       types.SimpleNamespace(SettingsPage=FakeSettingsPage))
                self.assertEqual(FakeSettingsPage().hint.text(),
                                 "默认使用游戏目录下的插件文件夹。")
            finally:
                sys.meta_path[:] = [finder for finder in sys.meta_path
                                    if not isinstance(finder, ns.get("_CnFinder", type(None)))]

    def test_home_adapter_scoped_constructor_refresh_and_diagnostics(self):
        """Only HOME page's literal display strings are translated."""
        class QWidget:
            def __init__(self, value=""):
                self.value = value
            def text(self):
                return self.value
            def setText(self, value):
                self.value = value
            def toolTip(self):
                return getattr(self, "tooltip", "")
            def setToolTip(self, value):
                self.tooltip = value
            def objectName(self):
                return getattr(self, "name", "")
        class QLabel(QWidget):
            pass
        class QAbstractButton(QWidget):
            pass
        foreign_dynamic_text = "Unrelated widget from another page"
        class FakeHomePage:
            def __init__(self):
                self.register = QAbstractButton("Register")
                self.register.tooltip = "Create a RavenCraft account"
                self.dynamic = QLabel(foreign_dynamic_text)
                self.state = QLabel("UPDATE")
                self.children = [self.register, self.dynamic, self.state]
            def findChildren(self, typ):
                return [widget for widget in self.children if isinstance(widget, typ)]
            def refresh(self):
                self.summary = QLabel("Installed client mods")
                self.children.append(self.summary)

        translation = {
            "Register": "注册", "Create a RavenCraft account": "创建账号",
            "Unrelated widget from another page": "其他页面",
            "Installed client mods": "已安装的客户端模组",
            "UPDATE": "更新",
        }
        code = compile("pass", "run.py", "exec")
        bootstrap = marshal.loads(make_bootstrap(code, "a" * 64, translation))
        fake_qt = types.ModuleType("PySide6")
        widgets = types.ModuleType("PySide6.QtWidgets")
        widgets.QWidget, widgets.QLabel = QWidget, QLabel
        widgets.QAbstractButton = QAbstractButton
        fake_qt.QtWidgets = widgets
        ns = {}
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(sys.modules, {"PySide6": fake_qt,
                                          "PySide6.QtWidgets": widgets}), \
                 patch.dict("os.environ", {"LOCALAPPDATA": tmp}):
                try:
                    exec(bootstrap, ns)
                    ns["_cn_patch_loaded"]("ichalaunch.ui.pages.home",
                                           types.SimpleNamespace(HomePage=FakeHomePage))
                    page = FakeHomePage()
                    self.assertEqual(page.register.text(), "注册")
                    self.assertEqual(page.register.toolTip(), "创建账号")
                    self.assertEqual(page.dynamic.text(), "Unrelated widget from another page")
                    self.assertEqual(page.state.text(), "UPDATE")
                    page.refresh()
                    self.assertEqual(page.summary.text(), "已安装的客户端模组")
                    journal = Path(tmp) / "RavenLaunch-CN" / "translation-coverage.jsonl"
                    events = [__import__("json").loads(line)
                              for line in journal.read_text(encoding="utf-8").splitlines()]
                    self.assertTrue(any(e["event"] == "applied" and e["source"] == "Register"
                                        for e in events))
                    self.assertTrue(any(e["event"] == "adapter-ready" and e["page"] == "home"
                                        for e in events))
                finally:
                    sys.meta_path[:] = [
                        finder for finder in sys.meta_path
                        if not isinstance(finder, ns.get("_CnFinder", type(None)))
                    ]

    def test_page_adapter_missing_class_is_logged_not_crash(self):
        code = compile("pass", "run.py", "exec")
        bootstrap = marshal.loads(make_bootstrap(code, "a" * 64, {"Register": "注册"}))
        fake_qt = types.ModuleType("PySide6")
        widgets = types.ModuleType("PySide6.QtWidgets")
        widgets.QWidget = type("QWidget", (), {})
        widgets.QLabel = type("QLabel", (widgets.QWidget,), {})
        widgets.QAbstractButton = type("QAbstractButton", (widgets.QWidget,), {})
        fake_qt.QtWidgets = widgets
        ns = {}
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(sys.modules, {"PySide6": fake_qt,
                                          "PySide6.QtWidgets": widgets}), \
                 patch.dict("os.environ", {"LOCALAPPDATA": tmp}):
                try:
                    exec(bootstrap, ns)
                    ns["_cn_patch_loaded"]("ichalaunch.ui.pages.client",
                                           types.SimpleNamespace())
                    journal = Path(tmp) / "RavenLaunch-CN" / "translation-coverage.jsonl"
                    self.assertIn('"event": "adapter-missing"',
                                  journal.read_text(encoding="utf-8"))
                finally:
                    sys.meta_path[:] = [
                        finder for finder in sys.meta_path
                        if not isinstance(finder, ns.get("_CnFinder", type(None)))
                    ]

    def test_glue_combo_paint_translation_preserves_filter_semantics(self):
        """Painting changes Chinese text, business currentText/model stay English."""
        class QStyledItemDelegate:
            def __init__(self, parent=None):
                self.parent = parent
            def initStyleOption(self, option, index):
                option.text = index.data()

        class FakeView:
            def __init__(self):
                self.delegate = QStyledItemDelegate()
            def itemDelegate(self):
                return self.delegate
            def setItemDelegate(self, delegate):
                self.delegate = delegate

        class GlueComboBox:
            def __init__(self):
                self.labels = ["Installed", "Available", "All"]
                self.selected = 0
                self._view = FakeView()
            def currentText(self):
                return self.labels[self.selected]
            def itemText(self, index):
                return self.labels[index]
            def view(self):
                return self._view
            def paintEvent(self, event):
                return self.currentText()

        class Option:
            text = ""

        class Index:
            def __init__(self, text):
                self.raw = text
            def data(self):
                return self.raw

        bootstrap = marshal.loads(make_bootstrap(
            compile("pass", "run.py", "exec"), "a" * 64,
            {"Installed": "已安装", "Available": "可用", "All": "全部"}))
        qt = types.ModuleType("PySide6")
        widgets = types.ModuleType("PySide6.QtWidgets")
        widgets.QStyledItemDelegate = QStyledItemDelegate
        qt.QtWidgets = widgets
        ns = {}
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(sys.modules, {"PySide6": qt, "PySide6.QtWidgets": widgets}), \
                 patch.dict("os.environ", {"LOCALAPPDATA": td}):
                try:
                    exec(bootstrap, ns)
                    ns["_cn_patch_loaded"]("ichalaunch.ui.widgets.glue_combo",
                                           types.SimpleNamespace(GlueComboBox=GlueComboBox))
                    combo = GlueComboBox()
                    self.assertEqual(combo.currentText(), "Installed")
                    self.assertEqual(combo.itemText(0), "Installed")
                    self.assertEqual(combo.paintEvent(None), "已安装")
                    self.assertEqual(combo.currentText(), "Installed")
                    combo.selected = 1
                    self.assertEqual(combo.paintEvent(None), "可用")
                    self.assertEqual(combo.currentText(), "Available")
                    option = Option()
                    combo.view().itemDelegate().initStyleOption(option, Index("All"))
                    self.assertEqual(option.text, "全部")
                    self.assertEqual(combo.itemText(2), "All")
                finally:
                    sys.meta_path[:] = [
                        finder for finder in sys.meta_path
                        if not isinstance(finder, ns.get("_CnFinder", type(None)))
                    ]

    def test_client_dynamic_constructor_and_refresh_labels(self):
        """CLIENT helper/refresh constants are eligible, status values remain untouched."""
        class QWidget:
            def __init__(self, value=""):
                self.value = value
            def text(self):
                return self.value
            def setText(self, value):
                self.value = value
            def objectName(self):
                return getattr(self, "name", "")
            def toolTip(self):
                return ""
            def setToolTip(self, value):
                self.tooltip = value

        class QLabel(QWidget):
            pass

        class QAbstractButton(QWidget):
            pass

        class ClientPage:
            def __init__(self):
                self.rows = []
                self._add_presets_page()
                self.status = QLabel("Not installed")
                self.status.name = "client_status"
                self.rows.append(self.status)
            def _add_presets_page(self):
                self.preset = QLabel("Choose a client preset")
                self.rows.append(self.preset)
            def findChildren(self, cls):
                return [row for row in self.rows if isinstance(row, cls)]
            def refresh_from_settings(self):
                self.help = QLabel("No pending client mod changes")
                self.rows.append(self.help)

        translated = {
            "Choose a client preset": "选择客户端预设",
            "No pending client mod changes": "没有待应用的客户端更改",
            "Not installed": "未安装",
        }
        bootstrap = marshal.loads(make_bootstrap(
            compile("pass", "run.py", "exec"), "a" * 64, translated))
        qt = types.ModuleType("PySide6")
        widgets = types.ModuleType("PySide6.QtWidgets")
        widgets.QWidget = QWidget
        widgets.QLabel = QLabel
        widgets.QAbstractButton = QAbstractButton
        qt.QtWidgets = widgets
        ns = {}
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(sys.modules, {"PySide6": qt,
                                          "PySide6.QtWidgets": widgets}), \
                 patch.dict("os.environ", {"LOCALAPPDATA": td}):
                try:
                    exec(bootstrap, ns)
                    ns["_cn_patch_loaded"]("ichalaunch.ui.pages.client",
                                           types.SimpleNamespace(ClientPage=ClientPage))
                    page = ClientPage()
                    self.assertEqual(page.preset.text(), "选择客户端预设")
                    self.assertEqual(page.status.text(), "Not installed")
                    page.refresh_from_settings()
                    self.assertEqual(page.help.text(), "没有待应用的客户端更改")
                    self.assertEqual(page.status.text(), "Not installed")
                finally:
                    sys.meta_path[:] = [
                        finder for finder in sys.meta_path
                        if not isinstance(finder, ns.get("_CnFinder", type(None)))
                    ]

    def test_source_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'launcher.exe'
            src.write_bytes(fixture())
            with self.assertRaisesRegex(ValueError, 'overwrite'):
                generate(src, src)

    def test_existing_output_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / 'launcher.exe', Path(tmp) / 'cn.exe'
            src.write_bytes(fixture())
            dst.write_bytes(b'keep')
            with self.assertRaises(FileExistsError):
                generate(src, dst)
            self.assertEqual(dst.read_bytes(), b'keep')

    def test_invalid_exe_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'launcher.exe'
            src.write_bytes(b'wrong')
            with self.assertRaises(ValueError):
                generate(src, Path(tmp) / 'cn.exe')


if __name__ == '__main__':
    unittest.main()
