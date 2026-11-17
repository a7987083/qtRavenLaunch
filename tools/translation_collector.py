"""Import Glyphshift JSON / CSV exports into a review-only candidate catalogue.

This tool does not modify the launcher, Qt widgets or translation runtime.
The source/translation format was checked against the upstream Glyphshift
repository. This implementation is independent of its GPL-covered code.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024
MAX_ENTRIES = 20000


def _checked_pair(source: object, translation: object, number: int) -> tuple[str, str]:
    if not isinstance(source, str) or not source.strip():
        raise ValueError(f"Invalid source text at entry {number}")
    if not isinstance(translation, str):
        raise ValueError(f"Invalid translation at entry {number}")
    if len(source) > 4096 or len(translation) > 4096:
        raise ValueError(f"Overlong text at entry {number}")
    return source, translation


def parse_glyphshift(path: Path) -> list[dict[str, str]]:
    """Recognize Glyphshift JSON arrays/entries or UTF-8 CSV source,translation."""
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Glyphshift export exceeds 8 MiB")
    kind = path.suffix.casefold()
    if kind == ".json":
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        entries = value.get("entries") if isinstance(value, dict) else value
        if not isinstance(entries, list):
            raise ValueError("JSON export needs an entries array")
        iterator = ((e.get("source"), e.get("translation")) if isinstance(e, dict)
                    else (None, None) for e in entries)
    elif kind == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise ValueError("Missing or duplicate CSV column names")
            if not {"source", "translation"} <= set(reader.fieldnames):
                raise ValueError("CSV needs source,translation columns")
            raw = list(reader)
        iterator = ((e.get("source"), e.get("translation")) for e in raw)
    else:
        raise ValueError("Expected Glyphshift .json or .csv export")

    result = []
    seen: dict[str, str] = {}
    for number, pair in enumerate(iterator, 1):
        if number > MAX_ENTRIES:
            raise ValueError("Too many entries")
        source, translation = _checked_pair(*pair, number)
        if source in seen:
            if seen[source] != translation:
                raise ValueError(f"Conflicting translations for {source!r}")
            continue
        seen[source] = translation
        result.append({"source": source, "translation": translation,
                       "status": "review"})
    return result


def collect(source: Path, output: Path) -> dict:
    if source.resolve() == output.resolve():
        raise ValueError("Cannot overwrite the Glyphshift export")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    entries = parse_glyphshift(source)
    document = {"schema": 1, "origin": "glyphshift-export",
                "review_required": True, "entries": entries}
    output.parent.mkdir(parents=True, exist_ok=True)
    # Fail closed: avoid modifying an existing file even if created concurrently.
    with output.open("x", encoding="utf-8") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return {"entries": len(entries), "translated": sum(bool(e["translation"]) for e in entries),
            "output": str(output), "review_required": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Glyphshift JSON or CSV export")
    parser.add_argument("--out", type=Path, default=Path("translations/glyphshift-candidates.json"))
    options = parser.parse_args()
    print(json.dumps(collect(options.source, options.out), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
