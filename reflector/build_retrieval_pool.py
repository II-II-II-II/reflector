"""
Build a pooled candidate set for retrieval eval.

For each query in data/eval/retrieval_queries.jsonl, collects:
- top-15 semantic KNN results (KNN over memory_embeddings, no sorting/limit bias)
- top-5 from each of the 6 structured sort_by axes

Assessment items (source_type='assessment') are excluded from the pool —
their summary_text is rule-derived template text ("GAD-7 taken, total 8,
Mild"), not real content worth judging retrieval relevance against.

Writes data/eval/retrieval_candidates.jsonl with one line per (query_id, memory_item_id) pair,
with metadata: query_id, memory_item_id, source_type, occurred_at, text_preview (first ~150 chars).

Privacy: only prints aggregate counts, no content.

Usage:
    python -m reflector.build_retrieval_pool
"""

import json
from pathlib import Path

import ollama
import sqlite_vec

from reflector.db import get_connection
from reflector.memory_search import memory_search

QUERIES_PATH = Path(__file__).parent.parent / "data" / "eval" / "retrieval_queries.jsonl"
OUT_PATH = Path(__file__).parent.parent / "data" / "eval" / "retrieval_candidates.jsonl"


def _semantic_knn_pool(conn, query: str, k: int = 15):
    vector = ollama.embed(model="nomic-embed-text", input=query).embeddings[0]
    rows = conn.execute(
        "SELECT memory_item_id, distance FROM memory_embeddings WHERE embedding MATCH ? AND k = ? ORDER BY distance",
        (sqlite_vec.serialize_float32(vector), k * 10),  # over-fetch then dedupe
    ).fetchall()
    candidate_ids = [r["memory_item_id"] for r in rows]
    if not candidate_ids:
        return []
    # Assessment rows (e.g. "GAD-7 taken, total 8, Mild") are rule-derived
    # template text, not real content — not meaningful to judge retrieval
    # relevance against, so excluded from the eval pool entirely.
    placeholders = ",".join("?" * len(candidate_ids))
    non_assessment = {
        r["id"] for r in conn.execute(
            f"SELECT id FROM memory_items WHERE id IN ({placeholders}) AND source_type != 'assessment'",
            candidate_ids,
        ).fetchall()
    }
    seen = set()
    ids = []
    for mid in candidate_ids:
        if mid not in non_assessment or mid in seen:
            continue
        seen.add(mid)
        ids.append(mid)
        if len(ids) >= k:
            break
    return ids


def _structured_pool(conn, sort_by: str, limit: int = 5):
    # Use memory_search internals for structured sorts — no semantic query
    # We replicate the SQL path directly to avoid semantic_query requirement
    order_sql = {
        "emotional_intensity": "mi.emotional_intensity DESC",
        "sentiment_low": "mi.sentiment_score ASC",
        "sentiment_high": "mi.sentiment_score DESC",
        "recency": "mi.occurred_at DESC",
        "notable": "mi.notable DESC, mi.occurred_at DESC",
        "risk_flag": "mi.risk_flag DESC, mi.occurred_at DESC",
    }.get(sort_by)
    if not order_sql:
        return []
    rows = conn.execute(
        f"SELECT mi.id FROM memory_items mi WHERE mi.source_type != 'assessment' ORDER BY {order_sql} LIMIT ?",
        (limit,),
    ).fetchall()
    return [r["id"] for r in rows]


def main():
    if not QUERIES_PATH.exists():
        print(f"No queries file at {QUERIES_PATH}")
        return

    queries = []
    with QUERIES_PATH.open() as f:
        for line in f:
            if line.strip():
                queries.append(json.loads(line))

    conn = get_connection()
    candidates = []

    for q in queries:
        query_id = q["id"]
        query_text = q["query"]
        # Semantic pool
        semantic_ids = _semantic_knn_pool(conn, query_text, k=15)
        # Structured pools
        structured_ids = []
        for axis in ["emotional_intensity", "sentiment_low", "sentiment_high", "recency", "notable", "risk_flag"]:
            structured_ids.extend(_structured_pool(conn, axis, limit=5))

        # Union
        pool_ids = list(dict.fromkeys(semantic_ids + structured_ids))

        # Fetch metadata
        if pool_ids:
            placeholders = ",".join("?" * len(pool_ids))
            rows = conn.execute(
                f"SELECT id, source_type, occurred_at, summary_text FROM memory_items WHERE id IN ({placeholders})",
                pool_ids,
            ).fetchall()
            meta = {r["id"]: r for r in rows}
            for mid in pool_ids:
                r = meta.get(mid)
                if not r:
                    continue
                preview = r["summary_text"][:150]
                candidates.append({
                    "query_id": query_id,
                    "memory_item_id": mid,
                    "source_type": r["source_type"],
                    "occurred_at": r["occurred_at"],
                    "text_preview": preview,
                })

    conn.close()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w") as out:
        for c in candidates:
            out.write(json.dumps(c) + "\n")

    # Aggregate stats
    per_query = {}
    for c in candidates:
        per_query.setdefault(c["query_id"], set()).add(c["memory_item_id"])

    print(f"Built retrieval pool with {len(candidates)} candidate rows")
    for qid, s in per_query.items():
        print(f"  {qid}: {len(s)} unique candidates")
    print(f"Wrote to {OUT_PATH}")


if __name__ == "__main__":
    main()
