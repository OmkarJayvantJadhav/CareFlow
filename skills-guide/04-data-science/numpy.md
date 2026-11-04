# NumPy

## 30-second answer
NumPy is Python's library for fast n-dimensional arrays: a contiguous typed buffer with **vectorised** operations implemented in C, **broadcasting**, linear algebra and random numbers. It underpins pandas, scikit-learn, TensorFlow and ONNX Runtime. In MedVision AI the **entire serving-side math is NumPy**: bilinear resizing identical to TensorFlow's, temperature-scaled softmax, Mahalanobis out-of-distribution distance, blur and noise gates, and **Grad-CAM with one `np.tensordot`**. In CareFlow, NumPy feeds the LightGBM wait-time model, normalises embedding vectors for pgvector and sorts BM25 scores.

---

## Basics you must know

### Arrays
```python
import numpy as np
a = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.float32)
a.shape   # (2, 3)
a.ndim    # 2
a.dtype   # float32
np.zeros((3, 4)), np.ones(5), np.arange(0, 10, 2), np.linspace(0, 1, 5), np.eye(3)
```

### Indexing and slicing
- `a[0, 1]`, `a[:, 1]` (column), `a[1:, ::2]`.
- **Boolean masks:** `a[a > 2]`.
- **Fancy indexing:** `probs[rows, targets]` picks one element per row (MedVision's NLL).
- Slices are **views** (no copy); fancy/boolean indexing returns **copies**.

### Vectorisation
Replace Python loops with whole-array operations: `x * 2 + 1`, `np.exp(x)`, `x.sum(axis=1)`. Typically 10–100× faster.

### Broadcasting rules
Compare shapes from the right; dimensions are compatible if equal or one of them is 1.
```python
scores - scores.max(axis=1, keepdims=True)    # (n, C) − (n, 1) → (n, C)
```
`keepdims=True` keeps the reduced axis so broadcasting works.

### Reductions and axes
`sum`, `mean`, `max`, `argmax`, `std`, `var`, `percentile`, `quantile`, `cumsum` — `axis=0` reduces rows (per column), `axis=1` reduces columns (per row).

### Shape manipulation
`reshape`, `ravel`, `transpose` / `.T`, `np.newaxis`, `squeeze`, `expand_dims`, `concatenate`, `stack`.

### Linear algebra
`@` (matmul), `np.dot`, `np.tensordot`, `np.linalg.norm`, `np.linalg.inv`, `np.linalg.pinv`, `np.trace`, `np.eye`.

### Numerical stability
- **Softmax/log-softmax:** subtract the row max before `exp` to avoid overflow.
- Use `float64` for statistics that need precision (covariance, NLL).

### Random
`rng = np.random.default_rng(seed)`; `rng.uniform`, `rng.normal`, `rng.permutation`.

---

## How I used it

### MedVision AI — serving without TensorFlow (`backend/app/inference/`)
| Function | NumPy technique |
|---|---|
| `cam_from_features` (Grad-CAM) | `np.tensordot(feature_maps (7,7,1280), kernel[:, c] (1280,), axes=([2],[0]))` → (7,7); `np.maximum(cam, 0)` for ReLU |
| `logits_from_features` | `feature_maps.mean(axis=(1, 2)) @ kernel + bias` |
| `softmax(logits / T)` | Stable: subtract the max, `exp`, divide by the sum |
| `mahalanobis_distance` | `d = x − μ`, `d @ P @ d` with a precision matrix |
| `laplacian_variance` | Laplacian with **shifted slices** `gray[:-2,1:-1] + gray[2:,1:-1] + … − 4*gray[1:-1,1:-1]`, then `.var()` |
| `noise_level` | 3×3 Immerkaer mask via slices, `reshape(rows, 8, cols, 8).mean(axis=(1, 3))` for 8×8 block means, `np.percentile(means, 5)` |
| `grayscale` | `rgb @ np.array([0.299, 0.587, 0.114])` |
| `resize_bilinear` | Precomputed axis weights to copy TensorFlow's bilinear resize exactly |
| `jet` colour map | `np.clip(1.5 − np.abs(4 * v − [3, 2, 1]), 0, 1)` with broadcasting |

### MedVision AI — training side (`ml/src/medvision_ml/`)
- **Temperature fitting** (`calibration/fitting.py`): stable `_log_softmax`, golden-section search over log T, NLL via fancy indexing `[rows, targets]`.
- **Confidence threshold:** `np.argsort(-confidence)`, `np.cumsum(correct[order]) / np.arange(1, n+1)` = running accuracy of the k most confident predictions.
- **OOD Gaussian** (`calibration/ood.py`): mean, covariance `centred.T @ centred / n`, **shrinkage** towards `trace/d · I`, inverse with `np.linalg.pinv(..., hermitian=True)`.
- **Perceptual hashing** (`data/hashing.py`): `pixels[:, 1:] > pixels[:, :-1]` → 256-bit difference hash; Hamming distances on packed `uint64` arrays.

### CareFlow
- **LightGBM input:** `np.array([r.features for r in rows], dtype=np.float64)` (`app/ml/model.py`).
- **Training metrics:** MAE, P90 error with `np.percentile`, coverage with `np.mean((actual >= low) & (actual <= high))`, conformal adjustments with `np.quantile` (`app/ml/train.py`).
- **Embeddings:** `_normalize_rows` → `matrix / np.linalg.norm(matrix, axis=1, keepdims=True)` so cosine similarity = dot product.
- **BM25 ranking:** `np.argsort(-scores)`.

---

## Interview questions

**Q: Why is NumPy faster than Python lists?**
Contiguous memory of one dtype and loops in compiled C (with SIMD), instead of Python objects and interpreted loops.

**Q: What is broadcasting?**
Automatic expansion of dimensions of size 1 so arrays of different shapes can be combined without copying — e.g. subtracting a per-row max of shape (n, 1) from (n, C).

**Q: View vs copy?**
Basic slicing returns a view sharing memory; fancy or boolean indexing returns a copy. Modifying a view modifies the original.

**Q: How do you compute a stable softmax?**
Subtract the maximum logit per row before exponentiating; the result is identical mathematically but avoids overflow.

**Q: How did you compute Grad-CAM with NumPy?**
`np.tensordot` of the (7, 7, 1280) feature maps with the dense weights for class c over the channel axis, then ReLU and normalisation.

**Q: Why `pinv` instead of `inv` for the precision matrix?**
The covariance of 1,280-d features can be near-singular; shrinkage plus the pseudo-inverse keeps it numerically stable.
