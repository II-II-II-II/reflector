"""
Score model extractions against the hand-labeled gold standard.

Safe to run and share: outputs only aggregate agreement metrics
(precision/recall/F1/MAE per field), never entry content or per-entry
labels. Writes a markdown report to data/eval/ in addition to printing.

Usage:
    python -m reflector.score_extractions data/processed/extractions_qwen2.5-32b.jsonl data/processed/extractions_llama3.3-70b.jsonl
"""

import json
import sys
from datetime import datetime
from pathlib import Path

GOLD_PATH = Path(__file__).parent.parent / "data" / "eval" / "gold.jsonl"
EVAL_DIR = Path(__file__).parent.parent / "data" / "eval"

SET_FIELDS = ["primary_emotions", "cognitive_distortions", "themes", "coping_behaviors"]
SCALAR_EXACT_FIELDS = ["notable_event", "event_category"]
NESTED_BOOL_FIELDS = [
    ("risk_flags", "self_harm_language"),
    ("risk_flags", "hopelessness_language"),
    ("physical_health", "exercise_mentioned"),
    ("physical_health", "substance_use_mentioned"),
]
NUMERIC_TOLERANCE = {"emotional_intensity": 1, "sentiment_score": 0.2}


def load_jsonl(path: Path) -> dict[str, dict]:
    with open(path) as f:
        return {(r := json.loads(line))["id"]: r for line in f if line.strip()}


def prf1(gold_set: set, pred_set: set) -> tuple[float, float, float]:
    if not gold_set and not pred_set:
        return 1.0, 1.0, 1.0
    tp = len(gold_set & pred_set)
    precision = tp / len(pred_set) if pred_set else (1.0 if not gold_set else 0.0)
    recall = tp / len(gold_set) if gold_set else (1.0 if not pred_set else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def score(gold: dict, pred_map: dict, name: str) -> list[str]:
    common = [eid for eid in gold if eid in pred_map]
    lines = [f"## {name}", "", f"Scored {len(common)} / {len(gold)} gold entries.", ""]
    if not common:
        lines.append("No overlapping entry IDs with gold set.")
        return lines

    lines.append("| Field | Metric |")
    lines.append("|---|---|")

    for field in SET_FIELDS:
        ps, rs, f1s = [], [], []
        for eid in common:
            g, p = set(gold[eid].get(field, [])), set(pred_map[eid].get(field, []))
            pr, rc, f1 = prf1(g, p)
            ps.append(pr)
            rs.append(rc)
            f1s.append(f1)
        lines.append(
            f"| `{field}` | precision={sum(ps)/len(ps):.2f}  recall={sum(rs)/len(rs):.2f}  f1={sum(f1s)/len(f1s):.2f} |"
        )

    for field in SCALAR_EXACT_FIELDS:
        matches = sum(1 for eid in common if gold[eid].get(field) == pred_map[eid].get(field))
        lines.append(f"| `{field}` | exact_match={matches/len(common):.2f} |")

    for parent, field in NESTED_BOOL_FIELDS:
        matches = sum(1 for eid in common if gold[eid][parent][field] == pred_map[eid][parent][field])
        extra = ""
        if parent == "risk_flags":
            gold_true = [eid for eid in common if gold[eid][parent][field] is True]
            if gold_true:
                recall = sum(1 for eid in gold_true if pred_map[eid][parent][field] is True) / len(gold_true)
                extra = f", recall_on_true_positives={recall:.2f} (n={len(gold_true)})"
            else:
                extra = ", (no true cases in gold — recall undefined)"
        lines.append(f"| `{parent}.{field}` | exact_match={matches/len(common):.2f}{extra} |")

    for field, tol in NUMERIC_TOLERANCE.items():
        errors = [abs(gold[eid][field] - pred_map[eid][field]) for eid in common]
        mae = sum(errors) / len(errors)
        within = sum(1 for e in errors if e <= tol) / len(errors)
        lines.append(f"| `{field}` | MAE={mae:.2f}, within_tolerance(±{tol})={within:.2f} |")

    lines.append("")
    return lines


def main() -> None:
    if not GOLD_PATH.exists():
        print(f"No gold file at {GOLD_PATH}. Run `python -m reflector.label_gold` first.")
        sys.exit(1)
    if len(sys.argv) < 2:
        print("Usage: python -m reflector.score_extractions <model_output1.jsonl> [model_output2.jsonl ...]")
        sys.exit(1)

    gold = load_jsonl(GOLD_PATH)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    report = [f"# Extraction model comparison — {timestamp}", "", f"Gold standard: {len(gold)} hand-labeled entries.", ""]
    for path_str in sys.argv[1:]:
        report.extend(score(gold, load_jsonl(Path(path_str)), path_str))

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EVAL_DIR / f"scores_{timestamp}.md"
    out_path.write_text("\n".join(report))

    print("\n".join(report))
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
