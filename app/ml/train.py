"""Train and evaluate the wait-time model on replayed simulator days (docs §14.3).

    python -m app.ml.train --end 2026-10-19 [--days 90] [--out app/ml/artifacts] [--results eval/results]

Uses DATABASE_URL (a database filled with ``python -m simulator history --days 90``).
Compares the model with both baselines - position × 10 minutes and position ×
the doctor's historical average - on the held-out test days, and writes the
metrics from this run to eval/results/.
"""

import argparse
import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

from app.db.session import session_scope
from app.ml.dataset import Dataset, build_dataset, doctor_averages, split_days
from app.ml.features import FEATURES
from app.ml.model import ARTIFACT_DIR
from app.timeutil import now_ist

TARGET_COVERAGE = 0.80
PARAMS = {
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_data_in_leaf": 50,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "seed": 42,
    "deterministic": True,
    "force_col_wise": True,
    "verbose": -1,
}


def metrics(
    pred: np.ndarray, actual: np.ndarray, low: np.ndarray | None = None, high: np.ndarray | None = None
) -> dict:
    err = np.abs(pred - actual)
    out = {"mae": round(float(err.mean()), 2), "p90_abs_error": round(float(np.percentile(err, 90)), 2)}
    if low is not None:
        out["range_coverage"] = round(float(np.mean((actual >= low) & (actual <= high))), 4)
        out["mean_range_width"] = round(float(np.mean(high - low)), 2)
    return out


def baselines(ds: Dataset) -> dict:
    return {
        "position_x_10": metrics(ds.position * 10.0, ds.wait),
        "position_x_doctor_avg": metrics(ds.position * ds.doctor_avg, ds.wait),
    }


def _train(objective: dict, train: Dataset, val: Dataset):
    import lightgbm as lgb

    dtrain = lgb.Dataset(train.x, train.residual, feature_name=FEATURES, free_raw_data=False)
    dval = lgb.Dataset(val.x, val.residual, reference=dtrain)
    return lgb.train(
        {**PARAMS, **objective},
        dtrain,
        num_boost_round=1500,
        valid_sets=[dval],
        callbacks=[lgb.early_stopping(50, verbose=False)],
    )


def evaluate(models: dict, adjust: tuple[float, float], ds: Dataset) -> dict:
    mid = np.maximum(models["mid"].predict(ds.x), 0) + ds.offset
    low = np.maximum(models["low"].predict(ds.x) - adjust[0], 0) + ds.offset
    high = np.maximum(models["high"].predict(ds.x) + adjust[1], 0) + ds.offset
    low, high = np.minimum(low, mid), np.maximum(high, mid)
    out = metrics(mid, ds.wait, low, high)
    walk = ds.walk_in == 1
    out["by_kind"] = {
        "booked": metrics(mid[~walk], ds.wait[~walk]),
        "walk_in": metrics(mid[walk], ds.wait[walk]) if walk.any() else None,
    }
    return out


def conformal_adjust(models: dict, val: Dataset) -> tuple[float, float]:
    """Shift the 10%/90% bounds so the validation coverage is ~80% (two-sided, equal tails)."""
    low = models["low"].predict(val.x)
    high = models["high"].predict(val.x)
    y = val.residual
    n = len(y)
    level = min(1.0, (1 - (1 - TARGET_COVERAGE) / 2) * (1 + 1 / n))
    return float(np.quantile(low - y, level)), float(np.quantile(y - high, level))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.ml.train")
    parser.add_argument("--end", type=date.fromisoformat, required=True, help="first day after the simulated history")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--out", type=Path, default=ARTIFACT_DIR)
    parser.add_argument("--results", type=Path, default=Path("eval/results"))
    args = parser.parse_args(argv)
    import lightgbm as lgb

    started = time.perf_counter()
    splits = split_days(args.end, args.days)
    with session_scope() as db:
        avg = doctor_averages(db, *splits["train"])
        data = {name: build_dataset(db, *span, avg) for name, span in splits.items()}
    for name, ds in data.items():
        if len(ds) == 0:
            print(f"no {name} rows: replay the history first", file=sys.stderr)
            return 1

    models = {
        "mid": _train({"objective": "l1", "metric": "l1"}, data["train"], data["val"]),
        "low": _train({"objective": "quantile", "alpha": 0.1, "metric": "quantile"}, data["train"], data["val"]),
        "high": _train({"objective": "quantile", "alpha": 0.9, "metric": "quantile"}, data["train"], data["val"]),
    }
    adjust = conformal_adjust(models, data["val"])

    args.out.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    for name, booster in models.items():
        text = booster.model_to_string()
        (args.out / f"{name}.txt").write_text(text)
        digest.update(text.encode())
    version = f"lgbm-v1-{digest.hexdigest()[:10]}"
    importance = dict(zip(FEATURES, models["mid"].feature_importance("gain").round(1).tolist(), strict=True))
    meta = {
        "version": version,
        "features": FEATURES,
        "doctor_avg": avg,
        "calibration": {
            "low_adjust": round(adjust[0], 4),
            "high_adjust": round(adjust[1], 4),
            "target_coverage": TARGET_COVERAGE,
        },
        "trees": {name: b.num_trees() for name, b in models.items()},
    }
    (args.out / "meta.json").write_text(json.dumps(meta, indent=2))

    results = {
        "run_at": now_ist().isoformat(timespec="seconds"),
        "model_version": version,
        "lightgbm_version": lgb.__version__,
        "data": {
            "source": "simulator history (python -m simulator history)",
            "splits": {k: [a.isoformat(), b.isoformat()] for k, (a, b) in splits.items()},
            "rows": {k: len(v) for k, v in data.items()},
            "sessions": {k: v.meta["sessions"] for k, v in data.items()},
        },
        "validation": {"model": evaluate(models, adjust, data["val"]), **baselines(data["val"])},
        "test": {"model": evaluate(models, adjust, data["test"]), **baselines(data["test"])},
        "feature_importance_gain": dict(sorted(importance.items(), key=lambda kv: -kv[1])),
        "seconds": round(time.perf_counter() - started, 1),
    }
    test = results["test"]
    results["gate"] = {
        "beats_position_x_10": test["model"]["mae"] < test["position_x_10"]["mae"],
        "beats_position_x_doctor_avg": test["model"]["mae"] < test["position_x_doctor_avg"]["mae"],
        "coverage_in_75_85": 0.75 <= test["model"]["range_coverage"] <= 0.85,
    }
    args.results.mkdir(parents=True, exist_ok=True)
    (args.results / "ml_wait_time.json").write_text(json.dumps(results, indent=2))
    print(json.dumps({"test": test, "gate": results["gate"], "rows": results["data"]["rows"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
