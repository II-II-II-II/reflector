# Retrieval Phases Log

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
