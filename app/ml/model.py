"""Wait-time model: a point estimate and a calibrated low-high range (FR-24).

The trained model is three LightGBM boosters over the features in
``app/ml/features.py``: an L1 (median) model for the estimate and 10th / 90th
percentile models for the range, widened or narrowed on the validation days
(conformalised quantile regression) so the range covers about 80% of actual
waits. If no trained model is available, a transparent fallback is used:
people ahead × the doctor's average consultation time.
"""

import json
import logging
import math
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.ml.features import FEATURES, WaitingRow

log = logging.getLogger(__name__)
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"


@dataclass(frozen=True)
class Estimate:
    predicted_min: float
    low_min: float
    high_min: float


def _finalise(offset: float, mid: float, low: float, high: float) -> Estimate:
    mid, low, high = max(mid, 0.0), max(low, 0.0), max(high, 0.0)
    low, high = min(low, mid), max(high, mid)
    return Estimate(round(offset + mid, 1), round(offset + low, 1), round(offset + high, 1))


class FallbackModel:
    """People ahead × the doctor's average consultation length, with a ±40% range."""

    version = "fallback-ahead-x-avg"

    def __init__(self, doctor_avg: dict[str, float] | None = None):
        self._avg = doctor_avg or {}

    def doctor_avg(self, doctor_name: str) -> float | None:
        return self._avg.get(doctor_name)

    def predict(self, rows: list[WaitingRow]) -> list[Estimate]:
        out = []
        for row in rows:
            avg = row.features[FEATURES.index("doctor_avg")]
            mid = row.ahead * avg
            out.append(_finalise(row.start_offset, mid, 0.6 * mid, 1.4 * mid + avg))
        return out


class LightGbmModel:
    def __init__(self, directory: Path):
        import lightgbm as lgb

        meta = json.loads((directory / "meta.json").read_text())
        if meta["features"] != FEATURES:
            raise ValueError("model was trained on a different feature list")
        self.version = meta["version"]
        self._avg = meta["doctor_avg"]
        self._low_adjust = meta["calibration"]["low_adjust"]
        self._high_adjust = meta["calibration"]["high_adjust"]
        self._boosters = {
            name: lgb.Booster(model_file=str(directory / f"{name}.txt")) for name in ("mid", "low", "high")
        }

    def doctor_avg(self, doctor_name: str) -> float | None:
        return self._avg.get(doctor_name)

    def predict(self, rows: list[WaitingRow]) -> list[Estimate]:
        if not rows:
            return []
        x = np.array([r.features for r in rows], dtype=np.float64)
        mid = self._boosters["mid"].predict(x)
        low = self._boosters["low"].predict(x) - self._low_adjust
        high = self._boosters["high"].predict(x) + self._high_adjust
        return [_finalise(r.start_offset, m, lo, hi) for r, m, lo, hi in zip(rows, mid, low, high, strict=True)]


_lock = threading.Lock()
_model = None


def get_wait_model(directory: Path | None = None):
    """The trained model if its artifacts load, otherwise the fallback (logged once)."""
    global _model
    with _lock:
        if _model is None or directory is not None:
            target = directory or ARTIFACT_DIR
            try:
                _model = LightGbmModel(target)
            except Exception as err:  # noqa: BLE001 - missing artifacts or library
                log.warning("wait-time model unavailable (%s); using %s", err, FallbackModel.version)
                avg = {}
                meta = target / "meta.json"
                if meta.exists():
                    avg = json.loads(meta.read_text()).get("doctor_avg", {})
                _model = FallbackModel(avg)
        return _model


def display_range(estimate: Estimate) -> str:
    """'about 35 min (25–50)': rounded to 5 minutes, never a single precise number."""

    def r5(x: float, how=round) -> int:
        return int(5 * how(x / 5))

    if estimate.high_min < 5:
        return "less than 5 min"
    mid = max(5, r5(estimate.predicted_min))
    low = max(0, r5(estimate.low_min, math.floor))
    high = max(mid, r5(estimate.high_min, math.ceil))
    return f"about {mid} min ({low}–{high})"
