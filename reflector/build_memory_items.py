"""
Build the unified memory_items index (see docs/ARCHITECTURE.md) from the
native source tables. Rebuildable — safe to rerun any time extraction
quality improves; memory_item ids stay stable across reruns (UPSERT keyed
on source_type+source_id) so embeddings tied to those ids stay valid.

Adapters here: journal (entries+extractions) and assessment (derived by
rule from scores, no free text to extract). Chat-session adapter is a
separate, later piece — it needs its own session-level extraction pass,
not just a reshape of existing data.

Privacy: journal summary_text is real entry content — that's the point,
it's what gets embedded for semantic recall. This script only ever prints
counts, never that content, same convention as extract.py/parse_entries.py.

Usage:
    python -m reflector.build_memory_items
"""

from reflector.db import get_connection
from reflector.instruments import INSTRUMENTS


def _upsert_memory_item(conn, source_type, source_id, occurred_at, summary_text,
                         sentiment_score, emotional_intensity, notable, risk_flag):
    row = conn.execute(
        """INSERT INTO memory_items
               (source_type, source_id, occurred_at, summary_text,
                sentiment_score, emotional_intensity, notable, risk_flag)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(source_type, source_id) DO UPDATE SET
               occurred_at=excluded.occurred_at, summary_text=excluded.summary_text,
               sentiment_score=excluded.sentiment_score,
               emotional_intensity=excluded.emotional_intensity,
               notable=excluded.notable, risk_flag=excluded.risk_flag
           RETURNING id""",
        (source_type, source_id, occurred_at, summary_text,
         sentiment_score, emotional_intensity, notable, risk_flag),
    ).fetchone()
    return row["id"]


def build_journal_memory_items() -> int:
    conn = get_connection()
    rows = conn.execute(
        """SELECT e.id, e.date, e.text, x.sentiment_score, x.emotional_intensity,
                  x.notable_event, x.self_harm_flag, x.hopelessness_flag
           FROM entries e JOIN extractions x ON x.entry_id = e.id"""
    ).fetchall()

    for r in rows:
        memory_item_id = _upsert_memory_item(
            conn, "journal_entry", r["id"], r["date"], r["text"],
            r["sentiment_score"], r["emotional_intensity"], r["notable_event"],
            bool(r["self_harm_flag"] or r["hopelessness_flag"]),
        )
        conn.execute("DELETE FROM memory_item_themes WHERE memory_item_id = ?", (memory_item_id,))
        conn.execute("DELETE FROM memory_item_emotions WHERE memory_item_id = ?", (memory_item_id,))
        themes = conn.execute("SELECT theme FROM entry_themes WHERE entry_id = ?", (r["id"],)).fetchall()
        conn.executemany(
            "INSERT INTO memory_item_themes (memory_item_id, theme) VALUES (?, ?)",
            [(memory_item_id, t["theme"]) for t in themes],
        )
        emotions = conn.execute(
            "SELECT emotion, rank FROM entry_emotions WHERE entry_id = ?", (r["id"],)
        ).fetchall()
        conn.executemany(
            "INSERT INTO memory_item_emotions (memory_item_id, emotion, rank) VALUES (?, ?, ?)",
            [(memory_item_id, e["emotion"], e["rank"]) for e in emotions],
        )

    conn.commit()
    conn.close()
    return len(rows)


def build_assessment_memory_items() -> int:
    """No free text to extract from — summary_text is derived by rule from
    the score/severity, e.g. 'GAD-7 taken, total 8, Mild'."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, instrument, administered_at, total_score, severity, risk_flag FROM assessments"
    ).fetchall()

    for r in rows:
        instrument = INSTRUMENTS[r["instrument"]]
        summary_text = f"{instrument['name']} taken, total {r['total_score']}, {r['severity']}"
        _upsert_memory_item(
            conn, "assessment", str(r["id"]), r["administered_at"], summary_text,
            sentiment_score=None, emotional_intensity=None, notable=False, risk_flag=bool(r["risk_flag"]),
        )

    conn.commit()
    conn.close()
    return len(rows)


if __name__ == "__main__":
    n_journal = build_journal_memory_items()
    print(f"Built/updated {n_journal} journal memory_items")
    n_assessment = build_assessment_memory_items()
    print(f"Built/updated {n_assessment} assessment memory_items")
