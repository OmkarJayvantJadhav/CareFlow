# Grad-CAM

## 30-second answer
**Grad-CAM (Gradient-weighted Class Activation Mapping)** explains a CNN's prediction with a heatmap of the image regions that most increased the score for a class. It takes the last convolutional feature maps, weights each channel by the average gradient of the class score with respect to it, sums them, and applies ReLU. In MedVision AI I noticed that for a **global-average-pool → dense** head, those gradients are exactly the dense layer's weights, so Grad-CAM reduces to **`ReLU(Σ_k W[k,c] · A_k)`**. That lets the backend compute the heatmap in **plain NumPy from the same ONNX forward pass** — no TensorFlow, no gradients, nearly free — and a **parity test** proves it matches TensorFlow Grad-CAM (cosine similarity ≥ 0.99).

---

## Basics you must know

### The algorithm
For an image, class *c*, last conv feature maps **A** with shape *(h, w, K)*:
1. Score `y_c` — use the **pre-softmax logit**.
2. Gradients `∂y_c / ∂A_k` for every channel *k* (with `tf.GradientTape`).
3. Channel weights: `α_k = mean over (i, j) of ∂y_c / ∂A_k(i, j)` (global average of the gradients).
4. Heatmap: `L_c = ReLU(Σ_k α_k · A_k)` → *(h, w)*.
5. Normalise to [0, 1], upsample to the image size (bilinear), colour (e.g. "jet") and overlay.

**ReLU** keeps only regions that *increase* the class score.

### CAM vs Grad-CAM
- **CAM** (2016) needs a GAP → dense architecture: heatmap = `Σ_k W[k,c] · A_k`.
- **Grad-CAM** (2017) generalises CAM to any architecture via gradients.
- For a GAP → dense head they are the same up to a positive constant — which is the trick MedVision uses.

### Why the equivalence holds
With `pooled_k = (1 / (h·w)) Σ_ij A_k(i,j)` and `y_c = Σ_k W[k,c] · pooled_k + b_c`:  
`∂y_c / ∂A_k(i,j) = W[k,c] / (h·w)` at every position, so `α_k = W[k,c] / (h·w)` and  
`Grad-CAM_c = ReLU(Σ_k W[k,c] · A_k) / (h·w)`. After normalising to [0,1] the constant disappears.

### Limitations (say these in interviews)
- Coarse: resolution of the last feature map (7×7 for EfficientNet-B0 at 224 px), then upsampled.
- Shows *where* the model looked, not *why*, and not proof of correctness — a heatmap on a ruler or hair means the model may use a shortcut.
- Not a segmentation of the lesion or of cancer.
- Alternatives: Grad-CAM++, Score-CAM, Integrated Gradients, SHAP, LIME, attention maps.

---

## How I used it in MedVision AI

### Reference implementation with TensorFlow (`ml/src/medvision_ml/explainability/gradcam.py`)
Uses `tf.GradientTape` on the logit, exactly as in the paper. It checks the model has exactly one Dense layer and a `GlobalAveragePooling2D` head (otherwise the shortcut is invalid). Used for tests and for figures.

### Serving implementation in NumPy (`backend/app/inference/cam.py`)
```python
def cam_from_features(feature_maps, kernel, class_index):
    cam = np.tensordot(feature_maps.astype(np.float32),          # (7, 7, 1280)
                       kernel[:, class_index].astype(np.float32),  # (1280,)
                       axes=([2], [0]))                            # → (7, 7)
    cam = np.maximum(cam, 0.0)                                     # ReLU
    peak = float(cam.max())
    return cam / peak if peak > 0 else np.zeros_like(cam)          # normalise to [0, 1]
```
Then:
- `resize_bilinear` (a NumPy re-implementation of TensorFlow's bilinear resize) upsamples 7×7 to the image size;
- `jet()` maps values to RGB with a closed-form "jet" colour map: `clip(1.5 − |4v − [3, 2, 1]|, 0, 1)`;
- `blend(image, coloured, alpha=0.4)` overlays it;
- `encode_png` uses Pillow with `compress_level=1` (≈10× faster than `optimize=True` for a few % larger files).

### Where the inputs come from
- The ONNX model has two outputs: `probabilities` and **`feature_maps`** (7×7×1280).
- The dense layer's `kernel` (1280×8) and `bias` ship in `head_weights.npz` with the model release.
- So **one ONNX call** gives logits, out-of-distribution distance **and** the heatmap.

### API and UI
- `POST /api/v1/explain` returns the prediction plus `heatmap_png` and `overlay_png` (base64); `?class_name=` explains a different class.
- `HeatmapViewer.jsx` lets the user switch the highlight off or change its strength.
- The UI and model card state clearly: the heatmap shows where the model looked; **it is not a diagnosis or an outline of cancer**.

### Parity test (`ml/tests/test_export_parity.py`)
Exports a model, runs the backend's NumPy heatmap and the TensorFlow Grad-CAM on the same image, and requires **cosine similarity ≥ 0.99**. It runs in CI.

---

## Interview questions

**Q: Explain Grad-CAM in two sentences.**
Weight each channel of the last conv layer by the average gradient of the class logit with respect to it, sum the weighted channels and apply ReLU. The result is a coarse heatmap of regions that pushed the score up.

**Q: How did you compute Grad-CAM without TensorFlow at serving time?**
For a GAP → dense head the averaged gradients equal the dense weights divided by h·w, so the heatmap is `ReLU(feature_maps @ W[:, c])`. I export the feature maps from ONNX and ship the dense weights, then compute it in NumPy — and a parity test confirms it matches TensorFlow's Grad-CAM.

**Q: Why use the logit and not the softmax probability?**
Softmax couples all classes, so gradients of a probability can be negative because other classes grow; the logit gives a cleaner, class-specific signal (and makes the closed-form equivalence exact).

**Q: Why ReLU?**
To show only features with a positive influence on the class; negative regions are evidence for other classes.

**Q: What are Grad-CAM's limitations?**
Low resolution, can highlight spurious cues, shows correlation not causation, and must not be read as a lesion boundary or a diagnosis.

**Q: How does it help build trust?**
A clinician can check the model looked at the lesion, not at hair, rulers or the dark dermoscopy border — and spot shortcuts.
