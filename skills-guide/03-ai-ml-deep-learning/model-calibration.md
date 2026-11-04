# Model Calibration

## 30-second answer
A model is **calibrated** when its confidence matches reality: of all predictions made with "70%" confidence, about 70% should be correct. Deep networks are usually **over-confident**. In MedVision AI I used **temperature scaling** — divide the logits by one number *T* fitted on the validation set — which brought the **expected calibration error (ECE) to 0.026**. On top of the calibrated probabilities I fitted, on validation only, a **high-risk alert threshold** on the combined malignant probability (catches **90.4%** of malignant test images) and a **confidence threshold** (labelled "confident" answers are right 86.9% of the time). In CareFlow, the LightGBM wait-time ranges are calibrated with **conformalised quantile regression** to cover ~80% of real waits (77.7% on test).

---

## Basics you must know

### Measuring calibration
- **Reliability diagram:** bin predictions by confidence (e.g. 15 bins), plot average confidence vs accuracy per bin; a perfectly calibrated model lies on the diagonal.
- **ECE (Expected Calibration Error):**  
  `ECE = Σ_bins (n_b / N) · |accuracy_b − confidence_b|`
- **NLL (negative log-likelihood)** and **Brier score** are also calibration-sensitive.

### Calibration methods
| Method | Idea | Changes ranking? |
|---|---|---|
| **Temperature scaling** | `softmax(z / T)`, one parameter T > 0 | **No** — top-1 prediction unchanged |
| Platt scaling | Logistic regression on the score (binary) | No |
| Isotonic regression | Monotonic piecewise-constant mapping | Can create ties |
| Vector / matrix scaling | Per-class parameters | Yes |

**T > 1** softens over-confident outputs; **T < 1** sharpens under-confident ones.

### Rules
- Fit calibration on a **validation** set, never the test set, never the training set.
- Report the effect on the untouched test set.

### Decision thresholds ≠ 0.5
In medicine a missed cancer costs more than a false alarm, so pick the threshold that reaches a target **recall** (sensitivity) and report the precision and alert rate it costs.

### Conformal prediction (CareFlow)
Turn a model's predicted interval into one with a guaranteed coverage level by measuring how far real values fall outside predicted intervals on held-out data and widening by that quantile.

---

## How I used it in MedVision AI

### Temperature scaling (`ml/src/medvision_ml/calibration/fitting.py`)
```python
def fit_temperature(logits, labels) -> float:
    def nll(log_t):
        return -log_softmax(logits / exp(log_t))[rows, labels].mean()
    # golden-section search on log(T) in [-3, 3]  (T ≈ 0.05 … 20); the loss has one minimum
    ...
    return exp((low + high) / 2)

def calibrated_probabilities(logits, T):
    return exp(log_softmax(logits / T))
```
- Searching over **log T** keeps T positive and makes the search symmetric.
- A numerically stable `log_softmax` (subtract the row max first).
- **Result: ECE 0.026** on the test set (target ≤ 0.05). Reliability diagrams before/after are in `docs/assets/`.

### Serving the calibration
The backend never sees TensorFlow. It recomputes logits from the ONNX feature maps (`mean(feature_maps) @ kernel + bias`) and applies `softmax(logits / T)` in NumPy (`backend/app/inference/calibration.py`). T ships inside `model_meta.json` with the model release.

### High-risk alert threshold (`threshold_for_recall` in `evaluation/metrics.py`, `operating_point`)
- Sum the calibrated probabilities of **melanoma + basal cell carcinoma + squamous cell carcinoma + actinic keratosis**.
- Pick the line that catches **90% of malignant validation images**.
- Test result: **90.4% recall, 68.1% precision, alert raised for 49% of images**, malignant-group ROC-AUC 0.916.
- The alert is raised **whatever the top class is** — a "nevus" top answer can still trigger it — and it is shown **above** the lesion type.

### Confident / uncertain threshold (`confidence_threshold`)
Sort validation predictions by confidence and find the lowest confidence above which accuracy is still ≥ **85%**. Test: **59%** of images labelled confident, **86.9%** of those correct.

### Why calibration matters here
"92%" must mean something to a clinician, and the alert threshold is a probability line — it is only meaningful if the probabilities are calibrated.

### Other gates fitted the same way (validation → test)
- **Out-of-distribution**: Mahalanobis distance threshold so 99% of validation lesion images pass → 98.9% pass on test, **99.6% of 497 everyday photos rejected** (AUROC 0.9998; energy and max-softmax scores only rejected 18% at the same acceptance).
- **Noise gate**: threshold so 99% of validation images pass → silent misses on noisy images cut **from up to 49% to 0%**.

---

## How I used it in CareFlow (wait-time ranges)

`app/ml/train.py` trains three LightGBM models: a median (L1) model and **10th / 90th percentile** quantile models. Then `conformal_adjust()` measures on the validation days how far actual waits fall below the low line / above the high line and takes the quantile needed for **80% coverage**:
```python
low_adjust  = quantile(low_pred - actual, level)
high_adjust = quantile(actual - high_pred, level)
```
At prediction time: `low − low_adjust`, `high + high_adjust`. Stored in `app/ml/artifacts/meta.json` (`low_adjust 0.52`, `high_adjust 2.73`). Test coverage **77.7%** (target 75–85%). The UI shows "about 65 min (60–100)", rounded to 5 minutes.

---

## Interview questions

**Q: What does temperature scaling change, and what doesn't it change?**
It changes confidence (how peaked the softmax is) but not the order of classes, so accuracy and top-1 predictions are identical.

**Q: Why not calibrate on the test set?**
Then the reported test ECE would be optimistic — it's the same as training on test data. Fit on validation, report on test.

**Q: How did you choose the alert threshold?**
Target recall: the line that catches 90% of malignant validation images, then report recall, precision and alert rate on test. Missing a cancer is worse than an extra referral.

**Q: Isn't alerting on 49% of images too often?**
It's the cost of 90% recall with the current model, and ISIC 2019 is cancer-rich (37% malignant on test); in primary care, with fewer cancers, the alert would fire less. A stronger model (roadmap) should keep recall at 0.90 with fewer alerts.

**Q: What's ECE and how many bins did you use?**
Weighted average gap between confidence and accuracy across confidence bins; 15 bins.

**Q: How is calibration different for regression?**
You calibrate intervals, not class probabilities — e.g. conformalised quantile regression in CareFlow so the predicted range covers the target share of real waits.
