# Reflector — Retrieval Maturity Handoff (Phases E, B, C)

**Read this whole file before touching anything.** This hands off the
remainder of an already-approved plan to a different coding agent so the
project owner can stay token-light with their primary assistant this week.
Phases 0 (doc sync) and A (document adapter) are DONE, verified, and will be
committed as the baseline you branch from. Your job is Phases E, B, and C
only — described in full detail below. Do not re-derive scope from
`docs/ARCHITECTURE.md` or invent additional work; everything you need is in
this file.

## Ground rules

1. **Work on branch `glimmer/retrieval-phases`.** It's created off the
   commit that includes Phase 0 + Phase A. Do not push, do not merge to
   `main`. Another Claude session will review and merge later.
2. **One phase at a time, in this exact order: E → B → C.** After finishing
   a phase and its verification step, STOP. Append a completion note to
   `docs/HANDOFF_RETRIEVAL_PHASES_LOG.md` (create it on your first phase)
   with: files changed, the exact verification command(s) you ran, and their
   real output pasted in full — not summarized. Then wait; don't
   auto-continue into the next phase in the same sitting unless told to.
3. **If a spec below conflicts with what you actually find in the code, or a
   verification step fails and you can't determine why after real
   investigation — STOP and write down exactly what you found instead of
   guessing past it.** A wrong guess that looks plausible is worse than an
   honest "stuck here, here's what I saw." This will be read and checked
   line-by-line before anything merges.
4. **Match existing conventions exactly** (see below) rather than
   introducing your own style, abstractions, or error handling. This is a
   small, deliberately unabstracted codebase — three similar lines beat a
   premature helper.
5. **Privacy discipline is non-negotiable**: no script may ever print raw
   journal/assessment/document content to stdout or a log file — only
   counts, ids, and aggregate stats. Every existing script in this repo
   follows this; grep any of them (`extract.py`, `build_memory_items.py`,
   `memory_search.py`) if unsure what "aggregate only" looks like in
   practice.

## Environment

- Use `.venv/bin/python`, never bare `python`/`python3`. The venv has
  `sqlite-vec`, `ollama`, `flask`, etc. Using the wrong interpreter fails
  with `AttributeError: 'sqlite3.Connection' object has no attribute
  'enable_load_extension'` — that error means wrong interpreter, not a code
  bug, don't try to fix it in code.
- Local Ollama must be running (`ollama serve`) for embeddings
  (`nomic-embed-text`) and any local-model calls.
- Database: `data/reflector.db` (gitignored, contains the real personal
  data). Schema lives in `reflector/db.py`.

## Conventions to match

- DB access: `reflector.db.get_connection()` → `sqlite3.Connection` with
  `sqlite_vec` loaded and `row_factory = sqlite3.Row` (dict-like row access,
  e.g. `row["field"]`).
- New tables/columns go in `reflector/db.py`'s `SCHEMA` string / `init_db()`.
  Column migrations use the existing detect-then-`ALTER` pattern — see
  `init_db()`, the `existing_columns = {row["name"] for row in
  conn.execute("PRAGMA table_info(...)")}` block, and mirror it exactly for
  any new column.
- Docstrings: short module-level docstring explaining *why* the file exists
  and any privacy implication, not what each line does. No inline comments
  on obvious code — only on genuinely non-obvious constraints.
- Every standalone script has a `Usage:` line in its docstring and an
  `if __name__ == "__main__":` entry point, matching
  `select_eval_candidates.py` / `label_gold.py` / `score_extractions.py`.

## Current state — already built, do not rebuild

- `memory_items` / `memory_item_themes` / `memory_item_emotions` /
  `memory_embeddings` tables exist in `reflector/db.py`.
- `reflector/build_memory_items.py` has three working adapters:
  `build_journal_memory_items()`, `build_assessment_memory_items()`,
  `build_document_memory_items()` (the last one is what Phase A just added —
  scans `data/documents/`, upserts by `(source_type, source_id)`, deletes
  the stale embedding row on content change).
- `reflector/build_embeddings.py` — resumable, only embeds rows missing from
  `memory_embeddings`.
- `reflector/memory_search.py` — the live retrieval tool, called by the chat
  agent via tool-calling. Signature:
  `memory_search(semantic_query=None, date_start=None, date_end=None,
  sort_by="relevance", theme=None, emotion=None, source_type=None,
  limit=5) -> str`. `sort_by="relevance"` embeds the query and does KNN over
  `memory_embeddings` (`k=100`), then joins back to `memory_items` and
  applies structured filters in Python. The other six `sort_by` values
  (`emotional_intensity`, `sentiment_low`, `sentiment_high`, `recency`,
  `notable`, `risk_flag`) are pure SQL `ORDER BY`, no embedding involved.
- `reflector/llm/providers.py` — full current contents relevant to Phase E:

  ```python
  @dataclass
  class ChatResult:
      text: str
      input_tokens: int | None = None
      output_tokens: int | None = None
  ```

  Three providers, each with `chat(messages, tools=None,
  tool_executor=None) -> ChatResult`:
  - `OllamaProvider.chat()` — loop up to `MAX_TOOL_ITERATIONS = 5`. Tool
    calls come back as `response.message.tool_calls`, each with
    `.function.name` / `.function.arguments`. Result is appended to
    `conversation` as `{"role": "tool", "content": result_text,
    "tool_name": tool_call.function.name}`.
  - `BedrockProvider.chat()` — loop up to `MAX_TOOL_ITERATIONS = 5`. Tool
    calls come back as `block["toolUse"]` (with `["name"]`, `["input"]`,
    `["toolUseId"]`) inside `response["output"]["message"]["content"]`.
    Result appended as a `toolResult` block.
  - `AnthropicProvider.chat()` — no tool-calling loop implemented yet (out
    of scope for Phase E — leave it as-is, just add the field to
    `ChatResult`, an empty list is correct for this provider).
- `reflector/web/app.py`, `chat_submit()` — builds `messages`, calls
  `provider.chat(messages, tools=[MEMORY_SEARCH_TOOL_SPEC],
  tool_executor={"memory_search": memory_search})`, persists `system_prompt`
  as a snapshot string into `chat_messages` on the assistant row.
- Eval trio for extraction quality (Phase B mirrors this exactly, see
  below): `reflector/select_eval_candidates.py` → `reflector/label_gold.py`
  → `reflector/score_extractions.py`, with `data/eval/gold.jsonl` as the
  hand-labeled ground truth.

---

## Phase E — tool-call audit log

**Problem:** `chat_messages.system_prompt` captures the standing context per
turn, but the actual `memory_search` calls made *during* a turn (query args,
retrieved text) are discarded once `ChatResult` is returned. No way to
inspect after the fact what the agent actually searched for or got back.

**Changes:**

1. `reflector/llm/providers.py` — add to `ChatResult`:
   ```python
   from dataclasses import dataclass, field

   @dataclass
   class ChatResult:
       text: str
       input_tokens: int | None = None
       output_tokens: int | None = None
       tool_calls: list[dict] = field(default_factory=list)
   ```
   In `OllamaProvider.chat()`: inside the `for tool_call in
   response.message.tool_calls:` loop, after computing `result_text`,
   append `{"tool": tool_call.function.name, "args":
   tool_call.function.arguments, "result": result_text}` to a local
   `tool_call_log` list (initialize `tool_call_log = []` before the main
   `for _ in range(...)` loop). Pass `tool_calls=tool_call_log` on every
   `ChatResult(...)` return in this method (both the success return and the
   iteration-limit-reached return).

   In `BedrockProvider.chat()`: same pattern — inside the `for block in
   assistant_message["content"]:` loop, after computing `result_text`,
   append `{"tool": tool_use["name"], "args": tool_use["input"], "result":
   result_text}` to a local `tool_call_log` list (init before the main loop).
   Pass `tool_calls=tool_call_log` on both `ChatResult(...)` returns.

   In `AnthropicProvider.chat()`: no loop exists, just pass `tool_calls=[]`
   (or omit it — the dataclass default already gives `[]`).

2. `reflector/db.py` — add `("tool_calls", "TEXT")` to the existing
   migration list in `init_db()` (the same list containing `input_tokens`,
   `output_tokens`, `model_id`, `code_version`, `system_prompt`). Do not
   create a new table for this — it's one JSON-serialized column on
   `chat_messages`, same tier as `system_prompt`.

3. `reflector/web/app.py`, `chat_submit()` — where the assistant row is
   inserted (the `conn.execute("INSERT INTO chat_messages ...")` after the
   `try/except` around `provider.chat(...)`), add `tool_calls` to the column
   list and bind `json.dumps(result.tool_calls)` (guard for the `except`
   branch, where `result` doesn't exist — bind `"[]"` there). Add `import
   json` at the top of the file if not already present.

**Verification:** with Ollama or Bedrock configured (check `config.yaml`,
don't change the active provider), send a chat message that should trigger
`memory_search` (e.g. "what have I written about work stress"). After it
responds, query the DB directly:
```
.venv/bin/python -c "
from reflector.db import get_connection
conn = get_connection()
row = conn.execute('SELECT tool_calls FROM chat_messages WHERE role=\"assistant\" ORDER BY id DESC LIMIT 1').fetchone()
print(row['tool_calls'])
"
```
Confirm the output is real JSON containing the actual query args and a
non-empty result string (not `"[]"`, not `null`, not truncated/malformed
JSON). Paste this real output into the log file as your Phase E evidence.

---

## Phase B — retrieval eval harness

**Problem:** there's a gold-standard eval harness for extraction quality
(`select_eval_candidates.py` → `label_gold.py` → `score_extractions.py`) but
none for retrieval quality. Before Phase C changes the scoring algorithm,
there needs to be a way to measure whether a change is actually an
improvement.

Mirror the extraction trio's shape and conventions exactly — same
docstring style, same "prints aggregate stats only" discipline, same
Ctrl+C-safe incremental-save pattern in the labeling script (see
`label_gold.py`'s `already = set(...)` / append-per-record loop).

**Files to create:**

1. **`data/eval/retrieval_queries.jsonl`** — you write this by hand (as the
   agent, generate a reasonable draft; the project owner may edit it later).
   12–15 lines, each `{"id": "q01", "query": "<natural language query>",
   "axis": "semantic|emotion|recency|salience|document"}`. Spread across:
   - ~5 semantic ("Ideas") — things findable by meaning, e.g. "times I felt
     unsupported by family"
   - ~3 emotion-axis — e.g. "when have I felt most anxious"
   - ~3 recency/anniversary ("Times") — e.g. "what happened around this time
     last year" (use a real relative date, not a placeholder)
   - ~2 salience — notable/risk-flagged moments, e.g. "the most significant
     thing that happened to me"
   - ~2 document queries — e.g. "what does my resume say about my most
     recent job" (only valid once Phase A's document adapter has real
     content indexed, which it does — `REFLECTOR_HANDOFF.md` is in there)

2. **`reflector/build_retrieval_pool.py`** (new) — for each query in
   `retrieval_queries.jsonl`, builds a *pooled* candidate set: union of the
   top-15 semantic KNN results (call `memory_search` internals directly, or
   replicate the KNN query — do NOT just call the public `memory_search()`
   with `sort_by="relevance"` alone, since that already applies the current
   algorithm's own ranking/limit and would bias the pool toward whatever
   you're trying to evaluate) plus the top-5 from each of the 6 structured
   `sort_by` axes. Dedupe by `memory_item_id`. Output format mirrors
   `select_eval_candidates.py`'s `candidates.jsonl`: writes
   `data/eval/retrieval_candidates.jsonl`, one line per (query_id,
   memory_item_id) pair, with `{"query_id", "memory_item_id", "source_type",
   "occurred_at", "text_preview"}` where `text_preview` is the first ~150
   chars only (not full content — this file may get reviewed/shared, follow
   the same "metadata not content" pattern as `candidates.jsonl`). Print
   only aggregate counts to stdout (candidates per query, total).

3. **`reflector/label_retrieval_gold.py`** (new, mirrors `label_gold.py`) —
   **the project owner runs this themselves, in their own terminal, NOT
   you.** For each query, show the pooled candidates (using `text_preview`
   plus enough identifying metadata to judge relevance — date, source_type)
   and prompt y/n relevant, saving incrementally to
   `data/eval/retrieval_gold.jsonl` as `{"query_id", "memory_item_id",
   "relevant": true/false}`, Ctrl+C-safe (resume by skipping
   already-labeled `(query_id, memory_item_id)` pairs, same pattern as
   `label_gold.py`'s `already` set). You (the agent) should build and
   syntax-check this script, but do not run it to produce fake/placeholder
   gold data — that would corrupt the eval set. Leave `retrieval_gold.jsonl`
   absent/empty for the project owner to populate.

4. **`reflector/score_retrieval.py`** (new, mirrors `score_extractions.py`)
   — given `data/eval/retrieval_gold.jsonl` and a retrieval config to test,
   runs each query's actual `memory_search()` call (or a variant, once Phase
   C adds config-driven weights) and computes precision@k, recall@k, and MRR
   against the gold relevance judgments, for k ∈ {3, 5, 10}. Writes a
   markdown report to `data/eval/` (timestamped filename, same pattern as
   `score_extractions.py`'s `scores_<timestamp>.md`), prints the same report
   to stdout.

**Verification:** you cannot fully verify this phase yourself — the real
gold-standard labels don't exist until the project owner runs
`label_retrieval_gold.py`. Your verification is: (a) `build_retrieval_pool.py`
runs cleanly against the real DB and produces a non-trivial candidate pool
per query (print and log the counts), (b) `score_retrieval.py` runs cleanly
against a small hand-written *fake* gold file you create temporarily for
testing only (e.g. 2 queries, a few made-up relevant/not-relevant labels)
to confirm the precision/recall/MRR math is correct — delete that fake file
before finishing the phase, do not leave it in place. State clearly in your
log entry that real gold labeling is a pending human step, not something
you completed.

---

## Phase C — blended scorer

**Only start this after Phase B's harness exists** (you need something to
measure improvement against, even if the project owner hasn't finished
labeling yet — you can still verify the code runs and produces sane
relative rankings).

Implements the "Ideas/Emotions/Times/Salience" blended-recall design
referenced in `docs/ARCHITECTURE.md`. Applies ONLY to
`memory_search(sort_by="relevance")` (the default / semantic path) — the six
explicit single-axis sorts (`recency`, `notable`, etc.) stay untouched
exactly as they are; an agent that explicitly asked for `sort_by=recency`
wants pure recency, not a blend.

**Changes:**

1. `config.yaml` — add a new top-level `retrieval:` section:
   ```yaml
   retrieval:
     weights:
       semantic: 0.5
       recency: 0.2
       salience: 0.2
       emotion: 0.1
     recency_half_life_days: 180
     anniversary_window_days: 3
     anniversary_bonus: 0.15
     notable_bonus: 0.15
     risk_flag_bonus: 0.15
   ```
   (These starting numbers are reasonable defaults, not tuned — Phase C's
   verification step is where they get tuned against real data, once real
   gold labels exist. Load via the existing `reflector.config.load_config()`
   pattern — check `reflector/config.py` for how other sections are read.)

2. `reflector/memory_search.py` — in the `sort_by == "relevance"` branch,
   after fetching the k=100 KNN pool and joining to `memory_items` (the
   existing code up through building `rows`), replace the final
   `sorted(rows, key=lambda r: order[r["id"]])[:limit]` line with a weighted
   score instead of raw KNN order:
   - `semantic_sim`: min-max normalize `1 - distance` (or however
     `sqlite-vec` distance is oriented — verify empirically: lower distance
     should mean higher similarity; check this before assuming) across the
     pool, so it's in [0, 1].
   - `recency_decay`: `exp(-days_ago / recency_half_life_days)` where
     `days_ago` is computed from `occurred_at` vs. now. Add
     `anniversary_bonus` (flat, not multiplied) when `occurred_at`'s
     month/day falls within `anniversary_window_days` of today's month/day
     in a prior year.
   - `salience_boost`: add `notable_bonus` if `mi.notable`, add
     `risk_flag_bonus` if `mi.risk_flag`. This is a deliberate, visible
     policy choice already made by the project — risk-flagged history
     should be more findable when relevant, not hidden. Don't second-guess
     or soften this.
   - `emotion_match`: if the caller passed `emotion`, give partial credit
     (e.g. `0.5` if the item has that emotion anywhere in its
     `memory_item_emotions`, ranked or not) instead of the current hard
     filter-out behavior — this makes `emotion` a soft signal within the
     blend rather than an exclusion filter, when `sort_by="relevance"`.
     (Note: this changes existing behavior for callers combining `emotion`
     + `sort_by="relevance"` — the hard filter still applies for the other
     six `sort_by` values, which are out of scope here.)
   - Final score = weighted sum using the config weights. Sort by score
     descending, take `limit`.
   - Keep this readable as a small pure function, e.g. `_relevance_score(row,
     semantic_sim, config) -> float`, not inlined into a giant lambda.

**Verification:** re-run `score_retrieval.py` (from Phase B) against
whatever gold labels exist at that point — if the project owner hasn't
finished labeling yet, verify instead with a manual sanity check: run a
query where you can reason about the expected top result (e.g. a
risk-flagged or notable entry that should now rank higher than before under
the same semantic query), confirm the ranking actually shifted the way the
weights predict, and log the before/after result order. Do not tune the
default weights further without real scored data — leave the defaults from
step 1 in place unless the log shows an obvious, clearly-reasoned fix (e.g.
a bug, not a taste adjustment).

---

## Explicitly out of scope — do not build

- **Chat-session adapter** (a fourth `memory_items` source for conversation
  history). No real chat history exists yet to index meaningfully — this
  was deliberately deferred by the project owner.
- Any change to Phase 0/A files beyond what's specified above (i.e. don't
  touch `build_document_memory_items()`'s core logic, `documents_context()`,
  or the doc-sync content in `docs/STATUS.md`/`docs/ARCHITECTURE.md`).
- Anything involving the `anthropic` or real user-facing chat persona
  content — this handoff is pure infrastructure/build work, not a chance to
  revise `CHAT_SYSTEM_PROMPT` or persona behavior.

## Reporting back

After each phase: append to `docs/HANDOFF_RETRIEVAL_PHASES_LOG.md` (create
on first use) — files changed, exact verification commands run, their real
output pasted in full, and anything uncertain or skipped. Be concrete, not
narrative — this is what gets checked against the spec above before merge,
not read as a status update.
