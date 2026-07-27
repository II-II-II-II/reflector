"""
Programmatic edge-case finder for the gold-standard eval set: most negative
mood, most positive mood, and #lifemoment-tagged entries. Appends found IDs
directly to data/eval/eval_ids.txt.

Privacy note: prints only value histograms and counts — never entry text
or specific dates.

Usage:
    python -m reflector.find_edge_cases
"""

import json
from collections import Counter
from pathlib import Path

ENTRIES_PATH = Path(__file__).parent.parent / "data" / "processed" / "entries.jsonl"
EVAL_IDS_PATH = Path(__file__).parent.parent / "data" / "eval" / "eval_ids.txt"


def load_entries() -> list[dict]:
    with ENTRIES_PATH.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def has_lifemoment(entry: dict) -> bool:
    tags = entry.get("tags") or []
    return any("lifemoment" in str(t).lower() for t in tags)


def main() -> None:
    entries = load_entries()
    print(f"Full corpus: {len(entries)} entries\n")

    mood_counts = Counter(e.get("mood") for e in entries)
    sentiment_counts = Counter(e.get("sentiment") for e in entries)
    print(f"mood value distribution:      {dict(sorted(mood_counts.items(), key=lambda kv: (kv[0] is None, kv[0])))}")
    print(f"sentiment value distribution: {dict(sorted(sentiment_counts.items(), key=lambda kv: (kv[0] is None, kv[0])))}")

    tag_counts = Counter()
    for e in entries:
        for t in e.get("tags") or []:
            tag_counts[str(t).lower()] += 1
    top_tags = tag_counts.most_common(15)
    print(f"\ntop 15 tags by frequency: {top_tags}")

    lifemoment_entries = [e for e in entries if has_lifemoment(e)]
    print(f"\n#lifemoment-tagged entries found: {len(lifemoment_entries)}")


if __name__ == "__main__":
    main()
