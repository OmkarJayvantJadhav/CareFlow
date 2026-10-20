# Results

Every number here comes from a real run, stored next to this file with its configuration.
Agent, RAG and safety evaluations (Phase 4) have not been run yet.

<!-- details below are kept -->

## Wait-time model (docs §14.3) — `ml_wait_time.json`

Run: 20 Oct 2026, model `lgbm-v1-4db5f69cf8` (LightGBM 4.7.0), data from
`python -m simulator history --days 90 --end 2026-10-19` (seed 42).

| Split | Days | Sessions | Rows (queue event × waiting patient) |
| --- | --- | --- | --- |
| Train | 21 Jul – 18 Sep 2026 (days 1–60) | 520 | 38,890 |
| Validation | 19 Sep – 3 Oct 2026 (days 61–75) | 130 | 11,589 |
| Test | 4 Oct – 18 Oct 2026 (days 76–90) | 120 | 9,736 |

Test days (held out):

| Method | MAE (min) | P90 absolute error (min) | Range coverage |
| --- | --- | --- | --- |
| Baseline: position × 10 min | 29.78 | 84.88 | — |
| Baseline: position × doctor's historical average | 29.38 | 84.07 | — |
| **LightGBM model** | **17.91** | **44.20** | **77.7%** (mean width 49.1 min) |

By patient type (model, test days): booked MAE 11.93 min, walk-in MAE 23.77 min.

Validation days: model MAE 16.42 (baselines 25.47 and 23.82), coverage 80.1%.

Gate (docs §10, Queue + ML): the model beats both baselines on the test days — **passed** —
and range coverage is inside the 75–85% target.

Caveats: the data is synthetic and its queues are short (usually 2–5 people waiting at once), which
is why there are only ~60,000 rows over 90 days. Real OPDs may behave differently (risk R09).
