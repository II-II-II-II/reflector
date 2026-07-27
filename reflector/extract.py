"""
Layer 1: run every normalized entry through a local LLM to produce
structured, schema-constrained extraction (see schema.py).

Privacy note: this script processes real journal content locally via
Ollama. It must never print entry content OR extracted field values to
stdout — only counts, timing, and confidence stats — since anything
printed here can end up in a Claude Code tool result. Per-entry results
live only in data/processed/extractions.jsonl (gitignored), for the user
to inspect locally.

Usage:
    python -m reflector.extract [--model qwen3.6:27b] [--limit N]
    python -m reflector.extract --model qwen2.5:32b --ids-file data/eval/eval_ids.txt --out extractions_qwen2.5-32b.jsonl
"""

import argparse
import json
import sys
import time
from pathlib import Path

import ollama
from pydantic import ValidationError

from reflector.prompts import EXTRACTION_SYSTEM_PROMPT
from reflector.schema import EntryExtraction

ENTRIES_PATH = Path(__file__).parent.parent / "data" / "processed" / "entries.jsonl"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"

DEFAULT_MODEL = "qwen3.6:27b"


def load_entries(ids_file: str | None) -> list[dict]:
    if not ENTRIES_PATH.exists():
        print(f"{ENTRIES_PATH} not found — run `python -m reflector.parse_entries` first.")
        sys.exit(1)
    with ENTRIES_PATH.open() as f:
        entries = [json.loads(line) for line in f if line.strip()]
    if ids_file:
        wanted = {line.strip() for line in Path(ids_file).read_text().splitlines() if line.strip()}
        entries = [e for e in entries if e["id"] in wanted]
    return entries


def already_processed_ids(out_path: Path) -> set[str]:
    if not out_path.exists():
        return set()
    ids = set()
    with out_path.open() as f:
        for line in f:
            if line.strip():
                ids.add(json.loads(line)["id"])
    return ids


def extract_one(entry: dict, model: str, think, num_ctx: int) -> EntryExtraction:
    kwargs = dict(
        model=model,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": entry["text"]},
        ],
        format=EntryExtraction.model_json_schema(),
        options={"temperature": 0, "num_ctx": num_ctx},
    )
    if think is not None:
        kwargs["think"] = think
    response = ollama.chat(**kwargs)
    return EntryExtraction.model_validate_json(response.message.content)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int, default=None, help="Process at most N new entries (for testing).")
    parser.add_argument("--ids-file", default=None, help="Restrict to entry IDs listed in this file, one per line.")
    parser.add_argument("--out", default="extractions.jsonl", help="Output filename, relative to data/processed/.")
    parser.add_argument("--think", default=None, help="Ollama think param: true/false/low/medium/high.")
    parser.add_argument(
        "--num-ctx",
        type=int,
        default=8192,
        help="Context window size. Ollama's model defaults (up to 131K) massively over-allocate KV "
        "cache memory for our short entries — override explicitly rather than trusting the default.",
    )
    args = parser.parse_args()

    think = args.think
    if think in ("true", "false"):
        think = think == "true"

    out_path = PROCESSED_DIR / args.out

    entries = load_entries(args.ids_file)
    done_ids = already_processed_ids(out_path)
    todo = [e for e in entries if e["id"] not in done_ids]
    if args.limit:
        todo = todo[: args.limit]

    print(f"Total entries: {len(entries)} | already done: {len(done_ids)} | queued this run: {len(todo)}")
    print(f"Model: {args.model} | think: {think} | num_ctx: {args.num_ctx} | out: {out_path}\n")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    processed = 0
    errors = 0
    confidences: list[float] = []
    start = time.time()

    with out_path.open("a") as out:
        for entry in todo:
            try:
                result = extract_one(entry, args.model, think, args.num_ctx)
            except (ValidationError, ollama.ResponseError, json.JSONDecodeError):
                errors += 1
                continue

            record = {"id": entry["id"], "date": entry["date"], **result.model_dump(mode="json")}
            out.write(json.dumps(record) + "\n")
            out.flush()
            processed += 1
            confidences.append(result.confidence)

            if processed % 10 == 0 or processed == len(todo):
                elapsed = time.time() - start
                avg_conf = sum(confidences) / len(confidences)
                print(
                    f"Processed {processed}/{len(todo)} | errors: {errors} | "
                    f"avg confidence: {avg_conf:.2f} | elapsed: {elapsed:.0f}s"
                )

    print(f"\nDone. {processed} extracted, {errors} errors, output at {out_path}")


if __name__ == "__main__":
    main()
