"""
The memory-search tool the chat agent can call mid-conversation (see
docs/ARCHITECTURE.md — "agentic, not force-fed"). Combines semantic
similarity (embed the query, KNN over memory_embeddings) with structured
filters/sort over memory_items, so "what was the most emotionally charged
thing in 2024" and "when do I mention my job" are both a single call with
different parameters, not different code paths.

Privacy: this module returns real journal content to the CALLER (the LLM,
via the tool result) — that's the intended function. It must never be used
to print that content to stdout/logs, same convention as the rest of the
pipeline.
"""

import math
from datetime import datetime

import ollama
import sqlite_vec

from reflector.config import load_config
from reflector.db import get_connection

SUMMARY_TRUNCATE_CHARS = 800

MEMORY_SEARCH_TOOL_SPEC = {
    "toolSpec": {
        "name": "memory_search",
        "description": (
            "Search the user's journal and assessment history. Use this when a question needs "
            "specific facts, events, or patterns from their past that aren't already in this "
            "conversation or the assessment scores you were given — e.g. 'what happened in 2024', "
            "'when have I felt most anxious', 'do I mention my job often'. Don't call this for "
            "things answerable from the current conversation alone."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "semantic_query": {
                        "type": "string",
                        "description": "Natural language description of what to search for, e.g. "
                        "'conflict with a family member'. Required unless sort_by is a "
                        "non-relevance ranking.",
                    },
                    "date_start": {
                        "type": "string",
                        "description": "ISO date (YYYY-MM-DD), inclusive lower bound on when it occurred.",
                    },
                    "date_end": {
                        "type": "string",
                        "description": "ISO date (YYYY-MM-DD), inclusive upper bound.",
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": [
                            "relevance", "emotional_intensity", "sentiment_low",
                            "sentiment_high", "recency", "notable", "risk_flag",
                        ],
                        "description": "'relevance' needs semantic_query. 'emotional_intensity' = "
                        "most intense first. 'sentiment_low'/'sentiment_high' = most negative/"
                        "positive first. 'recency' = most recent first. 'notable' = flagged "
                        "significant events first. 'risk_flag' = safety-risk-flagged entries first.",
                    },
                    "theme": {"type": "string", "description": "Filter to this theme, e.g. 'work', 'family', 'health'."},
                    "emotion": {"type": "string", "description": "Filter to this primary emotion."},
                    "source_type": {
                        "type": "string",
                        "enum": ["journal_entry", "assessment", "document"],
                        "description": "Filter to one source type, e.g. 'document' to search only "
                        "standing documents the user has shared (resumes, briefings, job postings) "
                        "rather than journal entries.",
                    },
                    "limit": {"type": "integer", "description": "Max results, default 5, max 10."},
                },
                "required": [],
            }
        },
    }
}


def memory_search(
    semantic_query: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    sort_by: str = "relevance",
    theme: str | None = None,
    emotion: str | None = None,
    source_type: str | None = None,
    limit: int = 5,
) -> str:
    """Returns a formatted text block for the tool result — this is what the
    model sees, not a Python object the app renders."""
    limit = max(1, min(int(limit or 5), 10))
    conn = get_connection()

    where, params = [], []
    if date_start:
        where.append("mi.occurred_at >= ?")
        params.append(date_start)
    if date_end:
        where.append("mi.occurred_at <= ?")
        params.append(date_end + "T23:59:59")
    if theme:
        where.append("mi.id IN (SELECT memory_item_id FROM memory_item_themes WHERE theme = ?)")
        params.append(theme)
    if emotion:
        where.append("mi.id IN (SELECT memory_item_id FROM memory_item_emotions WHERE emotion = ?)")
        params.append(emotion)
    if source_type:
        where.append("mi.source_type = ?")
        params.append(source_type)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    if sort_by == "relevance" or (sort_by not in {
        "emotional_intensity", "sentiment_low", "sentiment_high", "recency", "notable", "risk_flag",
    }):
        if not semantic_query:
            conn.close()
            return "Error: semantic_query is required when sort_by is 'relevance' (the default)."
        vector = ollama.embed(model="nomic-embed-text", input=semantic_query).embeddings[0]
        # Over-fetch by KNN, then apply structured filters in Python — simpler
        # and more portable than combining vec0 MATCH with arbitrary SQL joins.
        candidates = conn.execute(
            "SELECT memory_item_id, distance FROM memory_embeddings WHERE embedding MATCH ? AND k = 100 ORDER BY distance",
            (sqlite_vec.serialize_float32(vector),),
        ).fetchall()
        candidate_ids = [c["memory_item_id"] for c in candidates]
        if not candidate_ids:
            conn.close()
            return "No results."
        placeholders = ",".join("?" * len(candidate_ids))
        rows = conn.execute(
            f"SELECT mi.* FROM memory_items mi WHERE mi.id IN ({placeholders}) {('AND ' + ' AND '.join(where)) if where else ''}",
            candidate_ids + params,
        ).fetchall()
        # Blended relevance score (Phase C): semantic + recency + salience + emotion
        retrieval_cfg = load_config().get("retrieval", {})
        weights = retrieval_cfg.get("weights", {})
        w_sem = weights.get("semantic", 0.5)
        w_rec = weights.get("recency", 0.2)
        w_sal = weights.get("salience", 0.2)
        w_emo = weights.get("emotion", 0.1)
        recency_half_life = retrieval_cfg.get("recency_half_life_days", 180)
        anniversary_window = retrieval_cfg.get("anniversary_window_days", 3)
        anniversary_bonus = retrieval_cfg.get("anniversary_bonus", 0.15)
        notable_bonus = retrieval_cfg.get("notable_bonus", 0.15)
        risk_flag_bonus = retrieval_cfg.get("risk_flag_bonus", 0.15)

        distances = [c["distance"] for c in candidates]
        min_dist = min(distances)
        max_dist = max(distances)

        semantic_sims = {}
        for c in candidates:
            mid = c["memory_item_id"]
            if max_dist > min_dist:
                norm = (c["distance"] - min_dist) / (max_dist - min_dist)
                semantic_sims[mid] = 1.0 - norm
            else:
                semantic_sims[mid] = 0.5

        now = datetime.now()

        def _relevance_score(row):
            # semantic similarity (already normalized to [0, 1])
            sim = semantic_sims.get(row["id"], 0.5)

            # recency decay
            try:
                occurred_date = datetime.strptime(row["occurred_at"][:10], "%Y-%m-%d")
                days_ago = (now - occurred_date).days
            except (ValueError, OverflowError):
                days_ago = 365
            recency_decay = math.exp(-days_ago / recency_half_life)

            # salience boost
            score = sim * w_sem + recency_decay * w_rec
            if row["notable"]:
                score += notable_bonus * w_sal
            if row["risk_flag"]:
                score += risk_flag_bonus * w_sal

            # anniversary bonus
            try:
                occurred_date = datetime.strptime(row["occurred_at"][:10], "%Y-%m-%d")
                for year_offset in range(1, 10):
                    try:
                        prior_date = occurred_date.replace(year=now.year - year_offset)
                    except ValueError:
                        continue
                    if abs((prior_date.date() - now.date()).days) <= anniversary_window:
                        score += anniversary_bonus * w_sal
                        break
            except (ValueError, OverflowError):
                pass

            # emotion match — soft signal within the blend
            if emotion:
                emotion_rows = conn.execute(
                    "SELECT emotion FROM memory_item_emotions WHERE memory_item_id = ?",
                    (row["id"],),
                ).fetchall()
                if any(e["emotion"] == emotion for e in emotion_rows):
                    score += 0.5 * w_emo

            return score

        rows = sorted(rows, key=lambda r: _relevance_score(r), reverse=True)[:limit]
    else:
        order_sql = {
            "emotional_intensity": "mi.emotional_intensity DESC",
            "sentiment_low": "mi.sentiment_score ASC",
            "sentiment_high": "mi.sentiment_score DESC",
            "recency": "mi.occurred_at DESC",
            "notable": "mi.notable DESC, mi.occurred_at DESC",
            "risk_flag": "mi.risk_flag DESC, mi.occurred_at DESC",
        }[sort_by]
        rows = conn.execute(
            f"SELECT mi.* FROM memory_items mi {where_sql} ORDER BY {order_sql} LIMIT ?",
            params + [limit],
        ).fetchall()

    if not rows:
        conn.close()
        return "No results."

    blocks = []
    for r in rows:
        themes = [t["theme"] for t in conn.execute(
            "SELECT theme FROM memory_item_themes WHERE memory_item_id = ?", (r["id"],)
        ).fetchall()]
        emotions = [e["emotion"] for e in conn.execute(
            "SELECT emotion FROM memory_item_emotions WHERE memory_item_id = ? ORDER BY rank", (r["id"],)
        ).fetchall()]
        text = r["summary_text"]
        if len(text) > SUMMARY_TRUNCATE_CHARS:
            text = text[:SUMMARY_TRUNCATE_CHARS] + "… [truncated]"
        meta = [f"date: {r['occurred_at'][:10]}", f"source: {r['source_type']}"]
        if r["sentiment_score"] is not None:
            meta.append(f"sentiment: {r['sentiment_score']}")
        if r["emotional_intensity"] is not None:
            meta.append(f"intensity: {r['emotional_intensity']}")
        if themes:
            meta.append(f"themes: {', '.join(themes)}")
        if emotions:
            meta.append(f"emotions: {', '.join(emotions)}")
        if r["notable"]:
            meta.append("notable event")
        if r["risk_flag"]:
            meta.append("risk flag")
        blocks.append(f"[{' | '.join(meta)}]\n{text}")

    conn.close()
    return f"{len(rows)} result(s):\n\n" + "\n\n---\n\n".join(blocks)
