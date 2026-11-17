"""B2.1 importer contract tests (independent of Glyphshift runtime)."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from translation_collector import parse_glyphshift, collect


class CollectorTests(unittest.TestCase):
    def test_json_entries_with_metadata_and_empty_translation(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "export.json"
            source.write_text(json.dumps({"metadata": {"name": "test"}, "entries": [
                {"source": "GAME CLIENT", "translation": "游戏客户端"},
                {"source": "GAME LOCATION", "translation": ""},
                {"source": "GAME CLIENT", "translation": "游戏客户端"},
            ]}), encoding="utf-8")
            rows = parse_glyphshift(source)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["status"], "review")
            self.assertEqual(rows[1]["translation"], "")

    def test_json_plain_array(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "export.json"
            source.write_text('[{"source":"SETTINGS","translation":"设置"}]', encoding="utf-8")
            self.assertEqual(parse_glyphshift(source)[0]["source"], "SETTINGS")

    def test_utf8_bom_csv_quoted_comma(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "export.csv"
            source.write_text('source,translation,notes\n"BROWSE, FILE","浏览, 文件",x\n', encoding="utf-8-sig")
            self.assertEqual(parse_glyphshift(source)[0]["translation"], "浏览, 文件")

    def test_conflicting_duplicate_refused(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "export.json"
            source.write_text('[{"source":"PLAY","translation":"开始"},{"source":"PLAY","translation":"运行"}]', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Conflicting"):
                parse_glyphshift(source)

    def test_output_requires_review_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "export.csv"
            dest = Path(td) / "out.json"
            source.write_text('source,translation\nCLIENT,客户端\n', encoding="utf-8")
            meta = collect(source, dest)
            self.assertTrue(meta["review_required"])
            result = json.loads(dest.read_text(encoding="utf-8"))
            self.assertTrue(result["review_required"])
            with self.assertRaises(FileExistsError):
                collect(source, dest)

    def test_bad_headers_refused(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "export.csv"
            source.write_text('original,localized\na,b\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source,translation"):
                parse_glyphshift(source)


if __name__ == "__main__":
    unittest.main()
