"""CPython 3.14 synthetic offline PYZ extraction and dictionary preservation."""
from __future__ import annotations

import json
import marshal
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from cn_generator_core import COOKIE, ENTRY, MAGIC, load_translations, make_bootstrap
from extract_strings import export_strings, likely_ui_literal, read_ui_constants


def fixture() -> bytes:
    module = compile(
        'TITLE = "Game client"\n'
        'URL = "https://example.org"\n'
        'def setup():\n'
        '  labels = ("HOME", "Browse…", "Verify")\n'
        '  state = "status_internal"\n'
        '  return labels\n',
        "ichalaunch/ui/pages/settings.py", "exec")
    noise = compile('URL = "https://not-ui.example.org"\n',
                    "irrelevant.py", "exec")
    ui_data = zlib.compress(marshal.dumps(module))
    noise_data = zlib.compress(marshal.dumps(noise))
    directory = marshal.dumps([
        ("ichalaunch.ui.pages.settings", (0, 12, len(ui_data))),
        ("irrelevant.module", (0, 12 + len(ui_data), len(noise_data))),
    ])
    pyz = (b"PYZ\x00" + b"\0" * 4
           + struct.pack("!I", 12 + len(ui_data) + len(noise_data))
           + ui_data + noise_data + directory)
    name = b"PYZ.pyz\0"
    entry = ENTRY.pack(ENTRY.size + len(name), 0, len(pyz),
                       len(pyz), 0, b"z") + name
    cookie = COOKIE.pack(MAGIC, len(pyz) + len(entry) + COOKIE.size,
                         len(pyz), len(entry), 314,
                         b"python314.dll".ljust(64, b"\0"))
    return b"MZ" + b"X" * 48 + pyz + entry + cookie


class ExtractTests(unittest.TestCase):
    def test_real_literals_and_ui_filter(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "source.exe"
            source.write_bytes(fixture())
            strings, report = read_ui_constants(source)
            self.assertEqual(report["ui_modules_examined"], 1)
            self.assertIn("Game client", strings)
            self.assertIn("Browse…", strings)
            self.assertIn("HOME", strings)
            self.assertNotIn("https://example.org", strings)
            self.assertNotIn("status_internal", strings)

    def test_exports_flat_json_with_empty_translations(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "source.exe"
            target = Path(d) / "zh_CN.json"
            binary = fixture()
            source.write_bytes(binary)
            meta = export_strings(source, target)
            text = target.read_text(encoding="utf-8")
            doc = json.loads(text)
            self.assertTrue(text.endswith("\n"))
            self.assertEqual(doc["Game client"], "")
            self.assertEqual(doc["Browse…"], "")
            self.assertNotIn("schema", doc)
            self.assertEqual(source.read_bytes(), binary)
            self.assertGreater(meta["new_empty_entries"], 0)

    def test_merge_preserves_translation_and_old_keys(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "source.exe"
            target = Path(d) / "zh_CN.json"
            source.write_bytes(fixture())
            target.write_text('{"HOME":"主页","legacy item":"以前的译文"}',
                              encoding="utf-8")
            report = export_strings(source, target)
            self.assertEqual(report["kept_existing"], 2)
            translations = load_translations(target)
            self.assertEqual(translations["HOME"], "主页")
            self.assertEqual(translations["legacy item"], "以前的译文")
            self.assertEqual(translations["Game client"], "")
            export_strings(source, target)
            self.assertEqual(load_translations(target), translations)

    def test_blank_translations_not_embedded(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "zh_CN.json"
            source.write_text('{"HOME":"主页","Game client":""}', encoding="utf-8")
            translations = load_translations(source)
            code = compile('pass', "run.py", "exec")
            imported = marshal.loads(make_bootstrap(code, 'a' * 64, translations))
            ns = {}
            try:
                exec(imported, ns)
                self.assertEqual(ns["_CN_TRANSLATIONS"], {"HOME": "主页"})
            finally:
                sys.meta_path[:] = [
                    finder for finder in sys.meta_path
                    if not isinstance(finder, ns.get("_CnFinder", type(None)))
                ]

    def test_failed_extraction_leaves_previous_json_intact(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "broken.exe"
            target = Path(d) / "zh_CN.json"
            source.write_bytes(b"broken")
            target.write_text('{"HOME":"主页"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                export_strings(source, target)
            self.assertEqual(target.read_text(encoding="utf-8"), '{"HOME":"主页"}')

    def test_no_merge_refuses_existing_file(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "source.exe"
            target = Path(d) / "zh_CN.json"
            source.write_bytes(fixture())
            target.write_text("{}", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                export_strings(source, target, merge=False)

    def test_literal_filter_is_not_a_patch_authorization(self):
        self.assertTrue(likely_ui_literal("Browse…"))
        self.assertFalse(likely_ui_literal("https://example.org"))
        self.assertFalse(likely_ui_literal("debug_internal_id"))


if __name__ == "__main__":
    unittest.main()
