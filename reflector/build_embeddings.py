"""
Generate embeddings for every memory_item that doesn't have one yet, via
local Ollama (nomic-embed-text) — nothing leaves the machine. Resumable:
only processes memory_items missing from memory_embeddings.

Privacy: embeds summary_text (real journal content for journal_entry rows)
locally, but only ever prints counts/progress, never that content.

Usage:
    python -m reflector.build_embeddings
"""

import sys
import time

import ollama
import sqlite_vec

from reflector.db import EMBEDDING_DIM, get_connection


def build_embeddings(model: str = "nomic-embed-text") -> None:
    conn = get_connection()
    rows = conn.execute(
        """SELECT mi.id, mi.summary_text FROM memory_items mi
           LEFT JOIN memory_embeddings me ON me.memory_item_id = mi.id
           WHERE me.memory_item_id IS NULL"""
    ).fetchall()

    total = len(rows)
    print(f"{total} memory_items need embeddings (model: {model})")
    start = time.time()
    done = 0
    errors = 0

    for row in rows:
        try:
            resp = ollama.embed(model=model, input=row["summary_text"])
            vector = resp.embeddings[0]
            if len(vector) != EMBEDDING_DIM:
                raise ValueError(f"unexpected embedding dim {len(vector)} != {EMBEDDING_DIM}")
        except Exception as e:
            errors += 1
            print(f"  error on memory_item {row['id']}: {type(e).__name__}", file=sys.stderr)
            continue

        conn.execute(
            "INSERT INTO memory_embeddings (memory_item_id, embedding) VALUES (?, ?)",
            (row["id"], sqlite_vec.serialize_float32(vector)),
        )
        done += 1
        if done % 100 == 0 or done == total:
            elapsed = time.time() - start
            print(f"Embedded {done}/{total} | errors: {errors} | elapsed: {elapsed:.0f}s")
            conn.commit()

    conn.commit()
    conn.close()
    print(f"\nDone. {done} embedded, {errors} errors.")


if __name__ == "__main__":
    build_embeddings()
