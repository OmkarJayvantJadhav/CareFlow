"""Choose the emergency classifier's thresholds by cross-validation on its training data only.

    python -m app.safety.emergency_tune

The evaluation sets in eval/datasets/safety are never used here. Prints, for 5-fold
out-of-fold predictions, recall and false-alarm rate per threshold, and the two
thresholds used by ``app.safety.emergency``: the classifier threshold (highest
with recall >= 95%) and the bar a generic-word pattern must clear (highest with
recall >= 99%). The classifier threshold in use (0.6) was then raised from that
first choice after it flagged ordinary sentences (see the comment in emergency.py).
"""

import numpy as np
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from app.safety.emergency import build_classifier, training_data

GRID = [round(0.05 * i, 2) for i in range(2, 19)]


def main() -> None:
    texts, labels = training_data()
    y = np.array(labels)
    folds = StratifiedKFold(5, shuffle=True, random_state=0)
    proba = cross_val_predict(build_classifier(), texts, y, cv=folds, method="predict_proba")[:, 1]
    rows = []
    for t in GRID:
        flagged = proba >= t
        recall = float((flagged & (y == 1)).sum() / (y == 1).sum())
        false_alarm = float((flagged & (y == 0)).sum() / (y == 0).sum())
        rows.append((t, recall, false_alarm))
        print(f"threshold {t:.2f}  recall {recall:.3f}  false alarms {false_alarm:.3f}")
    main_t = max(t for t, r, _ in rows if r >= 0.95)
    weak_t = max(t for t, r, _ in rows if r >= 0.99)
    print(f"examples: {len(y)} ({int(y.sum())} emergencies)")
    print(f"CLASSIFIER_THRESHOLD = {main_t}  WEAK_PATTERN_THRESHOLD = {weak_t}")


if __name__ == "__main__":
    main()
