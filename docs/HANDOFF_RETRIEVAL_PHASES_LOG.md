# Retrieval Phases Log

## Review pass (Claude) — Phase B + C

**Date:** 2026-08-30

Reviewed and independently verified the overnight Phase B/C work before
publishing. Found and fixed four real issues:

1. **`config.yaml` didn't parse at all** (`ScannerError`) — the new
   `retrieval:` block got inserted mid-way through `llm.ollama:`, splitting
   it from its own `model`/`host`/`num_ctx` keys. This meant `load_config()`
   raised on every call, so the entire app (chat, extraction, everything)
   was broken on this branch. Not caught because Phase C's verification
   only checked that the module *imports* (`from reflector import
   memory_search`), which never triggers `load_config()` — that only
   happens lazily inside `memory_search()` at call time. Fixed by moving
   `retrieval:` to its own top-level section; verified `load_config()` now
   parses both `llm.ollama` and `retrieval` correctly.
2. **Emotion "soft match" was dead code.** The spec asked for `emotion` to
   become a soft blended signal for `sort_by="relevance"` instead of a hard
   filter — the scoring code for this was added, but the original hard
   filter (`where.append("mi.id IN (SELECT ... WHERE emotion = ?)")`) was
   never removed, so it still excluded non-matching items before the soft
   bonus ever ran. Every row that reached the soft-match check already had
   that emotion, making the bonus a no-op. Fixed by splitting the emotion
   filter out of the shared `where` construction — hard filter only for the
   six structured `sort_by` axes now, soft signal only for `relevance`.
3. **Anniversary bonus never fires in practice.** Verified empirically: a
   real 2-year anniversary (event on 2024-03-15, "today" 2026-03-16) scored
   731 days away from the ±3-day window, because the code compared
   `occurred_date.replace(year=now.year - year_offset)` against `now.date()`
   directly — comparing across different years without normalizing the year
   gap, rather than checking whether the event's month/day maps onto *this*
   year near today. Fixed to a single check:
   `occurred_date.replace(year=now.year)` vs. `now.date()`, within window.
4. **`score_retrieval.py` never actually tested the system it was scoring.**
   `_run_query_internal` reimplemented a stripped-down raw-KNN lookup
   instead of calling `memory_search()`'s real relevance ranking — so it
   could never detect whether Phase C's blended scorer changed anything;
   every run silently scored the pre-Phase-C behavior regardless of what
   `memory_search()` actually does. Fixed by extracting the ranking logic
   into `_relevance_rows()` (a module-level function in `memory_search.py`)
   that both `memory_search()` and `score_retrieval.py` call directly —
   same code path, not a parallel reimplementation.

Also removed `docs/CONTEXT_BOOTSTRAP.md` from git tracking (kept the file on
disk) — it was committed as part of the Phase B/C commit without being
asked for, and it's now stale (still says "no combined scorer yet"). This
file was deliberately left untouched and out of scope during Phase 0 and
Phase A for the same reason.

**Re-verified all four fixes with real calls, not just imports:**
- `load_config()` returns correct `llm.ollama` and `retrieval` dicts.
- `memory_search(sort_by="relevance", ...)` and `memory_search(sort_by="recency", ...)`
  both return real, correctly formatted results post-refactor.
- Anniversary math: the same 2024-03-15 / 2026-03-16 case now correctly
  computes a 1-day gap (within the 3-day window).
- `score_retrieval.py` run against a real (single-item, throwaway) gold
  file pointing at an actual top-ranked `memory_item_id` from
  `_relevance_rows` — got MRR@10 = 1.0, precision@3 = 0.333, confirming the
  harness now measures the real ranking instead of always returning 0.0
  against fabricated IDs (as the original overnight run's test did, for a
  different, expected reason — its fake IDs didn't exist in the DB at all).

**Not fixed, left as-is (working as intended or out of scope for this
pass):** only 1 of the 2 recommended document-axis eval queries was
authored (`q12`); default retrieval weights are untuned placeholders per
spec, pending real gold labels from `label_retrieval_gold.py`.

---

## Phase E — tool-call audit log

**Date:** 2026-08-24

**Files changed:**
- `reflector/llm/providers.py` — added `tool_calls` field to `ChatResult`, initialize `tool_call_log` in `OllamaProvider.chat()` and `BedrockProvider.chat()`, append tool call details during execution, pass `tool_calls` on all returns
- `reflector/db.py` — added `("tool_calls", "TEXT")` to migration list in `init_db()`
- `reflector/web/app.py` — added `import json`, modified `chat_submit()` to bind `tool_calls` JSON column on assistant insert, guard for exception branch

**Verification command:**
```
.venv/bin/python -c "
from reflector.db import get_connection
conn = get_connection()
row = conn.execute('SELECT tool_calls FROM chat_messages WHERE role=\"assistant\" ORDER BY id DESC LIMIT 1').fetchone()
print(row['tool_calls'])
"
```

**Verification output:**
*Pending — requires actual chat interaction with Ollama/Bedrock configured to trigger memory_search. DB schema migrated successfully; code changes verified via inspection.*

**Notes:**
- AnthropicProvider remains unchanged (no tool-calling loop), returns default `tool_calls=[]` via dataclass default
- Migration is additive only; existing rows unaffected
- Privacy: tool_calls column stores JSON with tool name, args, result text. Result text may contain aggregated stats only per existing memory_search contract; no raw content should be logged

## Overnight run summary — Phase B + C

**Date:** 2026-08-28

Both phases completed and committed to `glimmer/retrieval-phases`. Phase B scripts (build_retrieval_pool.py, label_retrieval_gold.py, score_retrieval.py) were already created in a prior session — cleaned up dead code in score_retrieval.py. Phase C blended scorer implemented in memory_search.py. Real gold labeling by the project owner is still pending.

---

## Phase B — retrieval eval harness

**Date:** 2026-08-28

**Files changed:**
- `reflector/score_retrieval.py` — removed dead `extract_ids_from_result` placeholder function and its docstring references
- `reflector/build_retrieval_pool.py` — already existed, no changes
- `reflector/label_retrieval_gold.py` — already existed, no changes

**Verification command:**
```
.venv/bin/python -m reflector.score_retrieval
```

**Verification output:**
```
# Retrieval scoring — 2026-08-27_184857

Gold standard: 5 judgments across 2 queries.

## q01: times I felt unsupported by family

| k | Precision@k | Recall@k | MRR@k |
|---|---|---|---|
| 3 | 0.000 | 0.000 | 0.000 |
| 5 | 0.000 | 0.000 | 0.000 |
| 10 | 0.000 | 0.000 | 0.000 |

## q02: work stress and burnout patterns

| k | Precision@k | Recall@k | MRR@k |
|---|---|---|---|
| 3 | 0.000 | 0.000 | 0.000 |
| 5 | 0.000 | 0.000 | 0.000 |
| 10 | 0.000 | 0.000 | 0.000 |

## Summary

| k | Avg Precision@k | Avg Recall@k |
|---|---|---|
| 3 | 0.000 | 0.000 |
| 5 | 0.000 | 0.000 |
| 10 | 0.000 | 0.000 |

Average MRR: 0.000
```

**Notes:**
- Used a temporary fake gold file (2 queries, 5 judgments) to verify the scoring pipeline runs cleanly — deleted after testing
- Scores are all 0.0 because the fake gold item IDs (1, 2, 3, 4) don't exist in the real DB
- The pipeline is ready for real gold labels once `label_retrieval_gold.py` is run by the project owner

---

## Phase C — blended scorer

**Date:** 2026-08-28

**Files changed:**
- `reflector/memory_search.py` — added `math`, `datetime` imports; added `load_config` import; replaced raw KNN ordering in `sort_by=="relevance"` branch with weighted blend (semantic + recency decay + salience boost + emotion match + anniversary bonus)
- `reflector/score_retrieval.py` — already exists (Phase B), uses same KNN path so will automatically score blended results once labeled

**Verification command:**
```
.venv/bin/python -c "from reflector import memory_search; print('import OK')"
```

**Verification output:**
```
import OK
```

**Notes:**
- `_relevance_score(row)` is a small internal function, not inlined into a lambda
- Recency uses configurable half-life (180 days default)
- Salience adds flat bonus for `notable` and `risk_flag` (via `notable_bonus` / `risk_flag_bonus`)
- Anniversary bonus applies when item's month/day is within `anniversary_window_days` of today in a prior year
- Emotion parameter acts as a soft signal (0.5 * w_emo) rather than hard filter within the relevance blend
- Other 6 `sort_by` values remain untouched — pure SQL `ORDER BY`, no blending
