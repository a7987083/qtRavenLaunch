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

    def test_login_prelaunch_writes_custom_realm_before_calling_official_game(self):
        from cn_generator_core import make_bootstrap
        import types as _types
        events = []
        class Row:
            needs_update = False
        realm = _types.SimpleNamespace(
            _raven_cn_realm_patched=True,
            apply_ravencraft_realm_endpoints=lambda game:
                events.append(("write-realm", game)),
            inspect_realm_endpoints=lambda game: [Row()],
        )
        game_pkg = _types.ModuleType("ichalaunch.game")
        game_pkg.realmlist_wtf = realm
        parent = _types.ModuleType("ichalaunch")
        parent.game = game_pkg
        launcher = _types.SimpleNamespace(
            detect_game=lambda: Path("D:/Game"),
            launch_game=lambda *a, **kw: events.append(("original-launch", kw))
        )
        ns = {}
        with patch.dict(sys.modules, {
            "ichalaunch": parent,
            "ichalaunch.game": game_pkg,
            "ichalaunch.game.realmlist_wtf": realm,
        }):
            try:
                exec(marshal.loads(make_bootstrap(
                    compile("pass", "test-run", "exec"), "a" * 64,
                    {}, "apac.capycraft.io")), ns)
                ns["_cn_patch_loaded"]("ichalaunch.game.launcher", launcher)
                launcher.launch_game(force_direct=True)
                self.assertEqual(events, [
                    ("write-realm", Path("D:/Game")),
                    ("original-launch", {"force_direct": True}),
                ])
                self.assertTrue(launcher._raven_cn_launch_host_patched)

                events.clear()
                realm.inspect_realm_endpoints = lambda game: [
                    _types.SimpleNamespace(needs_update=True)
                ]
                with self.assertRaisesRegex(RuntimeError,
                                            "Cannot safely apply custom"):
                    launcher.launch_game()
                self.assertEqual(events, [("write-realm", Path("D:/Game"))])
            finally:
                sys.meta_path[:] = [finder for finder in sys.meta_path
                    if not isinstance(finder, ns.get("_CnFinder", type(None)))]

    def test_login_prelaunch_blank_mode_does_not_write_config(self):
        from cn_generator_core import make_bootstrap
        launcher = types.SimpleNamespace(
            detect_game=lambda: Path("D:/Game"),
            launch_game=lambda: "official-launch",
        )
        original = launcher.launch_game
        ns = {}
        try:
            exec(marshal.loads(make_bootstrap(
                compile("pass", "test-run", "exec"), "a" * 64, {}, None)), ns)
            ns["_cn_patch_loaded"]("ichalaunch.game.launcher", launcher)
            self.assertIs(launcher.launch_game, original)
            self.assertEqual(launcher.launch_game(), "official-launch")
        finally:
            sys.meta_path[:] = [finder for finder in sys.meta_path
                if not isinstance(finder, ns.get("_CnFinder", type(None)))]

    def test_custom_login_runtime_scoped_to_realm_only(self):
        from dataclasses import dataclass
        from cn_generator_core import make_bootstrap

        @dataclass
        class Status:
            label: str
            realm_list: str | None
            patch_list: str | None
            missing_file: bool = False
            @property
            def needs_update(self):
                return (self.missing_file or self.realm_list != "logon.ravencraft.io"
                        or self.patch_list != "logon.ravencraft.io")

        with tempfile.TemporaryDirectory() as td:
            game = Path(td) / "game"
            (game / "WTF").mkdir(parents=True)
            realmlist = game / "realmlist.wtf"
            config = game / "WTF" / "Config.wtf"
            realmlist.write_bytes(
                b'SET realmList "logon.ravencraft.io"\r\n'
                b'SET patchList "logon.ravencraft.io"\r\n')
            config.write_bytes(
                b'SET realmList "logon.ravencraft.io"\n'
                b'SET patchList "preserve-patch.example"\n'
                b'SET gxWindow "1"\n')

            original_called = []
            module = types.SimpleNamespace(
                EXPECTED_HOST="logon.ravencraft.io",
                RealmlistFileStatus=Status,
                REALMLIST_NAME="realmlist.wtf",
                realmlist_wtf_path=lambda root: root / "realmlist.wtf",
                config_wtf_path=lambda root: root / "WTF" / "Config.wtf",
                _host_matches=lambda raw: (raw or "").lower() ==
                                        module.EXPECTED_HOST.lower(),
                _write_text=lambda path, body: path.write_bytes(body.encode("utf-8")),
                apply_ravencraft_realm_endpoints=lambda game:
                    original_called.append(game),
                realmlist_prompt_is_login_blocking=lambda rows:
                    rows[0].needs_update,
            )
            origin = compile("pass", "synthetic-run.py", "exec")
            ns = {}
            try:
                exec(marshal.loads(make_bootstrap(
                    origin, "a" * 64, {}, "apac.capycraft.io")), ns)
                ns["_cn_patch_loaded"]("ichalaunch.game.realmlist_wtf", module)
                self.assertEqual(module.EXPECTED_HOST, "apac.capycraft.io")
                rows = [Status("realmlist", "apac.capycraft.io", "logon.ravencraft.io")]
                self.assertFalse(rows[0].needs_update,
                                 "Official patchList must not force another overwrite")
                changed = module.apply_ravencraft_realm_endpoints(game)
                self.assertEqual(changed, [realmlist, config])
                self.assertFalse(original_called)
                self.assertEqual(realmlist.read_bytes(),
                    b'SET realmList "apac.capycraft.io"\r\n'
                    b'SET patchList "logon.ravencraft.io"\r\n')
                self.assertEqual(config.read_bytes(),
                    b'SET realmList "apac.capycraft.io"\n'
                    b'SET patchList "preserve-patch.example"\n'
                    b'SET gxWindow "1"\n')
                self.assertEqual(module.apply_ravencraft_realm_endpoints(game), [])
                self.assertIn("apac.capycraft.io", module.format_realmlist_prompt(rows))

                status_module = types.SimpleNamespace(
                    LOGON_HOST="logon.ravencraft.io", _cached_host="old")
                ns["_cn_patch_loaded"]("ichalaunch.game.realm_status", status_module)
                self.assertEqual(status_module.LOGON_HOST, "apac.capycraft.io")
                self.assertIsNone(status_module._cached_host)
            finally:
                sys.meta_path[:] = [finder for finder in sys.meta_path
                    if not isinstance(finder, ns.get("_CnFinder", type(None)))]

    def test_default_mode_does_not_patch_realm_functions(self):
        from cn_generator_core import make_bootstrap
        original_apply = lambda game: ["original-used"]
        module = types.SimpleNamespace(
            EXPECTED_HOST="logon.ravencraft.io",
            apply_ravencraft_realm_endpoints=original_apply,
        )
        ns = {}
        try:
            exec(marshal.loads(make_bootstrap(
                compile("pass", "synthetic-run.py", "exec"),
                "a" * 64, {}, "")), ns)
            ns["_cn_patch_loaded"]("ichalaunch.game.realmlist_wtf", module)
            self.assertIs(module.apply_ravencraft_realm_endpoints, original_apply)
            self.assertEqual(module.EXPECTED_HOST, "logon.ravencraft.io")
        finally:
            sys.meta_path[:] = [finder for finder in sys.meta_path
                if not isinstance(finder, ns.get("_CnFinder", type(None)))]

    def test_optional_login_server_patches_only_realmlist_in_output(self):
        from cn_generator_core import assemble, REALMLIST_ENTRY
        original_resource = (
            b'SET realmList "logon.ravencraft.io"\r\n'
            b'SET patchList "logon.ravencraft.io"\r\n'
        )
        raw = fixture()
        start, cookie, entries = read_carchive(raw)
        resource_name = REALMLIST_ENTRY.encode("utf-8") + b"\0"
        entries.append({
            "name": REALMLIST_ENTRY, "namebytes": resource_name,
            "kind": b"b", "compressed": 1,
            "raw_size": len(original_resource),
            "blob": zlib.compress(original_resource),
        })
        source_bytes = assemble(raw[:start], cookie, entries)
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "official.exe"
            translated = Path(td) / "translated.exe"
            unchanged = Path(td) / "default.exe"
            source.write_bytes(source_bytes)
            custom = generate(source, translated, login_server="apac.capycraft.io")
            self.assertEqual(custom["login_server_override"], "apac.capycraft.io")
            self.assertEqual(custom["modified_entries"], ["run", REALMLIST_ENTRY])
            self.assertEqual(source.read_bytes(), source_bytes)
            _, _, output_entries = read_carchive(translated.read_bytes())
            record = next(row for row in output_entries if row["name"] == REALMLIST_ENTRY)
            content = zlib.decompress(record["blob"])
            self.assertEqual(content,
                b'SET realmList "apac.capycraft.io"\r\n'
                b'SET patchList "logon.ravencraft.io"\r\n')
            default = generate(source, unchanged, login_server="   ")
            self.assertIsNone(default["login_server_override"])
            self.assertEqual(default["modified_entries"], ["run"])
            _, _, default_entries = read_carchive(unchanged.read_bytes())
            default_entry = next(row for row in default_entries
                                 if row["name"] == REALMLIST_ENTRY)
            self.assertEqual(default_entry["blob"], zlib.compress(original_resource))
            self.assertTrue(default["original_unchanged"])

    def test_login_server_validation_and_missing_resource_rejected(self):
        from cn_generator_core import validate_login_server
        self.assertIsNone(validate_login_server(None))
        self.assertIsNone(validate_login_server(""))
        self.assertEqual(validate_login_server(" apac.capycraft.io "),
                         "apac.capycraft.io")
        for bad in ("https://apac.capycraft.io", "example.org:3724",
                    "example.org/path", 'example.org"\nSET patchList "bad',
                    "localhost\r\n", "a..b", "-bad.org", "bad_.org",
                    "2001:db8::1"):
            with self.subTest(host=repr(bad)):
                with self.assertRaises(ValueError):
                    validate_login_server(bad)
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "original.exe"
            target = Path(td) / "output.exe"
            source.write_bytes(fixture())  # deliberately no realmlist data
            with self.assertRaisesRegex(ValueError, "realmlist.wtf"):
                generate(source, target, login_server="apac.capycraft.io")
            self.assertFalse(target.exists())
            self.assertEqual(source.read_bytes(), fixture())

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

    def test_client_ui_helper_strings_include_nested_literals(self):
        # A nested callback/lambda may own the original display string,
        # even though the parent method does not have it in flat co_consts.
        ns = {}
        exec(compile(
            "class Page:\n"
            "    def _build_menu(self):\n"
            "        def configure():\n"
            "            return 'Performance / Fixes'\n"
            "        return configure()\n"
            "    def set_check_status(self):\n"
            "        return 'BUSINESS_STATUS'\n",
            "fixture.py", "exec"), ns)
        bootstrap = marshal.loads(make_bootstrap(
            compile("pass", "run.py", "exec"), "a" * 64, {}))
        runtime = {}
        try:
            exec(bootstrap, runtime)
            literals = runtime["_cn_client_ui_literals"](ns["Page"])
            self.assertIn("Performance / Fixes", literals)
            self.assertNotIn("BUSINESS_STATUS", literals)
        finally:
            sys.meta_path[:] = [x for x in sys.meta_path
                                if not isinstance(x, runtime.get("_CnFinder", type(None)))]

    def test_glue_panel_button_paint_preserves_navigation_text(self):
        class GluePanelButton:
            def __init__(self, caption):
                self.caption = caption
            def text(self):
                return self.caption
            def paintEvent(self, _event):
                return self.text()

        bootstrap = marshal.loads(make_bootstrap(
            compile("pass", "run.py", "exec"), "a" * 64,
            {"Presets": "预设", "Launch": "启动"}))
        ns = {}
        try:
            exec(bootstrap, ns)
            ns["_cn_patch_loaded"](
                "ichalaunch.ui.widgets.glue_panel_button",
                types.SimpleNamespace(GluePanelButton=GluePanelButton))
            button = GluePanelButton("Presets")
            self.assertEqual(button.text(), "Presets")
            self.assertEqual(button.paintEvent(None), "预设")
            self.assertEqual(button.text(), "Presets")
        finally:
            sys.meta_path[:] = [x for x in sys.meta_path
                                if not isinstance(x, ns.get("_CnFinder", type(None)))]

    def test_settings_module_global_discord_labels_and_field_refresh(self):
        """Original UI captions are module globals, not init string literals."""
        class QWidget:
            def __init__(self, value=""):
                self.value = value
            def text(self):
                return self.value
            def setText(self, value):
                self.value = value
            def objectName(self):
                return ""
            def toolTip(self):
                return ""
            def setToolTip(self, value):
                pass
        class QLabel(QWidget):
            pass
        class QAbstractButton(QWidget):
            pass
        class SettingsPage:
            def __init__(self):
                self.parent = QAbstractButton(parent_caption)
                self.child = QAbstractButton(child_caption)
                self.name = QAbstractButton(field_names["name"])
                self.status = QLabel("UPDATE")
                self.controls = [self.parent, self.child, self.name, self.status]
            def findChildren(self, kind):
                return [item for item in self.controls if isinstance(item, kind)]
            def _sync_discord_character_row(self):
                self.child.setText(child_caption)
            def showEvent(self, event):
                self.parent.setText(parent_caption)

        parent_caption = "Show status on Discord"
        child_caption = "Show character details (name, race, class, guild, zone, level)"
        field_names = {"name": "Name"}
        fakeqt = types.ModuleType("PySide6")
        widgets = types.ModuleType("PySide6.QtWidgets")
        widgets.QWidget, widgets.QLabel, widgets.QAbstractButton = QWidget, QLabel, QAbstractButton
        fakeqt.QtWidgets = widgets
        ns = {}
        bootstrap = marshal.loads(make_bootstrap(
            compile("pass", "run.py", "exec"), "a" * 64,
            {parent_caption: "在 Discord 上显示活动状态",
             child_caption: "显示角色详情", "Name": "名称", "UPDATE": "更新"}))
        with patch.dict(sys.modules, {"PySide6": fakeqt,
                                      "PySide6.QtWidgets": widgets}):
            try:
                exec(bootstrap, ns)
                module = types.SimpleNamespace(
                    SettingsPage=SettingsPage,
                    _DISCORD_PARENT_LABEL=parent_caption,
                    _DISCORD_CHILD_LABEL=child_caption,
                    BROADCAST_FIELD_LABELS=field_names)
                ns["_cn_patch_loaded"]("ichalaunch.ui.pages.settings", module)
                page = SettingsPage()
                self.assertEqual(page.parent.text(), "在 Discord 上显示活动状态")
                self.assertEqual(page.child.text(), "显示角色详情")
                self.assertEqual(page.name.text(), "名称")
                self.assertEqual(page.status.text(), "UPDATE")
                page._sync_discord_character_row()
                self.assertEqual(page.child.text(), "显示角色详情")
                page.showEvent(None)
                self.assertEqual(page.parent.text(), "在 Discord 上显示活动状态")
            finally:
                sys.meta_path[:] = [
                    finder for finder in sys.meta_path
                    if not isinstance(finder, ns.get("_CnFinder", type(None)))]

    def test_cat_nav_theme_option_translation_preserves_native_text(self):
        """CLIENT CatNavButton QStyleOption uses Chinese, .text() stays English."""
        class StyleOption:
            def __init__(self):
                self.text = ""

        class ThemeButton:
            def __init__(self, label, object_name):
                self.caption = label
                self.name = object_name
            def objectName(self):
                return self.name
            def text(self):
                return self.caption
            def initStyleOption(self, option):
                option.text = self.caption
            def paintEvent(self, event):
                before = self.text()
                option = StyleOption()
                self.initStyleOption(option)
                return before, option.text

        bootstrap = marshal.loads(make_bootstrap(
            compile("pass", "run.py", "exec"), "a" * 64,
            {"Advanced": "高级", "Presets": "预设"}))
        ns = {}
        with tempfile.TemporaryDirectory() as td:
            with patch.dict("os.environ", {"LOCALAPPDATA": td}):
                try:
                    exec(bootstrap, ns)
                    ns["_cn_patch_loaded"](
                        "ichalaunch.ui.widgets.theme_button",
                        types.SimpleNamespace(ThemeButton=ThemeButton))
                    nav = ThemeButton("Advanced", "CatNavButton")
                    other = ThemeButton("Advanced", "OrdinaryThemeButton")
                    self.assertEqual(nav.text(), "Advanced")
                    self.assertEqual(nav.paintEvent(None), ("高级", "高级"))
                    self.assertEqual(nav.text(), "Advanced")
                    self.assertEqual(other.paintEvent(None), ("Advanced", "Advanced"))
                    self.assertEqual(other.text(), "Advanced")
                    report = (Path(td) / "RavenLaunch-CN" /
                              "translation-coverage.jsonl").read_text(encoding="utf-8")
                    self.assertIn('"event": "style-applied"', report)
                    self.assertIn('"source": "Advanced"', report)
                finally:
                    sys.meta_path[:] = [
                        finder for finder in sys.meta_path
                        if not isinstance(finder, ns.get("_CnFinder", type(None)))
                    ]

    def test_client_checkboxes_and_radio_paint_only_keep_business_values(self):
        """Qt self-drawn controls display Chinese without modifying their text or state."""
        class FakeChoice:
            def __init__(self, label):
                self.label = label
                self.checked = True
            def text(self):
                return self.label
            def isChecked(self):
                return self.checked
            def paintEvent(self, event):
                return (self.text(), self.isChecked())
        class ThemeCheckBox(FakeChoice):
            pass
        class ThemeRadioButton(FakeChoice):
            pass

        mapping = {
            "Minimize launcher when game starts": "游戏启动时最小化启动器",
            "None": "无",
        }
        bootstrap = marshal.loads(make_bootstrap(
            compile("pass", "run.py", "exec"), "a" * 64, mapping))
        ns = {}
        try:
            exec(bootstrap, ns)
            ns["_cn_patch_loaded"]("ichalaunch.ui.widgets.theme_checkbox",
                                   types.SimpleNamespace(ThemeCheckBox=ThemeCheckBox))
            ns["_cn_patch_loaded"]("ichalaunch.ui.widgets.theme_radio",
                                   types.SimpleNamespace(ThemeRadioButton=ThemeRadioButton))
            check = ThemeCheckBox("Minimize launcher when game starts")
            radio = ThemeRadioButton("None")
            self.assertEqual(check.paintEvent(None), ("游戏启动时最小化启动器", True))
            self.assertEqual(check.text(), "Minimize launcher when game starts")
            self.assertTrue(check.isChecked())
            self.assertEqual(radio.paintEvent(None), ("无", True))
            self.assertEqual(radio.text(), "None")
            self.assertTrue(radio.isChecked())
        finally:
            sys.meta_path[:] = [
                finder for finder in sys.meta_path
                if not isinstance(finder, ns.get("_CnFinder", type(None)))
            ]

    def test_client_catalog_description_label_is_scoped_not_status(self):
        """Only an allowlisted catalog description QLabel is mutated."""
        description = (
            "Patches WoW.exe (not a DLL). Farclip, grass, nameplates, "
            "4GB LAA, camera skip fix, custom glues, and blue moon on by "
            "default. Widescreen FoV, sound, and quickloot are optional "
            "— use the cog to configure."
        )
        class QWidget:
            def __init__(self, label="", name=""):
                self.value, self.name = label, name
            def text(self):
                return self.value
            def setText(self, value):
                self.value = value
            def objectName(self):
                return self.name
            def toolTip(self):
                return ""
            def setToolTip(self, value):
                pass
        class QLabel(QWidget):
            pass
        class QAbstractButton(QWidget):
            pass
        class ClientPage:
            def __init__(self):
                self.detail = QLabel(description)
                self.status = QLabel("Not installed", "client_status")
                self.module_name = QLabel("Vanilla Tweaks V2")
                self.widgets = [self.detail, self.status, self.module_name]
            def findChildren(self, cls):
                return [w for w in self.widgets if isinstance(w, cls)]

        qt = types.ModuleType("PySide6")
        widgets = types.ModuleType("PySide6.QtWidgets")
        widgets.QWidget, widgets.QLabel = QWidget, QLabel
        widgets.QAbstractButton = QAbstractButton
        qt.QtWidgets = widgets
        runtime = {}
        bootstrap = marshal.loads(make_bootstrap(
            compile("pass", "run.py", "exec"), "a" * 64,
            {description: "修补 WoW.exe 的画面与兼容性功能。",
             "Not installed": "未安装",
             "Vanilla Tweaks V2": "风险：不要修改模组标识"}))
        with patch.dict(sys.modules, {"PySide6": qt, "PySide6.QtWidgets": widgets}):
            try:
                exec(bootstrap, runtime)
                runtime["_cn_patch_loaded"](
                    "ichalaunch.ui.pages.client",
                    types.SimpleNamespace(ClientPage=ClientPage))
                page = ClientPage()
                self.assertEqual(page.detail.text(), "修补 WoW.exe 的画面与兼容性功能。")
                self.assertEqual(page.status.text(), "Not installed")
                self.assertEqual(page.module_name.text(), "Vanilla Tweaks V2")
            finally:
                sys.meta_path[:] = [
                    f for f in sys.meta_path
                    if not isinstance(f, runtime.get("_CnFinder", type(None)))
                ]

    def test_config_editor_labels_only_without_touching_config_values(self):
        """CVAR/DXVK captions change, key/value/combobox stay unmodified."""
        class QLabel:
            def __init__(self, value):
                self.value = value
            def text(self):
                return self.value
            def setText(self, value):
                self.value = value

        class FakeCombo:
            def __init__(self):
                self.values = [("Off", "off"), ("Auto", "auto")]
            def currentData(self):
                return "auto"

        class BaseDialog:
            def __init__(self):
                self.label = QLabel("Farclip (terrain distance)")
                self.group = QLabel("Distance")
                self.unrelated = QLabel("Unrelated business label")
                self.combo = FakeCombo()
                self.slider_value = 777
                self.labels = [self.label, self.group, self.unrelated]
            def findChildren(self, cls):
                return [x for x in self.labels if isinstance(x, cls)]

        class ConfigWtfSettingsDialog(BaseDialog):
            pass

        class DxvkConfSettingsDialog(BaseDialog):
            def __init__(self):
                super().__init__()
                self.label = QLabel("DXVK frame cap")
                self.group = QLabel("Presentation")
                self.labels = [self.label, self.group, self.unrelated]

        config_spec = types.SimpleNamespace(CVAR_SPECS=(
            types.SimpleNamespace(name="farclip", label="Farclip (terrain distance)",
                                  group="Distance", hint=""),
        ))
        dxvk_spec = types.SimpleNamespace(DXVK_SPECS=(
            types.SimpleNamespace(name="d3d9.maxFrameRate", label="DXVK frame cap",
                                  group="Presentation", hint=""),
        ))
        fake_qt = types.ModuleType("PySide6")
        fake_widgets = types.ModuleType("PySide6.QtWidgets")
        fake_widgets.QLabel = QLabel
        fake_qt.QtWidgets = fake_widgets
        code = compile("pass", "synthetic-run.py", "exec")
        boot = marshal.loads(make_bootstrap(code, "a" * 64, {
            "Farclip (terrain distance)": "地形视距",
            "Distance": "距离",
            "DXVK frame cap": "DXVK 帧率上限",
            "Presentation": "显示方式",
            "Unrelated business label": "错误的业务翻译",
        }))
        runtime = {}
        with patch.dict(sys.modules, {
            "PySide6": fake_qt, "PySide6.QtWidgets": fake_widgets,
            "ichalaunch.game.config_wtf_edits": config_spec,
            "ichalaunch.game.dxvk_conf_edits": dxvk_spec,
        }):
            try:
                exec(boot, runtime)
                runtime["_cn_patch_loaded"]("ichalaunch.ui.widgets.dialogs",
                    types.SimpleNamespace(ConfigWtfSettingsDialog=ConfigWtfSettingsDialog,
                                          DxvkConfSettingsDialog=DxvkConfSettingsDialog))
                config = ConfigWtfSettingsDialog()
                dxvk = DxvkConfSettingsDialog()
                self.assertEqual(config.label.text(), "地形视距")
                self.assertEqual(config.group.text(), "距离")
                self.assertEqual(dxvk.label.text(), "DXVK 帧率上限")
                self.assertEqual(dxvk.group.text(), "显示方式")
                self.assertEqual(config.unrelated.text(), "Unrelated business label")
                self.assertEqual(config.combo.currentData(), "auto")
                self.assertEqual(config.slider_value, 777)
                self.assertEqual(config_spec.CVAR_SPECS[0].name, "farclip")
                self.assertEqual(dxvk_spec.DXVK_SPECS[0].name, "d3d9.maxFrameRate")
            finally:
                sys.meta_path[:] = [
                    finder for finder in sys.meta_path
                    if not isinstance(finder, runtime.get("_CnFinder", type(None)))
                ]

    def test_four_known_metal_prompts_translate_only_their_display_labels(self):
        """Dynamic placeholders preserve folders/counts and dialog decisions."""
        class QLabel:
            def __init__(self, value, object_name=""):
                self.value, self.name = value, object_name
            def text(self):
                return self.value
            def setText(self, value):
                self.value = value
            def objectName(self):
                return self.name

        class MetalFramedDialog:
            def __init__(self, parent, title, text):
                self.title = QLabel(title, "ThemedDialogTitle")
                self.body = QLabel(text, "ThemedDialogBody")
                self.widgets = [self.title, self.body]
                self.result_code = 7
            def findChildren(self, cls):
                return [label for label in self.widgets if isinstance(label, cls)]

        class ThemedDialog(MetalFramedDialog):
            pass

        class RecommendedForkSwapDialog(ThemedDialog):
            def __init__(self):
                super().__init__(None, "Recommended addon forks",
                                 "These installed addons have a RavenCraft-recommended fork. Switch is selected by default — Apply switches those rows. Keep this fork is remembered for the current recommendation (we ask again only if the catalog pick changes). After a switch, Installed rows get a Revert control.")
                self.addon = QLabel("SHAGUTWEAKS")
                self.row = QLabel("Installed: ShaguTweaks-dusk\n"
                                  "Recommended: ShaguTweaks-octowowst")
                self.widgets += [self.addon, self.row]
                self.selected_fork = "ShaguTweaks-octowowst"

        mapping = {
            "Addon folder name mismatch": "插件文件夹名称不匹配",
            "Recommended addon forks": "推荐插件分支",
            "GAME UPDATE": "游戏更新",
            "Reset Client Link": "重置客户端关联",
            "Folder is {folder} but the .toc is {toc}. WoW requires the folder "
            "name to match the .toc. Rename folder to {target}?":
                "文件夹 {folder} 的目录定义为 {toc}。重命名为 {target}？",
            "{count} published game file(s) do not match this install.":
                "有 {count} 个游戏文件不匹配。",
            "PLAY will stay on UPDATE until this finishes.": "完成之前保持更新状态。",
            "Installed:": "当前安装",
            "Recommended:": "推荐版本",
            "Clear the saved WoW folder from launcher settings?": "清除 WoW 目录？",
            "PLAY will become INSTALL so you can choose a new install "
            "location. This does not delete any files on disk.":
                "现在可重新选择目录，磁盘文件不会被删除。",
            "These installed addons have a RavenCraft-recommended fork. Switch is selected by default — Apply switches those rows. Keep this fork is remembered for the current recommendation (we ask again only if the catalog pick changes). After a switch, Installed rows get a Revert control.":
                "这些插件已有推荐分支。",
            "SHAGUTWEAKS": "不要修改模组名称",
        }
        boot = marshal.loads(make_bootstrap(
            compile("pass", "synthetic-run.py", "exec"), "a" * 64, mapping))
        qt = types.ModuleType("PySide6")
        widgets = types.ModuleType("PySide6.QtWidgets")
        widgets.QLabel = QLabel
        qt.QtWidgets = widgets
        runtime = {}
        with patch.dict(sys.modules, {"PySide6": qt,
                                      "PySide6.QtWidgets": widgets}):
            try:
                exec(boot, runtime)
                runtime["_cn_patch_loaded"](
                    "ichalaunch.ui.widgets.metal_framed_dialog",
                    types.SimpleNamespace(MetalFramedDialog=MetalFramedDialog))
                runtime["_cn_patch_loaded"](
                    "ichalaunch.ui.widgets.dialogs",
                    types.SimpleNamespace(ThemedDialog=ThemedDialog,
                                          RecommendedForkSwapDialog=RecommendedForkSwapDialog))

                mismatch = ThemedDialog(None, "Addon folder name mismatch",
                    "Folder is SuperRaidVisual获取技能-saa but the .toc is "
                    "SuperRaidVisual.toc. WoW requires the folder name to match "
                    "the .toc. Rename folder to SuperRaidVisual?")
                self.assertEqual(mismatch.title.text(), "插件文件夹名称不匹配")
                self.assertIn("SuperRaidVisual获取技能-saa", mismatch.body.text())
                self.assertIn("SuperRaidVisual.toc", mismatch.body.text())
                self.assertIn("SuperRaidVisual？", mismatch.body.text())
                self.assertEqual(mismatch.result_code, 7)

                update = ThemedDialog(None, "GAME UPDATE",
                    "120 published game file(s) do not match this install.\n\n"
                    "PLAY will stay on UPDATE until this finishes.")
                self.assertEqual(update.title.text(), "游戏更新")
                self.assertIn("有 120 个游戏文件不匹配。", update.body.text())
                self.assertIn("完成之前保持更新状态。", update.body.text())

                reset = ThemedDialog(None, "Reset Client Link",
                    "Clear the saved WoW folder from launcher settings?\n\n"
                    "PLAY will become INSTALL so you can choose a new install "
                    "location. This does not delete any files on disk.")
                self.assertEqual(reset.title.text(), "重置客户端关联")
                self.assertEqual(reset.body.text(),
                    "清除 WoW 目录？\n\n现在可重新选择目录，磁盘文件不会被删除。")

                forks = RecommendedForkSwapDialog()
                self.assertEqual(forks.title.text(), "推荐插件分支")
                self.assertEqual(forks.body.text(), "这些插件已有推荐分支。")
                self.assertEqual(forks.row.text(),
                    "当前安装: ShaguTweaks-dusk\n推荐版本: ShaguTweaks-octowowst")
                self.assertEqual(forks.addon.text(), "SHAGUTWEAKS")
                self.assertEqual(forks.selected_fork, "ShaguTweaks-octowowst")

                unrelated = ThemedDialog(None, "Delete everything?",
                                         "File path C:\\Games should not change")
                self.assertEqual(unrelated.title.text(), "Delete everything?")
                self.assertEqual(unrelated.body.text(),
                                 "File path C:\\Games should not change")
            finally:
                sys.meta_path[:] = [
                    finder for finder in sys.meta_path
                    if not isinstance(finder, runtime.get("_CnFinder", type(None)))
                ]

    def test_prompt_placeholder_substitution_preserves_literal_brace_names(self):
        """No recursive substitution; an invalid user template leaves English."""
        source = (
            "Folder is Super{toc}Raid-saa but the .toc is SuperRaid.toc. "
            "WoW requires the folder name to match the .toc. "
            "Rename folder to SuperRaid?"
        )
        template_key = (
            "Folder is {folder} but the .toc is {toc}. WoW requires the "
            "folder name to match the .toc. Rename folder to {target}?"
        )
        translation = "当前目录 {folder}，定义文件 {toc}，目标 {target}？"
        boot = marshal.loads(make_bootstrap(
            compile("pass", "synthetic-run.py", "exec"), "a" * 64,
            {template_key: translation}))
        ns = {}
        try:
            exec(boot, ns)
            actual = ns["_cn_dialog_display_text"](source, "addon-folder-mismatch")
            self.assertIn("Super{toc}Raid-saa", actual)
            self.assertIn("SuperRaid.toc", actual)
            self.assertIn("SuperRaid？", actual)
            # Reject a malformed template which would silently drop a
            # folder name or the target rename path.
            ns["_CN_TRANSLATIONS"][template_key] = "将 {folder} 重命名？"
            self.assertEqual(ns["_cn_dialog_display_text"](
                source, "addon-folder-mismatch"), source)
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
