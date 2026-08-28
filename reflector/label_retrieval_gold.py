"""
Interactive labeling of retrieval candidates.

RUN THIS YOURSELF, in your own terminal. It displays candidate previews and
asks y/n for relevance. Builds data/eval/retrieval_gold.jsonl incrementally,
Ctrl+C-safe (resumes by skipping already-labeled pairs).

Usage:
    python -m reflector.label_retrieval_gold
"""

import json
import sys
from pathlib import Path

CANDIDATES_PATH = Path(__file__).parent.parent / "data" / "eval" / "retrieval_candidates.jsonl"
GOLD_PATH = Path(__file__).parent.parent / "data" / "eval" / "retrieval_gold.jsonl"
QUERIES_PATH = Path(__file__).parent.parent / "data" / "eval" / "retrieval_queries.jsonl"

# Load queries for display
queries = {}
if QUERIES_PATH.exists():
    with QUERIES_PATH.open() as f:
        for line in f:
            if line.strip():
                q = json.loads(line)
                queries[q["id"]] = q


def main():
    if not CANDIDATES_PATH.exists():
        print(f"No candidates at {CANDIDATES_PATH}. Run build_retrieval_pool first.")
        sys.exit(1)

    # Load candidates
    candidates = []
    with CANDIDATES_PATH.open() as f:
        for line in f:
            if line.strip():
                candidates.append(json.loads(line))

    # Group by query
    by_query = {}
    for c in candidates:
        by_query.setdefault(c["query_id"], []).append(c)

    # Load already labeled
    already = set()
    if GOLD_PATH.exists():
        with GOLD_PATH.open() as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    already.add((rec["query_id"], rec["memory_item_id"]))

    # Build todo list
    todo = []
    for qid, items in by_query.items():
        for c in items:
            key = (qid, c["memory_item_id"])
            if key not in already:
                todo.append((qid, c))

    print(f"{len(todo)} candidates to label ({len(already)} already done). Ctrl+C any time to stop — progress is saved per entry.\n")

    GOLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    with GOLD_PATH.open("a") as out:
        for i, (qid, c) in enumerate(todo, 1):
            q = queries.get(qid, {})
            print("=" * 100)
            print(f"Query {qid}: {q.get('query', '')}")
            print(f"Axis: {q.get('axis', '')}")
            print("-" * 100)
            print(f"source: {c['source_type']} | date: {c['occurred_at'][:10]} | id: {c['memory_item_id']}")
            print("-" * 100)
            print(c["text_preview"])
            print("-" * 100)
            while True:
                ans = input("Relevant? (y/n): ").strip().lower()
                if ans in ("y", "n", ""):
                    if ans == "":
                        ans = "n"
                    break
                print("Please enter y or n")
            relevant = ans == "y"
            rec = {
                "query_id": qid,
                "memory_item_id": c["memory_item_id"],
                "relevant": relevant,
            }
            out.write(json.dumps(rec) + "\n")
            out.flush()
            print(f"Saved ({i}/{len(todo)}).\n")

    print("Done.")


if __name__ == "__main__":
    main()
