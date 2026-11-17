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
        """Settings text is translated while unrelated state labels remain original."""
        class QLabel:
            def __init__(self, value):
                self.value = value
            def text(self):
                return self.value
            def setText(self, value):
                self.value = value

        class QAbstractButton(QLabel):
            pass

        class FakeSettingsPage:
            def __init__(self):
                self.title = QLabel("GAME CLIENT")
                self.action = QAbstractButton("BROWSE...")
                self.status = QLabel("UPDATE")
                self.input = object()
                self.children = [self.title, self.action, self.status, self.input]
            def findChildren(self, cls):
                return [w for w in self.children if isinstance(w, cls)]
            def refresh(self):
                self.title.setText("GAME LOCATION")

        # A translation map is available, but only approved SETTINGS literals
        # are eligible for setText mutation; "UPDATE" remains business state.
        translations = {
            "GAME CLIENT": "游戏客户端", "GAME LOCATION": "游戏目录",
            "BROWSE...": "浏览...", "UPDATE": "更新"
        }
        bootstrap = marshal.loads(
            make_bootstrap(compile('pass', 'synthetic-run.py', 'exec'),
                           'a' * 64, translations))
        fake_pyside = types.ModuleType("PySide6")
        fake_widgets = types.ModuleType("PySide6.QtWidgets")
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
                self.assertEqual(page.title.text(), "游戏客户端")
                self.assertEqual(page.action.text(), "浏览...")
                self.assertEqual(page.status.text(), "UPDATE")
                page.refresh()
                self.assertEqual(page.title.text(), "游戏目录")
                self.assertEqual(page.status.text(), "UPDATE")
                self.assertTrue(FakeSettingsPage._raven_cn_settings_patched)
            finally:
                sys.meta_path[:] = [f for f in sys.meta_path
                                    if not isinstance(f, ns.get('_CnFinder', type(None)))]

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
