"""Translation coverage summary tests."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from translation_diagnostics import summarize


class DiagnosticsTests(unittest.TestCase):
    def test_latest_session_only_and_unobserved_not_failure(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "translation-coverage.jsonl"
            events = [
                {"event": "session-start", "page": "bootstrap", "source": "old"},
                {"event": "applied", "page": "home", "source": "Database"},
                {"event": "session-start", "page": "bootstrap", "source": "new"},
                {"event": "adapter-ready", "page": "home", "source": ""},
                {"event": "applied", "page": "home", "source": "Register"},
                {"event": "applied", "page": "home", "source": "Register"},
                {"event": "adapter-missing", "page": "addons_114",
                 "source": "Raven114AddonsPanel"},
            ]
            p.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
            out = summarize(p, {"Database": "资料库", "Register": "注册"})
            self.assertEqual(out["session_source_hash_prefix"], "new")
            self.assertEqual(out["applied_keys"], ["Register"])
            self.assertEqual(out["unobserved_translated_keys"], ["Database"])
            self.assertEqual(out["ready_pages"], ["home"])
            self.assertEqual(len(out["adapter_warnings"]), 1)
            self.assertEqual(out["event_count"], 5)

    def test_malformed_log_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "broken.jsonl"
            p.write_text('{"event": "applied"}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Invalid diagnostics"):
                summarize(p)


if __name__ == "__main__":
    unittest.main()
