"""
One-off: append the 4 user-verified emotional-extreme entries plus 2
#lifemoment-tagged entries to data/eval/eval_ids.txt.

Privacy note: prints only counts, never entry content.
"""

import json
from pathlib import Path

ENTRIES_PATH = Path(__file__).parent.parent / "data" / "processed" / "entries.jsonl"
EVAL_IDS_PATH = Path(__file__).parent.parent / "data" / "eval" / "eval_ids.txt"

# User-verified calibration entries (2026-06-28, 2026-04-12, 2026-04-10, 2026-04-05)
KNOWN_IDS = [
    "1782698550411-8clqw0bi4tch8o8u",
    "1776049019161-t2t2gwhqp6bzvgl3",
    "1775874213576-tswogsw1ft24dkxs",
    "1775442633273-ebuhhvmsokfld6cu",
]


def has_lifemoment(entry: dict) -> bool:
    tags = entry.get("tags") or []
    return any("lifemoment" in str(t).lower() for t in tags)


def main() -> None:
    with ENTRIES_PATH.open() as f:
        entries = [json.loads(line) for line in f if line.strip()]

    lifemoment_entries = [e for e in entries if has_lifemoment(e)]
    picked_lifemoment = [e["id"] for e in lifemoment_entries[:2]]

    new_ids = KNOWN_IDS + picked_lifemoment

    existing_ids = set()
    if EVAL_IDS_PATH.exists():
        existing_ids = {line.strip() for line in EVAL_IDS_PATH.read_text().splitlines() if line.strip()}

    added = [i for i in new_ids if i not in existing_ids]
    with EVAL_IDS_PATH.open("a") as f:
        for i in added:
            f.write(i + "\n")

    print(f"Added {len(added)} new IDs (4 calibration entries + {len(picked_lifemoment)} lifemoment-tagged)")
    print(f"Skipped {len(new_ids) - len(added)} already present")
    print(f"eval_ids.txt total: {len(existing_ids) + len(added)} entries")


if __name__ == "__main__":
    main()
