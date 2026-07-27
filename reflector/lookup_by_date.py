"""
One-off calibration lookup: given specific dates the user has identified
as known emotional reference points, print only the mood/sentiment values
for entries on those dates — never the text.

Usage:
    python -m reflector.lookup_by_date 2026-06-28 2026-04-05 2026-04-10 2026-04-12
"""

import json
import sys
from pathlib import Path

ENTRIES_PATH = Path(__file__).parent.parent / "data" / "processed" / "entries.jsonl"


def main() -> None:
    target_dates = sys.argv[1:]
    with ENTRIES_PATH.open() as f:
        entries = [json.loads(line) for line in f if line.strip()]

    for target in target_dates:
        matches = [e for e in entries if e["date"].startswith(target)]
        if not matches:
            print(f"{target}: no entry found")
            continue
        for e in matches:
            print(f"{target}: id={e['id']} mood={e.get('mood')} sentiment={e.get('sentiment')}")


if __name__ == "__main__":
    main()
