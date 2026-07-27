"""
Parse a Journey JSON export into normalized entries ready for embedding.

Privacy note: this script processes real journal content locally. It must
never print entry content to stdout — only counts and aggregate stats —
since anything printed here can end up in a Claude Code tool result.
Output goes to data/processed/entries.jsonl (gitignored).

Usage:
    python -m reflector.parse_entries
"""

import json
import sys
import zipfile
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
EXTRACT_DIR = RAW_DIR / "extracted"
OUT_PATH = Path(__file__).parent.parent / "data" / "processed" / "entries.jsonl"


def source_dir() -> Path:
    zips = list(RAW_DIR.glob("*.zip"))
    if zips:
        EXTRACT_DIR.mkdir(exist_ok=True)
        for z in zips:
            with zipfile.ZipFile(z) as f:
                f.extractall(EXTRACT_DIR)
        return EXTRACT_DIR
    return RAW_DIR


def strip_html(raw: str) -> str:
    if "<" not in raw:
        return raw.strip()
    return BeautifulSoup(raw, "html.parser").get_text("\n").strip()


def normalize(entry: dict) -> dict | None:
    text = strip_html(entry.get("text", ""))
    if not text:
        return None
    ms = entry["date_journal"]
    tz = entry.get("timezone") or "UTC"
    try:
        dt = datetime.fromtimestamp(ms / 1000, tz=ZoneInfo(tz))
    except Exception:
        dt = datetime.fromtimestamp(ms / 1000, tz=dt_timezone.utc)
    return {
        "id": entry["id"],
        "date": dt.isoformat(),
        "text": text,
        "mood": entry.get("mood"),
        "sentiment": entry.get("sentiment"),
        "tags": entry.get("tags") or [],
        "favourite": entry.get("favourite", False),
        "lat": entry.get("lat"),
        "lon": entry.get("lon"),
        "address": entry.get("address") or None,
        "photo_count": len(entry.get("photos") or []),
    }


def main() -> None:
    src = source_dir()
    json_files = sorted(src.rglob("*.json"))
    if not json_files:
        print(f"No .json files found under {src}.")
        sys.exit(1)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped_empty = 0
    skipped_error = 0
    earliest = latest = None

    with OUT_PATH.open("w") as out:
        for jf in json_files:
            try:
                raw_entry = json.loads(jf.read_text())
            except json.JSONDecodeError:
                skipped_error += 1
                continue
            normalized = normalize(raw_entry)
            if normalized is None:
                skipped_empty += 1
                continue
            out.write(json.dumps(normalized) + "\n")
            written += 1
            d = normalized["date"]
            earliest = d if earliest is None or d < earliest else earliest
            latest = d if latest is None or d > latest else latest

    print(f"Parsed {written} entries -> {OUT_PATH}")
    print(f"Skipped: {skipped_empty} empty-text, {skipped_error} malformed JSON")
    if earliest:
        print(f"Date range (boundaries only): {earliest} to {latest}")


if __name__ == "__main__":
    main()
