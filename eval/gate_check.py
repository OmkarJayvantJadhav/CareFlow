"""The emergency gate on its own (no LLM) on every emergency set: recall on emergencies, false alarms on
look-alike non-emergencies. Fast and free, so it is re-run whenever the gate's training data changes.

    python -m eval.gate_check [--out emergency_gate_v3.json] [--note "..."]

The full safety run (``python -m eval.run_safety``) also measures what the user is shown with the LLM in
the loop; this checks only the code-level gate.
"""

import argparse
import json
import sys

import numpy as np
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from app.safety.emergency import CLASSIFIER_THRESHOLD, build_classifier, check_emergency, training_data
from eval.common import load_jsonl, run_header, write_result

SETS = {
    "emergency": "eval/datasets/safety/emergency.jsonl",
    "emergency_holdout": "eval/datasets/safety/emergency_holdout.jsonl",
    "emergency_holdout2": "eval/datasets/safety/emergency_holdout2.jsonl",
    "emergency_negatives": "eval/datasets/safety/emergency_negatives.jsonl",
    "emergency_holdout_negatives": "eval/datasets/safety/emergency_holdout_negatives.jsonl",
    "emergency_holdout2_negatives": "eval/datasets/safety/emergency_holdout2_negatives.jsonl",
}


def cross_validated() -> dict:
    """5-fold out-of-fold recall and false alarms of the classifier alone at the threshold in use."""
    texts, labels = training_data()
    y = np.array(labels)
    folds = StratifiedKFold(5, shuffle=True, random_state=0)
    proba = cross_val_predict(build_classifier(), texts, y, cv=folds, method="predict_proba")[:, 1]
    flagged = proba >= CLASSIFIER_THRESHOLD
    return {
        "examples": len(y),
        "emergencies": int(y.sum()),
        "threshold": CLASSIFIER_THRESHOLD,
        "recall": round(float((flagged & (y == 1)).sum() / (y == 1).sum()), 4),
        "false_alarm_rate": round(float((flagged & (y == 0)).sum() / (y == 0).sum()), 4),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.gate_check")
    parser.add_argument("--out", default="emergency_gate_v3.json")
    parser.add_argument("--note", default="")
    args = parser.parse_args(argv)
    sets = {}
    for name, path in SETS.items():
        rows = load_jsonl(path)
        flagged = [r for r in rows if check_emergency(r["message"]).is_emergency]
        negatives = name.endswith("negatives")
        sets[name] = {
            "cases": len(rows),
            "flagged": len(flagged),
            ("false_alarm_rate" if negatives else "gate_recall"): round(len(flagged) / len(rows), 4),
        }
    out = {"header": run_header(note=args.note), "training_cv": cross_validated(), "sets": sets}
    path = write_result(args.out, out)
    print(json.dumps(out["sets"] | {"training_cv": out["training_cv"]}, indent=2))
    print(f"written to {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
