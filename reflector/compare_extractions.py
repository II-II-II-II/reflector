"""
Side-by-side viewer for comparing extraction quality across models.

IMPORTANT — run this yourself, in your own terminal. Do not paste its
output back into a chat with a cloud-hosted assistant: it prints real
entry text next to real extracted psychological signal. This script
exists specifically so you can judge model quality locally, without
that judgment ever needing to leave your machine.

Usage:
    python -m reflector.extract --model qwen2.5:32b --ids-file data/eval/eval_ids.txt --out extractions_qwen2.5-32b.jsonl
    python -m reflector.extract --model llama3.3:70b --ids-file data/eval/eval_ids.txt --out extractions_llama3.3-70b.jsonl
    python -m reflector.compare_extractions data/eval/gold.jsonl data/processed/extractions_qwen2.5-32b.jsonl data/processed/extractions_llama3.3-70b.jsonl
"""

import json
import sys
from pathlib import Path

ENTRIES_PATH = Path(__file__).parent.parent / "data" / "processed" / "entries.jsonl"


def load_jsonl(path: Path) -> dict[str, dict]:
    with path.open() as f:
        return {json.loads(l)["id"]: json.loads(l) for l in f if l.strip()}


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m reflector.compare_extractions <file1.jsonl> [file2.jsonl ...]")
        sys.exit(1)

    entries = load_jsonl(ENTRIES_PATH)
    result_sets = {Path(name).name: load_jsonl(Path(name)) for name in sys.argv[1:]}

    common_ids = set.intersection(*(set(rs.keys()) for rs in result_sets.values()))
    if not common_ids:
        print("No entry IDs are common across all provided files.")
        sys.exit(1)

    for entry_id in sorted(common_ids):
        print("=" * 100)
        print(f"ENTRY {entry_id}  ({entries[entry_id]['date']})")
        print("-" * 100)
        print(entries[entry_id]["text"])
        print("-" * 100)
        for name, rs in result_sets.items():
            r = dict(rs[entry_id])
            r.pop("id", None)
            r.pop("date", None)
            print(f"\n[{name}]")
            print(json.dumps(r, indent=2))
        print()


if __name__ == "__main__":
    main()
