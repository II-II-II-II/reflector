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

DB_PATH = Path(__file__).parent.parent / "data" / "reflector.db"
ENTRIES_PATH = Path(__file__).parent.parent / "data" / "processed" / "entries.jsonl"

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

-- Chat history — the single point of contact with the LLM. No RAG/profile
-- grounding wired in yet (that's Layer 4 proper, once #3/#7 exist); this
-- is just the conversation log for now.
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    crisis_flag BOOLEAN NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created ON chat_messages(created_at);
"""


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    conn.executescript(SCHEMA)
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


if __name__ == "__main__":
    init_db()
    load_entries()
