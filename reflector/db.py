"""
Unified local SQLite store — entries, Layer 1 extraction results, and
self-assessment history all live in one file. No server, no network,
single-user.

Safe to run: init/load operations here only ever move already-processed
data (entries.jsonl, extractions.jsonl) into SQLite, or print counts —
never entry content — to stdout.
"""

import json
import sqlite3
from pathlib import Path

import sqlite_vec

EMBEDDING_DIM = 768  # nomic-embed-text

DB_PATH = Path(__file__).parent.parent / "data" / "reflector.db"
ENTRIES_PATH = Path(__file__).parent.parent / "data" / "processed" / "entries.jsonl"
EXTRACTIONS_PATH = Path(__file__).parent.parent / "data" / "processed" / "extractions.jsonl"

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    text TEXT NOT NULL,
    mood INTEGER,
    sentiment INTEGER,
    tags TEXT,
    favourite BOOLEAN,
    lat REAL,
    lon REAL,
    address TEXT,
    photo_count INTEGER
);
CREATE INDEX IF NOT EXISTS idx_entries_date ON entries(date);

-- Layer 1 extraction results (schema ready now; populated once a model
-- is chosen via the gold-standard evaluation).
CREATE TABLE IF NOT EXISTS extractions (
    entry_id TEXT PRIMARY KEY REFERENCES entries(id),
    emotional_intensity INTEGER,
    sentiment_score REAL,
    notable_event BOOLEAN,
    event_category TEXT,
    self_harm_flag BOOLEAN,
    hopelessness_flag BOOLEAN,
    sleep_quality TEXT,
    exercise_mentioned BOOLEAN,
    substance_use_mentioned BOOLEAN,
    notable_detail TEXT,
    confidence REAL
);
CREATE TABLE IF NOT EXISTS entry_emotions (
    entry_id TEXT REFERENCES entries(id), emotion TEXT, rank INTEGER
);
CREATE TABLE IF NOT EXISTS entry_distortions (
    entry_id TEXT REFERENCES entries(id), distortion TEXT
);
CREATE TABLE IF NOT EXISTS entry_themes (
    entry_id TEXT REFERENCES entries(id), theme TEXT
);
CREATE TABLE IF NOT EXISTS entry_coping (
    entry_id TEXT REFERENCES entries(id), behavior TEXT
);
CREATE TABLE IF NOT EXISTS entry_relationships (
    entry_id TEXT REFERENCES entries(id), type TEXT, valence TEXT
);
CREATE TABLE IF NOT EXISTS entry_stressors (
    entry_id TEXT REFERENCES entries(id), category TEXT
);
CREATE INDEX IF NOT EXISTS idx_entry_emotions_emotion ON entry_emotions(emotion);
CREATE INDEX IF NOT EXISTS idx_entry_distortions_distortion ON entry_distortions(distortion);
CREATE INDEX IF NOT EXISTS idx_entry_themes_theme ON entry_themes(theme);

-- Self-assessment history. Every submission is its own timestamped row,
-- so scores trend over time rather than overwriting a single value.
CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instrument TEXT NOT NULL,
    administered_at TEXT NOT NULL,
    total_score INTEGER NOT NULL,
    severity TEXT,
    risk_flag BOOLEAN NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_assessments_instrument_date ON assessments(instrument, administered_at);

CREATE TABLE IF NOT EXISTS assessment_responses (
    assessment_id INTEGER NOT NULL REFERENCES assessments(id),
    item_index INTEGER NOT NULL,
    item_text TEXT NOT NULL,
    response_value INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assessment_responses_assessment ON assessment_responses(assessment_id);

-- For instruments scored as independent trait subscales (e.g. Big Five)
-- rather than one meaningful total. The parent assessments row still gets
-- a total_score/severity (NOT NULL constraint), but for these instruments
-- treat those two fields as a non-meaningful placeholder — the real result
-- lives here, per-subscale.
CREATE TABLE IF NOT EXISTS assessment_subscores (
    assessment_id INTEGER NOT NULL REFERENCES assessments(id),
    subscale TEXT NOT NULL,
    score INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assessment_subscores_assessment ON assessment_subscores(assessment_id);

-- Unified memory layer (see docs/ARCHITECTURE.md) — one normalized row per
-- journal entry / assessment / chat session, regardless of source shape.
-- Rebuildable index, not a source of truth: entries/extractions/assessments/
-- chat_messages stay the full-fidelity data; this can be dropped and
-- regenerated from them at any time as extraction quality improves.
CREATE TABLE IF NOT EXISTS memory_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,      -- 'journal_entry' | 'assessment' | 'chat_session'
    source_id TEXT NOT NULL,        -- FK back to the native record
    occurred_at TEXT NOT NULL,      -- shared timestamp — the join key across all three
    summary_text TEXT NOT NULL,     -- normalized text, what gets embedded
    sentiment_score REAL,
    emotional_intensity INTEGER,
    notable BOOLEAN,
    risk_flag BOOLEAN,
    UNIQUE(source_type, source_id)
);
CREATE INDEX IF NOT EXISTS idx_memory_items_occurred ON memory_items(occurred_at);
CREATE INDEX IF NOT EXISTS idx_memory_items_source ON memory_items(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_memory_items_notable ON memory_items(notable);
CREATE INDEX IF NOT EXISTS idx_memory_items_risk ON memory_items(risk_flag);

CREATE TABLE IF NOT EXISTS memory_item_themes (
    memory_item_id INTEGER REFERENCES memory_items(id), theme TEXT
);
CREATE INDEX IF NOT EXISTS idx_memory_item_themes_theme ON memory_item_themes(theme);

CREATE TABLE IF NOT EXISTS memory_item_emotions (
    memory_item_id INTEGER REFERENCES memory_items(id), emotion TEXT, rank INTEGER
);
CREATE INDEX IF NOT EXISTS idx_memory_item_emotions_emotion ON memory_item_emotions(emotion);

-- Chat history — the single point of contact with the LLM. No RAG/profile
-- grounding wired in yet (that's Layer 4 proper, once #3/#7 exist); this
-- is just the conversation log for now.
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    crisis_flag BOOLEAN NOT NULL DEFAULT 0,
    input_tokens INTEGER,
    output_tokens INTEGER,
    model_id TEXT,
    code_version TEXT,
    system_prompt TEXT
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created ON chat_messages(created_at);

-- Rolling conversation compaction — without this, every turn re-sends the
-- entire chat history with no bound (cost grows forever, and can silently
-- exceed a local model's num_ctx). Each row folds everything up through
-- covers_through_message_id into one summary; only messages after that id
-- get sent verbatim. See reflector/context_management.py.
CREATE TABLE IF NOT EXISTS chat_compactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    covers_through_message_id INTEGER NOT NULL,
    summary_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    model_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_chat_compactions_covers ON chat_compactions(covers_through_message_id);
"""


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def init_db() -> None:
    conn = get_connection()
    conn.executescript(SCHEMA)

    # One vector per memory_item, same primary key — separate from SCHEMA
    # since vec0 virtual tables are created via the loaded sqlite-vec
    # extension, not plain SQL DDL.
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS memory_embeddings USING "
        f"vec0(memory_item_id INTEGER PRIMARY KEY, embedding FLOAT[{EMBEDDING_DIM}])"
    )

    # Migration for chat_messages created before token/cost tracking existed.
    existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(chat_messages)")}
    for column, coltype in [
        ("input_tokens", "INTEGER"),
        ("output_tokens", "INTEGER"),
        ("model_id", "TEXT"),
        ("code_version", "TEXT"),
        ("system_prompt", "TEXT"),
    ]:
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE chat_messages ADD COLUMN {column} {coltype}")

    conn.commit()
    conn.close()


def load_entries() -> None:
    """Populate the entries table from data/processed/entries.jsonl. Idempotent."""
    if not ENTRIES_PATH.exists():
        print(f"{ENTRIES_PATH} not found — run `python -m reflector.parse_entries` first.")
        return

    conn = get_connection()
    inserted = 0
    with ENTRIES_PATH.open() as f:
        for line in f:
            if not line.strip():
                continue
            e = json.loads(line)
            conn.execute(
                """INSERT OR REPLACE INTO entries
                   (id, date, text, mood, sentiment, tags, favourite, lat, lon, address, photo_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    e["id"],
                    e["date"],
                    e["text"],
                    e.get("mood"),
                    e.get("sentiment"),
                    json.dumps(e.get("tags", [])),
                    e.get("favourite", False),
                    e.get("lat"),
                    e.get("lon"),
                    e.get("address"),
                    e.get("photo_count", 0),
                ),
            )
            inserted += 1
    conn.commit()
    conn.close()
    print(f"Loaded {inserted} entries into {DB_PATH}")


def load_extractions() -> None:
    """Populate extractions + child tables from data/processed/extractions.jsonl.
    Idempotent — child rows are cleared and re-inserted per entry on rerun."""
    if not EXTRACTIONS_PATH.exists():
        print(f"{EXTRACTIONS_PATH} not found — run `python -m reflector.extract` first.")
        return

    conn = get_connection()
    inserted = 0
    with EXTRACTIONS_PATH.open() as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            entry_id = d["id"]
            physical_health = d.get("physical_health", {})
            risk_flags = d.get("risk_flags", {})

            conn.execute(
                """INSERT OR REPLACE INTO extractions
                   (entry_id, emotional_intensity, sentiment_score, notable_event, event_category,
                    self_harm_flag, hopelessness_flag, sleep_quality, exercise_mentioned,
                    substance_use_mentioned, notable_detail, confidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry_id,
                    d.get("emotional_intensity"),
                    d.get("sentiment_score"),
                    d.get("notable_event"),
                    d.get("event_category"),
                    risk_flags.get("self_harm_language"),
                    risk_flags.get("hopelessness_language"),
                    physical_health.get("sleep_quality"),
                    physical_health.get("exercise_mentioned"),
                    physical_health.get("substance_use_mentioned"),
                    d.get("notable_detail"),
                    d.get("confidence"),
                ),
            )

            for table in (
                "entry_emotions", "entry_distortions", "entry_themes",
                "entry_coping", "entry_relationships", "entry_stressors",
            ):
                conn.execute(f"DELETE FROM {table} WHERE entry_id = ?", (entry_id,))

            conn.executemany(
                "INSERT INTO entry_emotions (entry_id, emotion, rank) VALUES (?, ?, ?)",
                [(entry_id, e, i) for i, e in enumerate(d.get("primary_emotions", []))],
            )
            conn.executemany(
                "INSERT INTO entry_distortions (entry_id, distortion) VALUES (?, ?)",
                [(entry_id, dist) for dist in d.get("cognitive_distortions", [])],
            )
            conn.executemany(
                "INSERT INTO entry_themes (entry_id, theme) VALUES (?, ?)",
                [(entry_id, t) for t in d.get("themes", [])],
            )
            conn.executemany(
                "INSERT INTO entry_coping (entry_id, behavior) VALUES (?, ?)",
                [(entry_id, b) for b in d.get("coping_behaviors", [])],
            )
            conn.executemany(
                "INSERT INTO entry_relationships (entry_id, type, valence) VALUES (?, ?, ?)",
                [(entry_id, r.get("type"), r.get("valence")) for r in d.get("relationships_mentioned", [])],
            )
            conn.executemany(
                "INSERT INTO entry_stressors (entry_id, category) VALUES (?, ?)",
                [(entry_id, s.get("category")) for s in d.get("stressors", [])],
            )
            inserted += 1
    conn.commit()
    conn.close()
    print(f"Loaded {inserted} extractions into {DB_PATH}")


if __name__ == "__main__":
    init_db()
    load_entries()
    load_extractions()
