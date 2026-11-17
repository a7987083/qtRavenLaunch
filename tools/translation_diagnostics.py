"""Summarize native RavenLaunch-CN translation adapter events (no injection)."""
from __future__ import annotations
import json
import os
from pathlib import Path

MAX_LOG_BYTES = 8 * 1024 * 1024


def diagnostic_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or "."
    return Path(base) / "RavenLaunch-CN" / "translation-coverage.jsonl"


def summarize(log_path: Path, translations: dict[str, str] | None = None) -> dict:
    if not log_path.is_file():
        raise FileNotFoundError(log_path)
    if log_path.stat().st_size > MAX_LOG_BYTES:
        raise ValueError("Diagnostic journal exceeds 8 MiB")
    entries = []
    for number, line in enumerate(log_path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed diagnostics JSONL at line {number}: {exc}") from exc
        if not isinstance(entry, dict) or not all(
                isinstance(entry.get(k), str) for k in ("event", "page", "source")):
            raise ValueError(f"Invalid diagnostics event at line {number}")
        entries.append(entry)

    start = next((idx for idx in range(len(entries) - 1, -1, -1)
                  if entries[idx]["event"] == "session-start"), 0)
    session = entries[start:]
    applied = sorted({e["source"] for e in session
                      if e["event"] in ("applied", "tooltip-applied", "paint-applied")})
    ready = sorted({e["page"] for e in session if e["event"] == "adapter-ready"})
    failures = [{"page": e["page"], "error": e["source"]}
                for e in session if e["event"] in
                ("adapter-missing", "adapter-error", "unsupported-control")]
    mapped = {k for k, v in (translations or {}).items() if isinstance(v, str) and v.strip()}
    return {
        "session_source_hash_prefix": next(
            (e["source"] for e in session if e["event"] == "session-start"), ""),
        "event_count": len(session),
        "ready_pages": ready,
        "applied_keys": applied,
        "applied_unique_count": len(applied),
        "unobserved_translated_keys": sorted(mapped - set(applied)),
        "unobserved_note": "Not observed this run; may be on unopened pages or unsupported controls.",
        "adapter_warnings": failures,
    }
