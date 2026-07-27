"""
Interactive tool for hand-labeling entries with the EXACT same schema and
field definitions given to the models — this produces the gold standard
the model outputs get scored against.

RUN THIS YOURSELF, in your own terminal. It displays real entry text and
asks you to grade it. Do not run this through a cloud-hosted assistant.

Usage:
    python -m reflector.label_gold data/eval/eval_ids.txt
"""

import json
import sys
from pathlib import Path

from reflector.prompts import EXTRACTION_SYSTEM_PROMPT
from reflector.schema import (
    CognitiveDistortion,
    CopingBehavior,
    Emotion,
    EntryExtraction,
    PhysicalHealth,
    RelationshipType,
    RiskFlags,
    SleepQuality,
    Theme,
    Valence,
)

ENTRIES_PATH = Path(__file__).parent.parent / "data" / "processed" / "entries.jsonl"
GOLD_PATH = Path(__file__).parent.parent / "data" / "eval" / "gold.jsonl"


def prompt_enum_list(label: str, enum_cls, max_n: int | None = None) -> list[str]:
    valid = [e.value for e in enum_cls]
    while True:
        raw = input(f"{label}\n  options: {', '.join(valid)}\n  > ").strip()
        if not raw:
            return []
        vals = [v.strip() for v in raw.split(",")]
        if all(v in valid for v in vals) and (max_n is None or len(vals) <= max_n):
            return vals
        print(f"  Invalid — must be from the list above{f' (max {max_n})' if max_n else ''}.")


def prompt_enum(label: str, enum_cls, allow_none: bool = False) -> str | None:
    valid = [e.value for e in enum_cls]
    while True:
        raw = input(f"{label} ({'/'.join(valid)}{' — blank for none' if allow_none else ''}): ").strip()
        if not raw and allow_none:
            return None
        if raw in valid:
            return raw
        print(f"  Invalid — must be one of: {valid}")


def prompt_bool(label: str) -> bool:
    while True:
        raw = input(f"{label} (y/n): ").strip().lower()
        if raw in ("y", "n"):
            return raw == "y"


def prompt_float(label: str, lo: float, hi: float) -> float:
    while True:
        raw = input(f"{label} ({lo} to {hi}): ").strip()
        try:
            v = float(raw)
            if lo <= v <= hi:
                return v
        except ValueError:
            pass
        print(f"  Enter a number between {lo} and {hi}")


def prompt_int(label: str, lo: int, hi: int) -> int:
    while True:
        raw = input(f"{label} ({lo}-{hi}): ").strip()
        try:
            v = int(raw)
            if lo <= v <= hi:
                return v
        except ValueError:
            pass
        print(f"  Enter an integer between {lo} and {hi}")


def label_one(entry: dict) -> EntryExtraction:
    print("=" * 100)
    print(entry["date"])
    print("-" * 100)
    print(entry["text"])
    print("-" * 100)

    primary_emotions = prompt_enum_list("primary_emotions (up to 3, most to least prominent)", Emotion, max_n=3)
    emotional_intensity = prompt_int("emotional_intensity", 1, 10)
    sentiment_score = prompt_float("sentiment_score", -1.0, 1.0)
    cognitive_distortions = prompt_enum_list("cognitive_distortions (blank if none)", CognitiveDistortion)
    themes = prompt_enum_list("themes (up to 4)", Theme, max_n=4)
    stressors = [{"category": c} for c in prompt_enum_list("stressor categories (blank if none)", Theme)]

    relationships_mentioned = []
    n_rel = prompt_int("how many relationships to tag (0 if none)", 0, 5)
    for i in range(n_rel):
        rtype = prompt_enum(f"  relationship {i + 1} type", RelationshipType)
        rvalence = prompt_enum(f"  relationship {i + 1} valence", Valence)
        relationships_mentioned.append({"type": rtype, "valence": rvalence})

    coping_behaviors = prompt_enum_list("coping_behaviors (blank if none)", CopingBehavior)
    sleep_quality = prompt_enum("sleep_quality", SleepQuality)
    exercise_mentioned = prompt_bool("exercise_mentioned")
    substance_use_mentioned = prompt_bool("substance_use_mentioned")

    notable_event = prompt_bool("notable_event")
    event_category = prompt_enum("event_category", Theme, allow_none=True) if notable_event else None

    self_harm_language = prompt_bool("risk_flags.self_harm_language")
    hopelessness_language = prompt_bool("risk_flags.hopelessness_language")
    notable_detail = input("notable_detail (optional, <200 chars, blank ok): ").strip() or None

    return EntryExtraction(
        primary_emotions=primary_emotions,
        emotional_intensity=emotional_intensity,
        sentiment_score=sentiment_score,
        cognitive_distortions=cognitive_distortions,
        themes=themes,
        stressors=stressors,
        relationships_mentioned=relationships_mentioned,
        coping_behaviors=coping_behaviors,
        physical_health=PhysicalHealth(
            sleep_quality=sleep_quality,
            exercise_mentioned=exercise_mentioned,
            substance_use_mentioned=substance_use_mentioned,
        ),
        notable_event=notable_event,
        event_category=event_category,
        risk_flags=RiskFlags(self_harm_language=self_harm_language, hopelessness_language=hopelessness_language),
        notable_detail=notable_detail,
        confidence=1.0,
    )


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m reflector.label_gold <ids_file>")
        sys.exit(1)

    wanted_ids = [line.strip() for line in Path(sys.argv[1]).read_text().splitlines() if line.strip()]

    entries_by_id = {}
    with ENTRIES_PATH.open() as f:
        for line in f:
            e = json.loads(line)
            if e["id"] in wanted_ids:
                entries_by_id[e["id"]] = e

    GOLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    already = set()
    if GOLD_PATH.exists():
        with GOLD_PATH.open() as f:
            already = {json.loads(line)["id"] for line in f if line.strip()}

    todo = [eid for eid in wanted_ids if eid in entries_by_id and eid not in already]
    print(f"Field definitions reference:\n\n{EXTRACTION_SYSTEM_PROMPT}\n")
    print(f"{len(todo)} entries to label ({len(already)} already done). Ctrl+C any time to stop — progress is saved per entry.\n")

    with GOLD_PATH.open("a") as out:
        for i, eid in enumerate(todo, 1):
            result = label_one(entries_by_id[eid])
            record = {"id": eid, "date": entries_by_id[eid]["date"], **result.model_dump(mode="json")}
            out.write(json.dumps(record) + "\n")
            out.flush()
            print(f"Saved ({i}/{len(todo)}).\n")


if __name__ == "__main__":
    main()
