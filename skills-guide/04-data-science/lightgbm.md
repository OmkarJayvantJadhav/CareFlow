# LightGBM

## 30-second answer
LightGBM is Microsoft's **gradient-boosted decision tree** library — fast, memory-efficient and usually the best choice for tabular data. In CareFlow I trained a **LightGBM wait-time predictor**: three boosters over 22 queue features — a **median (L1) model** for the estimate and **10th / 90th percentile quantile models** for a range, widened on validation days with **conformal calibration** so the range covers ~80% of real waits. On held-out test days it reached **MAE 17.9 min vs 29.4 min** for the best baseline (people ahead × doctor's average), P90 error 44 vs 84 min, and **77.7% range coverage**.

---

## Basics you must know

### Gradient boosting in one paragraph
Build trees **one after another**; each new tree is fitted to the **gradient of the loss** (for squared error: the residuals) of the current ensemble, and added with a small **learning rate**. The final prediction is the sum of all trees. Many shallow, weak trees → a strong model.

### What makes LightGBM fast
| Technique | Idea |
|---|---|
| **Histogram-based splits** | Bucket feature values into bins; find splits on histograms, not sorted values |
| **Leaf-wise growth** | Split the leaf with the largest loss reduction (deeper, more accurate trees; control with `num_leaves`) vs XGBoost's default level-wise |
| **GOSS** | Gradient-based One-Side Sampling — keep large-gradient rows, sample small ones |
| **EFB** | Exclusive Feature Bundling for sparse features |
| Native categorical features, missing values handled automatically | |

### Key hyperparameters
| Parameter | Effect |
|---|---|
| `learning_rate` | Smaller = more trees needed, usually better generalisation |
| `num_leaves` | Model complexity (main overfitting knob) |
| `min_data_in_leaf` | Minimum samples per leaf — regularisation |
| `feature_fraction` | Column subsampling per tree |
| `bagging_fraction` + `bagging_freq` | Row subsampling |
| `num_boost_round` + **early stopping** | Stop when validation loss stops improving |
| `objective` | `regression` (L2), `l1` (median), `quantile` with `alpha`, `binary`, `multiclass`, `lambdarank` |

### Quantile regression
The **pinball loss** with `alpha = 0.9` makes the model predict the 90th percentile — 90% of true values should lie below it. Two quantile models (0.1 and 0.9) give an 80% prediction interval.

### LightGBM vs XGBoost vs CatBoost vs Random Forest
- Random forest: trees in parallel on bootstrap samples, averaged (bagging).
- XGBoost: boosting, level-wise by default, very mature.
- LightGBM: boosting, leaf-wise, fastest on large data.
- CatBoost: boosting with strong categorical handling.

---

## How I used it in CareFlow (`app/ml/`)

### Problem framing (`app/ml/features.py`)
Predict how long a waiting patient will wait until their consultation starts.
- **Target split:** `wait = start_offset + residual`. `start_offset` is known for certain (doctor on a break, delayed, OPD not open yet); the model learns only the **residual**. A break therefore moves every estimate by exactly its length (test TC-10).
- **No leakage in time:** `state_at(records, t)` rebuilds the queue **using only events up to time t**. Training rows from finished days contain exactly what the live system would have known; live prediction calls the same function with `t = now`.

### The 22 features
`position, ahead, in_room, walk_in, late_or_returned, priority, minutes_waited, slot_offset, booked_ahead, walk_ins_ahead, upcoming_booked, queue_length, slot_minutes, doctor_avg, today_mean_consult, today_done, room_elapsed, minutes_since_open, hour, weekday, alternate_rule, expected_naive`

### Data and split (`app/ml/train.py`, `app/ml/dataset.py`)
- 90 simulated clinic days (`python -m simulator history --days 90`).
- **Calendar split** (not random — rows from the same day are correlated): days 1–60 train, 61–75 validation, 76–90 test.

### Training
```python
PARAMS = {"learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 50,
          "feature_fraction": 0.9, "bagging_fraction": 0.8, "bagging_freq": 1,
          "seed": 42, "deterministic": True, "force_col_wise": True, "verbose": -1}

models = {
    "mid":  _train({"objective": "l1", "metric": "l1"}, train, val),
    "low":  _train({"objective": "quantile", "alpha": 0.1, "metric": "quantile"}, train, val),
    "high": _train({"objective": "quantile", "alpha": 0.9, "metric": "quantile"}, train, val),
}
# each: lgb.train(..., num_boost_round=1500, valid_sets=[dval], callbacks=[lgb.early_stopping(50)])
adjust = conformal_adjust(models, val)        # widen/narrow to 80% coverage on validation days
```
- **L1 objective** for the point estimate: predicts the median, robust to very long outliers.
- Trees after early stopping: mid 287, low 94, high 166 (`app/ml/artifacts/meta.json`).

### Serving (`app/ml/model.py`)
- `LightGbmModel` loads `mid.txt`, `low.txt`, `high.txt` with `lgb.Booster(model_file=...)` and checks the feature list matches `meta.json`.
- `predict` → `offset + max(pred, 0)`, ensures `low ≤ mid ≤ high`.
- **Fallback** `FallbackModel` (people ahead × doctor's average, ±40%) if the artifacts can't load — logged once.
- `display_range` rounds to 5 minutes: "about 35 min (25–50)" — never a falsely precise number.
- Predictions are recalculated on every queue event and pushed over WebSockets.
- The Docker image installs `libgomp1` (OpenMP runtime LightGBM needs), and CI smoke-tests that the model loads inside the image.

### Results (held-out test days, `eval/results/ml_wait_time.json`)
| Metric | Position × 10 min | Position × doctor avg | **LightGBM** |
|---|---:|---:|---:|
| MAE (min) | 29.78 | 29.38 | **17.91** |
| P90 abs. error (min) | 84.88 | 84.07 | **44.20** |
| Range coverage | — | — | **77.7%** (target 75–85%) |

### Limitation to mention
Trained on **simulated** days whose parameters are assumptions; a real hospital would retrain on its own history.

---

## Interview questions

**Q: Why LightGBM and not a neural network?**
Small tabular dataset with mixed numeric features — gradient-boosted trees are the strongest, fastest and most robust choice there, need no scaling and train in seconds.

**Q: Why three models?**
One median model for the estimate and two quantile models (10th and 90th percentile) for the range, because patients need an honest range, not one number.

**Q: Why L1 instead of L2 loss?**
Wait times have long tails; L2 chases outliers, L1 predicts the median, which is a more useful "typical" wait.

**Q: What is conformal calibration here?**
Quantile models are rarely exactly calibrated, so on validation days I measured how far real waits fall outside the predicted range and widened the range by the quantile needed for 80% coverage.

**Q: Why split by calendar days?**
Rows from the same day share the same doctor delays and queue state; a random split would leak information between train and test and overstate accuracy.

**Q: How do you prevent leakage in features?**
Features are computed by replaying the queue up to time t with only events that had happened by then — the exact function used live.

**Q: How do you avoid overfitting?**
Early stopping on validation (50 rounds), `min_data_in_leaf=50`, feature and row subsampling, moderate `num_leaves`.
