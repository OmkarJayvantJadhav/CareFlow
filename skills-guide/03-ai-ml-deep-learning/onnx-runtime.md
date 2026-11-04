# ONNX Runtime

## 30-second answer
**ONNX (Open Neural Network Exchange)** is an open file format for ML models — a graph of standard operators — so a model trained in one framework can run in another. **ONNX Runtime** is Microsoft's fast C++ inference engine for ONNX models, with CPU, GPU and other "execution providers". In MedVision AI I exported the trained Keras model with **tf2onnx (opset 17)** and serve it with **ONNX Runtime on CPU — no TensorFlow in the server**: about **30 ms per image**, a **16 MB** model, ~170 MB of memory, and **parity tests** that prove the served outputs match TensorFlow. CareFlow also uses ONNX Runtime indirectly: `fastembed` runs the embedding and re-ranking models as ONNX.

---

## Basics you must know

### Why export to ONNX?
| Benefit | Explanation |
|---|---|
| **Smaller deployment** | `onnxruntime` is tens of MB; TensorFlow is hundreds of MB |
| **Faster CPU inference** | Graph optimisations (constant folding, operator fusion), optimised kernels |
| **Framework-independent** | Train in TF/PyTorch, serve anywhere (Python, C++, C#, Java, JS, mobile) |
| **Hardware options** | Execution providers: CPU, CUDA, TensorRT, DirectML, OpenVINO, CoreML |

### Key concepts
- **Opset:** version of the operator set (MedVision uses 17).
- **Graph inputs/outputs:** named tensors with shapes and dtypes; a dynamic batch dimension is common.
- **InferenceSession:** loads the model once; `session.run(output_names, {input_name: array})`.
- **SessionOptions:** `graph_optimization_level` (`ORT_ENABLE_ALL`), `intra_op_num_threads`, `inter_op_num_threads`.
- **Quantisation:** int8 weights for smaller/faster models (CareFlow's re-ranker is int8).

### Converters
- TensorFlow/Keras → `tf2onnx`
- PyTorch → `torch.onnx.export`
- scikit-learn → `skl2onnx`

### Always check parity
After export, compare outputs of the original and ONNX model on the same inputs (max absolute difference, cosine similarity).

---

## How I used it in MedVision AI

### Export (`ml/src/medvision_ml/export/onnx_export.py`)
The export directory (a GitHub release, e.g. `model-v2.2.0`) contains:
| File | Contents |
|---|---|
| `model.onnx` | Input `image` (N, 224, 224, 3) float32 raw 0–255; outputs **`probabilities`** (N, 8) and **`feature_maps`** (N, 7, 7, 1280) |
| `head_weights.npz` | Dense head `kernel` (1280, 8) and `bias` (8) — for logits and Grad-CAM |
| `ood_stats.npz` | Mean and precision matrix of pooled training features — for the out-of-distribution gate |
| `model_meta.json` | Version, classes, input spec, temperature, fitted thresholds and **SHA-256 checksums** of the other files |

The model has **two outputs on purpose**: from the feature maps the backend derives logits, the OOD distance and the heatmap — all from **one** ONNX call.

### Serving (`backend/app/inference/predictor.py`)
```python
options = ort.SessionOptions()
options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
options.intra_op_num_threads = threads          # 1 on Render's free fraction of a CPU
self.session = ort.InferenceSession(str(onnx_path), options, providers=["CPUExecutionProvider"])
# check the graph's input/output names match model_meta.json

probabilities, feature_maps = self.session.run(
    ["probabilities", "feature_maps"], {"image": batch})
```
- One `Predictor` holds one session, created at start-up in FastAPI's `lifespan`, shared by requests (`session.run` is thread-safe); requests call it via `run_in_threadpool`.
- `MEDVISION_INFERENCE_THREADS=1` and `OMP_NUM_THREADS=1` on the free server: extra threads only fight for the same CPU slice.

### Verified model delivery
- The Dockerfile downloads the release at **build time** (`python -m app.inference.download`) and **fails the build if any SHA-256 checksum doesn't match**.
- `/api/v1/ready` reports ready only when the model loaded and checksums were verified.

### Everything else in NumPy
Preprocessing (a NumPy copy of TensorFlow's bilinear resize), temperature scaling, Mahalanobis distance, noise/quality gates and Grad-CAM are NumPy code, so the backend's dependencies are just FastAPI, Pydantic, ONNX Runtime, NumPy and Pillow.

### Parity tests (`ml/tests/test_export_parity.py`)
They import the backend's inference code and compare it to TensorFlow:
- ONNX vs Keras probabilities;
- NumPy heatmap vs TensorFlow Grad-CAM (cosine ≥ 0.99);
- served resize vs the training input pipeline;
- out-of-distribution and noise scores vs the training-side implementations.

### Numbers
~30 ms/image on a normal CPU, 0.9–2.8 s on Render's ~0.1 CPU; model 16 MB; ~170 MB memory; Docker image ~829 MB measured locally (D43).

## How CareFlow uses it
`fastembed` downloads ONNX versions of `paraphrase-multilingual-MiniLM-L12-v2` (embeddings) and `bge-reranker-v2-m3` (int8 re-ranker) and runs them with ONNX Runtime — no PyTorch in the image.

---

## Interview questions

**Q: Why not serve the Keras model directly?**
TensorFlow is large and slow to start; the free server has 512 MB RAM. ONNX Runtime is smaller, fast on CPU, and removes TensorFlow from the production image.

**Q: How do you know the ONNX model is correct?**
Parity tests compare ONNX and Keras outputs, and NumPy heatmaps with TensorFlow Grad-CAM, in CI. The export step also measures the maximum probability difference.

**Q: Why two outputs?**
The feature maps let me compute logits, Grad-CAM and the OOD distance without a second model or gradients — one forward pass for everything.

**Q: What are execution providers?**
Back-ends ONNX Runtime can use — CPU, CUDA, TensorRT, OpenVINO, etc. I used `CPUExecutionProvider` because the hosting is CPU-only.

**Q: How did you tune performance?**
`ORT_ENABLE_ALL` graph optimisations, one session reused across requests, thread count matched to the CPU quota, and Pillow PNG encoding with fast compression for heatmaps.

**Q: What would you try next?**
Int8 quantisation of the classifier (check accuracy/calibration don't change), batching if traffic grows.
