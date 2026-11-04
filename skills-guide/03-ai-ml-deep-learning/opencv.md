# OpenCV

## Where it fits in my work (say this honestly)
**OpenCV (`cv2`) is not imported in CareFlow or MedVision.** MedVision does several classic OpenCV-style image operations, but I implemented them with **Pillow and NumPy** on purpose: the server must reproduce TensorFlow's preprocessing *exactly* (verified by parity tests) and the Docker image should stay small. So I can explain the OpenCV way and why I chose NumPy.

> If asked "where did you use OpenCV?" → "In MedVision I needed blur detection, noise estimation, resizing and heatmap overlays. Those are standard OpenCV operations — `cv2.Laplacian(...).var()`, `cv2.resize`, `cv2.applyColorMap`, `cv2.addWeighted` — but I wrote them in NumPy so the served preprocessing matches TensorFlow's training pipeline exactly and the image has no OpenCV dependency. I've used OpenCV itself for <your coursework/practice project>."

---

## 30-second answer
OpenCV is the most widely used open-source computer-vision library (C++ core, Python bindings). It reads/writes images and video, converts colour spaces, filters, detects edges and contours, does geometric transforms, feature detection, camera calibration and runs DNN models. Images are NumPy arrays in **BGR** order by default.

---

## Basics you must know

### Reading and showing
```python
import cv2
img = cv2.imread("lesion.jpg")              # BGR, uint8, shape (H, W, 3)
rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
cv2.imwrite("out.png", img)
```
**Gotcha:** OpenCV uses BGR; Pillow, Matplotlib and TensorFlow use RGB.

### Common operations
| Task | OpenCV | MedVision's NumPy/Pillow equivalent |
|---|---|---|
| Resize | `cv2.resize(img, (w, h), interpolation=cv2.INTER_LINEAR)` | `resize_bilinear` — exact copy of TensorFlow's bilinear resize (`backend/app/inference/preprocessing.py`) |
| Grayscale | `cv2.cvtColor(..., COLOR_BGR2GRAY)` | `rgb @ [0.299, 0.587, 0.114]` (ITU-R BT.601 luma) in `quality.py` |
| **Blur detection** | `cv2.Laplacian(gray, cv2.CV_64F).var()` | `laplacian_variance()` — 4-neighbour Laplacian with array slicing |
| Noise estimate | Custom filter with `cv2.filter2D` | `noise_level()` — Immerkaer's 3×3 mask, per 8×8 block, 5th percentile |
| Colour map | `cv2.applyColorMap(heat, cv2.COLORMAP_JET)` | `jet()` closed-form colour map in `cam.py` |
| Overlay | `cv2.addWeighted(img, 0.6, heat, 0.4, 0)` | `blend(image, coloured, alpha=0.4)` |
| EXIF rotation | (manual) | `ImageOps.exif_transpose` (Pillow) |
| Encode PNG | `cv2.imencode(".png", img)` | Pillow `save(format="PNG", compress_level=1)` |

### Filtering and edges
- Smoothing: `GaussianBlur`, `medianBlur` (salt-and-pepper noise), `bilateralFilter` (edge-preserving).
- Edges: `Sobel`, `Laplacian`, `Canny`.
- Thresholding: `threshold`, Otsu's method, `adaptiveThreshold`.
- Morphology: `erode`, `dilate`, opening/closing (e.g. removing hair in dermoscopy — the "DullRazor" approach).
- Contours: `findContours`, `contourArea`, `boundingRect` — lesion segmentation basics.

### Geometric transforms
`warpAffine` (rotate/scale/translate), `warpPerspective`, `flip`.

### Video
`cv2.VideoCapture(0)` → read frames in a loop.

### DNN module
`cv2.dnn.readNetFromONNX("model.onnx")` can run ONNX models — an alternative to ONNX Runtime.

---

## Why the Laplacian-variance blur check works (asked often)
The Laplacian is a second-derivative filter that responds to rapid intensity changes (edges). A sharp image has strong edges → high variance of the Laplacian response; a blurry image has weak edges → low variance. MedVision rejects an image when the variance is below a fixed bound (`min_sharpness`).

```python
def laplacian_variance(gray):
    lap = gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:] - 4 * gray[1:-1, 1:-1]
    return float(lap.var())
```

## Why the noise gate looks at the *smoothest* patches
Hair and pigment texture create high-frequency signal that a naive noise estimate would count as noise. MedVision measures Immerkaer's noise response per 8×8 block and takes the **5th percentile**, i.e. the calmest blocks, where only sensor noise remains. This gate cut silent misses on noisy images from up to 49% to 0%.

---

## Interview questions

**Q: Why might you avoid OpenCV in a serving container?**
Size and exactness: `opencv-python` adds tens of MB plus system libraries, and its resize differs slightly from TensorFlow's; a model is most accurate when serving preprocessing matches training preprocessing exactly.

**Q: BGR vs RGB — why does it matter?**
Feeding BGR to a model trained on RGB swaps red and blue channels and silently hurts accuracy.

**Q: How would you detect a blurry image?**
Variance of the Laplacian below a threshold.

**Q: How would you segment a lesion with classic CV?**
Grayscale → Gaussian blur → Otsu threshold → morphological opening/closing → largest contour.
