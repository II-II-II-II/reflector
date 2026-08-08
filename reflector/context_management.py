"""
Keeps the chat agent's working context bounded, the same shape as Claude
Code's own context compaction: a full-detail "hot" window of recent turns,
with everything older folded into a real, persisted, incrementally-updated
summary rather than either (a) re-sending the entire history forever
(unbounded cost, and can silently exceed a local model's num_ctx) or
(b) hard-truncating history (silent, undetectable data loss).

Privacy: the summarization pass sends real conversation content to
whichever provider is active — same trust boundary as a normal chat turn,
nothing new. This module only ever prints counts, never content.
"""

from reflector.db import get_connection

KEEP_RECENT_MESSAGES = 10  # ~5 exchanges kept verbatim, never summarized
COMPACTION_TRIGGER_TOKENS = 6000  # trigger a compaction pass once uncompacted history exceeds this

SUMMARIZE_SYSTEM_PROMPT = """You are compressing a conversation log, not participating in it.
You will be given two sections: an EARLIER SUMMARY and MORE RECENT CONVERSATION. Produce ONE new
summary that covers BOTH sections — everything in the earlier summary must still be represented in
your output, not just the recent conversation. Do not summarize only the most recent section; a
summary that drops the earlier material is wrong, no matter how concise it is. Preserve specific
facts, names, dates, emotional throughlines, and anything explicitly asked to be remembered. Do not
add commentary, advice, or evaluation — just compress everything you were given into one summary."""


def estimate_tokens(text: str) -> int:
    """Rough chars/4 heuristic — good enough for a trigger threshold, not
    meant to match any specific model's real tokenizer exactly."""
    return max(1, len(text) // 4)


def _latest_compaction(conn):
    return conn.execute(
        "SELECT id, covers_through_message_id, summary_text FROM chat_compactions ORDER BY id DESC LIMIT 1"
    ).fetchone()


def get_context(provider, model_id: str) -> tuple[str | None, list[dict], int, int]:
    """Returns (summary_text_or_None, recent_messages, extra_input_tokens, extra_output_tokens).
    extra_* account for a compaction LLM call made during this turn, if any,
    so the caller's cost tracking for this turn stays honest rather than
    hiding the summarization call's real cost."""
    conn = get_connection()
    compaction = _latest_compaction(conn)
    covers_through = compaction["covers_through_message_id"] if compaction else 0
    summary_text = compaction["summary_text"] if compaction else None

    rows = conn.execute(
        "SELECT id, role, content FROM chat_messages WHERE id > ? ORDER BY id ASC", (covers_through,)
    ).fetchall()

    budget_text = (summary_text or "") + "".join(r["content"] for r in rows)

    if estimate_tokens(budget_text) <= COMPACTION_TRIGGER_TOKENS or len(rows) <= KEEP_RECENT_MESSAGES:
        conn.close()
        return summary_text, [{"role": r["role"], "content": r["content"]} for r in rows], 0, 0

    to_compact = rows[: -KEEP_RECENT_MESSAGES]
    recent = rows[-KEEP_RECENT_MESSAGES:]

    transcript = "\n\n".join(f"{r['role']}: {r['content']}" for r in to_compact)
    prior = f"=== EARLIER SUMMARY (must still be represented in your output) ===\n{summary_text}\n\n" if summary_text else ""
    result = provider.chat([
        {"role": "system", "content": SUMMARIZE_SYSTEM_PROMPT},
        {"role": "user", "content": f"{prior}=== MORE RECENT CONVERSATION ===\n{transcript}"},
    ])

    conn.execute(
        "INSERT INTO chat_compactions (covers_through_message_id, summary_text, created_at, model_id) "
        "VALUES (?, ?, datetime('now'), ?)",
        (to_compact[-1]["id"], result.text, model_id),
    )
    conn.commit()
    conn.close()

    return (
        result.text,
        [{"role": r["role"], "content": r["content"]} for r in recent],
        result.input_tokens or 0,
        result.output_tokens or 0,
    )
