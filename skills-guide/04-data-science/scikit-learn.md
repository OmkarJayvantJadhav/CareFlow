# scikit-learn

## 30-second answer
scikit-learn is Python's standard library for classical machine learning: a consistent **`fit` / `predict` / `transform`** API for models, preprocessing, pipelines, model selection and metrics. I used it in **both** projects. In CareFlow, the **emergency classifier** is a scikit-learn **Pipeline** — character and word **TF-IDF** features joined with `make_union` feeding a **class-balanced LogisticRegression** — and the offline retrieval fallback embeds text with **TF-IDF + TruncatedSVD** (LSA). In MedVision, `sklearn.metrics` computes **ROC-AUC, F1, precision/recall, accuracy, confusion matrices and the classification report**.

---

## Basics you must know

### The estimator API
```python
model.fit(X_train, y_train)
model.predict(X_test)
model.predict_proba(X_test)          # classifiers
transformer.fit_transform(X)         # preprocessing
```
Fit only on training data; transform validation/test with the fitted object (prevents leakage).

### Pipelines
```python
from sklearn.pipeline import make_pipeline, make_union
pipe = make_pipeline(StandardScaler(), LogisticRegression())
```
A pipeline guarantees the same preprocessing at train and predict time and works with cross-validation without leakage. `make_union` (FeatureUnion) concatenates several feature extractors side by side.

### Text features
- `CountVectorizer` — word counts.
- `TfidfVectorizer` — term frequency × inverse document frequency; `analyzer="word"` or `"char_wb"` (character n-grams within word boundaries — robust to spelling variations and mixed scripts); `ngram_range`; `sublinear_tf=True` uses `1 + log(tf)`.

### Common models
| Task | Models |
|---|---|
| Classification | LogisticRegression, SVC, RandomForest, GradientBoosting, KNN, NaiveBayes |
| Regression | LinearRegression, Ridge, Lasso, RandomForestRegressor |
| Clustering | KMeans, DBSCAN |
| Dimensionality reduction | PCA, TruncatedSVD (works on sparse matrices), t-SNE |

### Logistic regression essentials
- Linear model + sigmoid → probability.
- `C` = inverse regularisation strength (higher C → less regularisation).
- `class_weight="balanced"` → weights inversely proportional to class frequency.

### Model selection
`train_test_split` (with `stratify=y`), `KFold`, `StratifiedKFold`, `GroupKFold` (keep groups together), `cross_val_score`, `GridSearchCV`, `RandomizedSearchCV`.

### Metrics
- Classification: accuracy, precision, recall, F1 (macro/weighted), ROC-AUC (one-vs-rest for multiclass), confusion matrix, classification report.
- Regression: MAE, MSE, RMSE, R².
- Probabilities: log loss, Brier score; calibration curve.

---

## How I used it

### CareFlow — emergency classifier (`app/safety/emergency.py`)
```python
features = make_union(
    TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True),
    TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True, token_pattern=r"[^\s,.!?;:()]+"),
)
model = make_pipeline(features, LogisticRegression(C=8.0, class_weight="balanced", max_iter=3000, random_state=0))
model.fit(texts, labels)
probability = model.predict_proba([normalize(message)])[0][1]
```
- **Character n-grams** handle English, Devanagari Hindi/Marathi and romanised text ("saans nahi aa rahi") and typos without a tokenizer.
- **Balanced class weights** because emergencies are the minority class.
- Trained at start-up (thread-safe lazy singleton) on hand-written examples plus `emergency_training.jsonl` — never on the evaluation sets.
- Thresholds chosen with **5-fold cross-validation** (`python -m app.safety.emergency_tune` prints recall and false alarms per threshold): 0.6 alone (CV recall 90%, false alarms 4%), 0.2 when a weak pattern also matched.
- Result: **60/60** held-out emergencies with the full gate.

### CareFlow — offline embedder (`app/rag/embeddings.py`, `LsaEmbedder`)
`TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True)` → `TruncatedSVD` (Latent Semantic Analysis), padded to 384 dimensions and L2-normalised. Used when the neural model can't be downloaded and on the 512 MB server; it's deterministic, which also makes tests reproducible.

### MedVision — evaluation metrics (`ml/src/medvision_ml/evaluation/metrics.py`)
```python
from sklearn import metrics as skm
skm.accuracy_score(labels, predicted)
skm.roc_auc_score(labels, probs, multi_class="ovr", average="macro")   # 0.935
skm.classification_report(...)          # per-class precision/recall/F1 → macro F1 0.508
skm.confusion_matrix(labels, predicted, labels=all_labels)
skm.recall_score / precision_score      # malignant-group recall and precision
skm.roc_auc_score(is_malignant, malignant_score)                      # 0.916
```
Calibration (ECE, reliability bins) and threshold fitting are my own NumPy code because I needed exact control (see [Model calibration](../03-ai-ml-deep-learning/model-calibration.md)).

### Leakage-aware splitting (concept from `GroupKFold`)
MedVision splits by **lesion group and near-duplicate group** so no lesion appears in two splits — same idea as `GroupShuffleSplit`/`GroupKFold`, implemented in `data/splitting.py` with union-find style group merging.

---

## Interview questions

**Q: Why logistic regression for emergencies instead of a deep model?**
Small labelled set, needs to be fast, interpretable, and trainable at start-up in seconds. Character n-gram TF-IDF + logistic regression is a strong baseline for short multilingual text, and it is the second stage behind high-precision patterns.

**Q: What does `class_weight="balanced"` do?**
Weights each class by `n_samples / (n_classes × n_class_samples)` so the minority class (emergencies) contributes as much to the loss as the majority.

**Q: What's `char_wb`?**
Character n-grams taken only inside word boundaries (padded with spaces) — robust to typos and inflections, and works across scripts.

**Q: How do you avoid data leakage?**
Fit preprocessing inside a pipeline on training data only; split by groups (patients, lesions); never tune on the test set — MedVision fits every threshold on validation and reports on test; CareFlow's evaluation sets are never used for training.

**Q: Macro vs weighted F1?**
Macro averages per-class F1 equally (rare classes count as much as common ones); weighted averages by support. MedVision reports macro F1 (0.508) because rare cancers matter.

**Q: What does ROC-AUC measure?**
The probability that a random positive is scored higher than a random negative — threshold-independent ranking quality.
