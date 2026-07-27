# Reflector — Roadmap

This tracks the high-level build status of each part of the system described
in [`ARCHITECTURE.md`](ARCHITECTURE.md). It's a snapshot, not a changelog —
see commit history for day-to-day detail.

## Legend
- ✅ Done
- 🔨 In progress
- ⏳ Not started

---

### Ingestion & normalization — ✅ Done
Raw journal export parsed, HTML stripped, normalized into a consistent
per-entry schema (date, text, mood, sentiment, tags, location, photo count).

### Layer 1 — Structured extraction — 🔨 In progress
Per-entry extraction schema, prompt, and extractor built, along with a full
gold-standard human-labeled evaluation harness for comparing candidate
models against hand-labeled ground truth before trusting any model's output
at scale. Multiple local model candidates benchmarked head-to-head on
extraction accuracy (precision/recall/F1 per field, error tolerance on
numeric fields) rather than assumed from general capability.

### Layer 2 — Temporal aggregation — ⏳ Not started
Rolling up per-entry structured tags into weekly/monthly/yearly trend lines
and thematic-frequency summaries — turning thousands of individual entries
into a tractable time-series problem.

### Layer 3 — Longitudinal synthesis — ⏳ Not started
A standing, incrementally-updated profile document synthesized from the
aggregated rollups: recurring patterns, what's improved or regressed, life
events correlated with mood shifts. Depends on Layer 2.

### Layer 4 — Conversational agent — 🔨 In progress
Chat interface with persisted history and a swappable model backend
(local/self-hosted/frontier, selected via config, all behind one common
interface) is built and working end-to-end, including a keyword-based
crisis-safety net on free-text input. Still open: no grounding yet in
journal history or assessment data — that depends on Layers 2/3 and the
unified memory/retrieval layer below.

### Clinical assessment intake — 🔨 In progress
Structured self-assessment forms (PHQ-9, GAD-7, PCL-5) with timestamped
submissions and hardcoded (non-AI) crisis-resource routing on clinical risk
indicators. Still open: wiring assessment results into the conversational
agent's context.

### Unified memory / retrieval layer — ⏳ Not started
A normalized index unifying journal entries, assessments, and chat sessions
behind one retrieval interface, supporting multiple recall strategies
(semantic similarity, emotional resonance, recency/anniversary effects,
salience) rather than plain cosine-similarity RAG. Depends on Layer 1
clearing evaluation.

### Model-hosting strategy — 🔨 Ongoing decision
Evaluating local vs. self-hosted-private vs. confidential-computing vs.
frontier-API tradeoffs per layer, rather than picking one model tier for
the whole system — see the "Model-hosting tiers" section in
[`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## Why this is slow, on purpose

Nothing in this pipeline is trusted at scale until it clears an evaluation
gate first — human-labeled ground truth for extraction quality, real
end-to-end testing for the assessment and chat flows. Given the subject
matter, getting each layer right before building on top of it matters more
than moving fast.
