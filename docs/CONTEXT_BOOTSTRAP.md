# Reflector — Context Bootstrap

Last updated: 2026-08-21

## Project identity
Privacy-first, local-first longitudinal AI psychologist. Raw journal content never leaves machine. Extraction local, frontier opt-in for reasoning.

## Architecture layers
1. Layer 1 — Per-entry structured extraction — DONE. 1,815 entries extracted.
2. Layer 2 — Temporal aggregation — NOT STARTED
3. Layer 3 — Longitudinal synthesis — NOT STARTED
4. Layer 4 — Chat agent — LIVE with tool calling

## Data state
- `data/processed/entries.jsonl`: 1,815 entries
- `data/processed/extractions.jsonl`: 1,815 records, 0 errors
- `data/reflector.db`: `memory_items` 1,823 rows — journal_entry 1,815, assessment 8
- `memory_embeddings`: 1,823 rows, 768-dim nomic-embed-text
- Assessments: PHQ-9, GAD-7, PCL-5, ACE, Big Five, Holmes-Rahe

## Retrieval
- `memory_search` tool live in chat, agentic tool calling active
- Search axes: semantic KNN + filters/sort by emotional_intensity, sentiment_low/high, recency, notable, risk_flag, theme, emotion
- Truncation: SUMMARY_TRUNCATE_CHARS=800
- Privacy note: tool returns real journal excerpts to LLM

## Model hosting
- Extraction/embeddings: local Ollama
- Chat: swappable via config.yaml — ollama / bedrock / anthropic
- Current config provider: bedrock

## Open items
- Retrieval policy blending: no combined semantic+emotion+salience scorer yet
- Retrieval eval harness: missing
- Chat session adapter to memory_items
- Layer 2/3 aggregation/synthesis

## Key files
- `reflector/schema.py` — extraction enums
- `reflector/prompts.py` — EXTRACTION_SYSTEM_PROMPT, CHAT_SYSTEM_PROMPT
- `reflector/db.py` — SQLite schema
- `reflector/memory_search.py` — retrieval tool
- `reflector/web/app.py` — Flask UI + chat loop
- `docs/ARCHITECTURE.md`, `docs/STATUS.md`, `docs/ROADMAP.md`

## Safety
- Hardcoded crisis routing on PHQ-9 risk items
- Keyword crisis safety net on free-text chat
- No raw content printed to stdout

## How to resume
Load this file as first user message in a new session, then ask for current data state check.
