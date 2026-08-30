"""
Score retrieval quality against hand-labeled gold.

Given data/eval/retrieval_gold.jsonl and a retrieval config to test,
runs each query's actual memory_search() call and computes precision@k,
recall@k, and MRR against the gold relevance judgments, for k in {3,5,10}.

Writes a markdown report to data/eval/ (timestamped filename, same pattern as
score_extractions.py's scores_<timestamp>.md), prints the same report to stdout.

Privacy: outputs only aggregate stats, never entry content.

Usage:
    python -m reflector.score_retrieval
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from reflector.memory_search import memory_search
from reflector.config import load_config

GOLD_PATH = Path(__file__).parent.parent / "data" / "eval" / "retrieval_gold.jsonl"
QUERIES_PATH = Path(__file__).parent.parent / "data" / "eval" / "retrieval_queries.jsonl"
EVAL_DIR = Path(__file__).parent.parent / "data" / "eval"


def load_gold(path):
    gold = {}
    with open(path) as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                qid = rec["query_id"]
                mid = rec["memory_item_id"]
                gold.setdefault(qid, {})[mid] = rec["relevant"]
    return gold


def load_queries(path):
    queries = {}
    with open(path) as f:
        for line in f:
            if line.strip():
                q = json.loads(line)
                queries[q["id"]] = q
    return queries


def _run_query_internal(query_text: str, limit: int = 10):
    """Runs the SAME ranking function memory_search() itself calls
    (_relevance_rows — semantic + recency + salience + emotion blend, Phase
    C), so this measures what the agent would actually retrieve, not a
    separate reimplementation. limit=10 matches memory_search()'s own max
    limit, covering every k this script tests (3/5/10) with one real call."""
    from reflector.db import get_connection
    from reflector.memory_search import _relevance_rows

    conn = get_connection()
    rows = _relevance_rows(conn, query_text, where=[], params=[], emotion=None, limit=limit)
    ids = [r["id"] for r in rows]
    conn.close()
    return ids


def precision_recall_at_k(gold_set, pred_ids, k):
    pred_k = pred_ids[:k]
    if not gold_set:
        return 1.0 if not pred_k else 0.0, 1.0
    tp = len(set(pred_k) & gold_set)
    precision = tp / k if k > 0 else 0.0
    recall = tp / len(gold_set) if gold_set else 0.0
    return precision, recall


def mrr_at_k(gold_set, pred_ids, k):
    if not gold_set:
        return 1.0
    for i, pid in enumerate(pred_ids[:k], 1):
        if pid in gold_set:
            return 1.0 / i
    return 0.0


def main():
    if not GOLD_PATH.exists():
        print(f"No gold file at {GOLD_PATH}. Run label_retrieval_gold first or create a fake gold file for testing.")
        sys.exit(1)

    gold = load_gold(GOLD_PATH)
    queries = load_queries(QUERIES_PATH)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    report = [f"# Retrieval scoring — {timestamp}", "", f"Gold standard: {sum(len(v) for v in gold.values())} judgments across {len(gold)} queries.", ""]

    ks = [3, 5, 10]
    all_precisions = {k: [] for k in ks}
    all_recalls = {k: [] for k in ks}
    all_mrrs = []

    for qid, qinfo in queries.items():
        query_text = qinfo["query"]
        gold_set = {mid for mid, rel in gold.get(qid, {}).items() if rel}
        if not gold_set:
            # Skip queries without gold labels
            continue

        pred_ids = _run_query_internal(query_text)

        row = [f"## {qid}: {query_text}", ""]
        row.append("| k | Precision@k | Recall@k | MRR@k |")
        row.append("|---|---|---|---|")
        for k in ks:
            p, r = precision_recall_at_k(gold_set, pred_ids, k)
            m = mrr_at_k(gold_set, pred_ids, k)
            all_precisions[k].append(p)
            all_recalls[k].append(r)
            all_mrrs.append(m)
            row.append(f"| {k} | {p:.3f} | {r:.3f} | {m:.3f} |")
        row.append("")
        report.extend(row)

    # Summary
    report.append("## Summary")
    report.append("")
    report.append("| k | Avg Precision@k | Avg Recall@k |")
    report.append("|---|---|---|")
    for k in ks:
        avg_p = sum(all_precisions[k]) / len(all_precisions[k]) if all_precisions[k] else 0.0
        avg_r = sum(all_recalls[k]) / len(all_recalls[k]) if all_recalls[k] else 0.0
        report.append(f"| {k} | {avg_p:.3f} | {avg_r:.3f} |")
    if all_mrrs:
        avg_mrr = sum(all_mrrs) / len(all_mrrs)
        report.append(f"")
        report.append(f"Average MRR: {avg_mrr:.3f}")
    report.append("")

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EVAL_DIR / f"retrieval_scores_{timestamp}.md"
    out_path.write_text("\n".join(report))
    print("\n".join(report))
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
