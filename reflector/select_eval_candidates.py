"""
Build a stratified shortlist of candidate entries for the human-labeled
gold-standard eval set. Uses Journey's own mood/sentiment metadata (already
in entries.jsonl) to spread candidates across the emotional range and
across years, so you're not manually scrolling through 8 years of entries
to find variety.

Privacy: writes full candidate metadata (id, date, mood, sentiment, text
length — no entry text) to data/eval/candidates.jsonl for YOU to review
locally. Only prints an aggregate distribution summary to stdout.

Usage:
    python -m reflector.select_eval_candidates --n 30
    # then review data/eval/candidates.jsonl yourself (add/drop entries,
    # e.g. ones you know cover a distortion or risk-flag edge case),
    # and save final IDs (one per line) to data/eval/eval_ids.txt
"""

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

ENTRIES_PATH = Path(__file__).parent.parent / "data" / "processed" / "entries.jsonl"
OUT_PATH = Path(__file__).parent.parent / "data" / "eval" / "candidates.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=30, help="Total candidates to select")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    with ENTRIES_PATH.open() as f:
        entries = [json.loads(line) for line in f if line.strip()]

    buckets: dict[tuple, list[dict]] = defaultdict(list)
    for e in entries:
        buckets[(e.get("mood"), e["date"][:4])].append(e)

    rng = random.Random(args.seed)
    per_bucket = max(1, args.n // max(1, len(buckets)))
    selected: list[dict] = []
    for items in buckets.values():
        rng.shuffle(items)
        selected.extend(items[:per_bucket])
    rng.shuffle(selected)
    selected = selected[: args.n]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w") as out:
        for e in selected:
            out.write(
                json.dumps(
                    {
                        "id": e["id"],
                        "date": e["date"],
                        "mood": e.get("mood"),
                        "sentiment": e.get("sentiment"),
                        "favourite": e.get("favourite"),
                        "text_length": len(e["text"]),
                    }
                )
                + "\n"
            )

    mood_counts: dict = defaultdict(int)
    year_counts: dict = defaultdict(int)
    for e in selected:
        mood_counts[e.get("mood")] += 1
        year_counts[e["date"][:4]] += 1

    print(f"Selected {len(selected)} candidates -> {OUT_PATH}")
    print(f"Mood distribution: {dict(sorted(mood_counts.items(), key=lambda kv: (kv[0] is None, kv[0])))}")
    print(f"Year distribution: {dict(sorted(year_counts.items()))}")
    print(
        "\nReview data/eval/candidates.jsonl yourself (it has dates/mood, no text), "
        "add/drop entries as needed for coverage (e.g. entries you know involve a "
        "distortion or risk-flag edge case), then save final IDs (one per line) to "
        "data/eval/eval_ids.txt"
    )


if __name__ == "__main__":
    main()
