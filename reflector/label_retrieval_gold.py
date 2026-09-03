"""
Interactive labeling of retrieval candidates.

RUN THIS YOURSELF, in your own terminal. It displays the full candidate text
(fetched live from the DB, same truncation the agent itself sees via
memory_search — SUMMARY_TRUNCATE_CHARS — not the short preview stored in
retrieval_candidates.jsonl, which only exists for that file's own "metadata,
not content" review convention) and asks y/n for relevance. Builds
data/eval/retrieval_gold.jsonl incrementally, Ctrl+C-safe (resumes by
skipping already-labeled pairs).

Presents candidates in round-robin blocks of BLOCK_SIZE per query (5 from
q01, 5 from q02, ..., then back to q01 for the next 5) rather than
exhausting one query before starting the next — a short session then
touches every query at least a little instead of fully covering only the
first one or two, so score_retrieval.py has something to say about all of
them even from a partial, incremental labeling session.

Usage:
    python -m reflector.label_retrieval_gold
"""

import json
import sys
from pathlib import Path

from reflector.db import get_connection
from reflector.memory_search import SUMMARY_TRUNCATE_CHARS

BLOCK_SIZE = 5

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

    # Fetch full text live from the DB — the stored text_preview is only
    # 150 chars (fine for the metadata-only candidates.jsonl file itself,
    # not enough to actually judge relevance).
    conn = get_connection()
    mids = list({c["memory_item_id"] for c in candidates})
    placeholders = ",".join("?" * len(mids))
    full_text = {}
    if mids:
        rows = conn.execute(
            f"SELECT id, summary_text FROM memory_items WHERE id IN ({placeholders})", mids
        ).fetchall()
        full_text = {r["id"]: r["summary_text"] for r in rows}
    conn.close()

    # Load already labeled
    already = set()
    if GOLD_PATH.exists():
        with GOLD_PATH.open() as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    already.add((rec["query_id"], rec["memory_item_id"]))

    # Per-query queues of not-yet-labeled candidates, in their original order
    queues = {
        qid: [c for c in items if (qid, c["memory_item_id"]) not in already]
        for qid, items in by_query.items()
    }

    # Round-robin in blocks of BLOCK_SIZE: take up to 5 from each query in
    # turn, repeat, so a session that stops partway has touched every query
    # instead of only the first one or two.
    todo = []
    qids = list(queues.keys())
    while any(queues[qid] for qid in qids):
        for qid in qids:
            block, queues[qid] = queues[qid][:BLOCK_SIZE], queues[qid][BLOCK_SIZE:]
            todo.extend((qid, c) for c in block)

    print(f"{len(todo)} candidates to label ({len(already)} already done). Ctrl+C any time to stop — progress is saved per entry.\n")

    GOLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    prev_qid = None
    with GOLD_PATH.open("a") as out:
        for i, (qid, c) in enumerate(todo, 1):
            if qid != prev_qid:
                print(f"\n>>> New block: {BLOCK_SIZE} from {qid} <<<")
                prev_qid = qid
            q = queries.get(qid, {})
            print("=" * 100)
            print(f"Query {qid}: {q.get('query', '')}")
            print(f"Axis: {q.get('axis', '')}")
            print("-" * 100)
            print(f"source: {c['source_type']} | date: {c['occurred_at'][:10]} | id: {c['memory_item_id']}")
            print("-" * 100)
            text = full_text.get(c["memory_item_id"], c["text_preview"])
            if len(text) > SUMMARY_TRUNCATE_CHARS:
                text = text[:SUMMARY_TRUNCATE_CHARS] + "… [truncated]"
            print(text)
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
