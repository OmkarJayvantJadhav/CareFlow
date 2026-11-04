# TensorFlow / Keras

## 30-second answer
TensorFlow is Google's deep-learning framework (tensors, automatic differentiation, GPU execution, `tf.data` input pipelines); **Keras** is its high-level API for building and training models (`keras.Model`, layers, `compile`, `fit`, callbacks). In MedVision AI I used **TensorFlow 2.18–2.20 with Keras 3** to fine-tune **EfficientNet-B0** on **ISIC 2019** (25,331 images, 8 classes) on a Kaggle T4 GPU: a `tf.data` pipeline, built-in augmentation layers, **two-stage fine-tuning**, **square-root class weights**, **mixed precision**, and callbacks for early stopping, checkpoints and learning-rate reduction. TensorFlow is used **only for training** — the served model runs on ONNX Runtime without TensorFlow.

---

## Basics you must know

### Tensors and autodiff
- A **tensor** is an n-dimensional array with a dtype and shape (`(32, 224, 224, 3)` = batch of 32 RGB images).
- **`tf.GradientTape`** records operations so gradients can be computed — the basis of backpropagation (and of Grad-CAM's reference implementation).
- **Eager** execution by default; `@tf.function` compiles to a graph for speed.

### Three ways to build a Keras model
1. **Sequential** — a stack of layers (MedVision's augmentation block is `keras.Sequential`).
2. **Functional API** — `inputs = keras.Input(...)`, chain layers, `keras.Model(inputs, outputs)` — supports branches and nested models (MedVision's classifier).
3. **Subclassing** — `class MyModel(keras.Model)` with `call()`.

### Training loop pieces
- `model.compile(optimizer, loss, metrics)`.
- `model.fit(train_ds, validation_data=val_ds, epochs, class_weight, callbacks)`.
- `model.evaluate`, `model.predict`.
- **Loss for integer labels:** `SparseCategoricalCrossentropy`; for one-hot labels: `CategoricalCrossentropy`.
- **Optimizer:** Adam (adaptive learning rates).

### Callbacks
`EarlyStopping`, `ModelCheckpoint`, `ReduceLROnPlateau`, `CSVLogger`, `TensorBoard`.

### `tf.data`
`image_dataset_from_directory` → `.cache()` → `.shuffle()` → `.batch()` → `.prefetch(tf.data.AUTOTUNE)` so the GPU never waits for data.

### Overfitting tools
Data augmentation, dropout, weight decay, early stopping, freezing pretrained layers, more data.

### Mixed precision
`keras.mixed_precision.set_global_policy("mixed_float16")` computes in float16 on GPUs with Tensor Cores (faster, less memory) while keeping weights in float32; keep the final softmax in float32 for numerical stability.

### Saving
Keras 3 native format `model.keras`; weights-only `.weights.h5`; export for serving (SavedModel, ONNX via `tf2onnx`, TFLite).

---

## How I used it in MedVision AI (`ml/src/medvision_ml/`)

### Model — `models/builder.py` (Functional API with a nested backbone)
```python
base = keras.applications.EfficientNetB0(include_top=False, weights="imagenet", input_shape=(224, 224, 3))
backbone = keras.Model(base.input, base.output, name="backbone")
backbone.trainable = False

inputs = keras.Input(shape=(224, 224, 3), name="image")       # raw 0–255 pixels
x = build_augmentation(config)(inputs)                         # RandomFlip, RandomRotation(0.15), RandomZoom(0.2), RandomContrast(0.15)
x = backbone(x, training=False)                                # → (7, 7, 1280) feature maps
x = keras.layers.GlobalAveragePooling2D(name="pool")(x)
x = keras.layers.Dropout(0.30, name="dropout")(x)
logits = keras.layers.Dense(num_classes, name="logits")(x)
probabilities = keras.layers.Activation("softmax", dtype="float32", name="probabilities")(logits)
```
- Augmentation layers are **inside the model** and only active during training (Keras disables them in inference).
- EfficientNet includes its own input normalisation, so the model takes raw 0–255 pixels.
- The fixed layout `pool → dropout → logits` is what makes Grad-CAM computable with NumPy later.
- Also supported via config: EfficientNetV2-S, ConvNeXt-Tiny, MobileNetV2.

### Training — `training/trainer.py` (two stages)
| | Stage 1 | Stage 2 |
|---|---|---|
| Trainable | Head only (backbone frozen) | Top **40** backbone layers, **BatchNorm stays frozen** |
| Learning rate | 1e-4 | 1e-5 |
| Max epochs | 50 | 15 |
- Compile: `Adam`, `SparseCategoricalCrossentropy`, metric `accuracy`.
- **Class weights** (`training/class_weights.py`): square root of "balanced" weights, rescaled so the sample-weighted mean is 1.
- If stage 2 doesn't improve validation loss, the stage-1 weights are restored.
- **Callbacks** (`training/callbacks.py`): `EarlyStopping(patience=10, restore_best_weights=True)`, `ModelCheckpoint(save_best_only=True)`, `ReduceLROnPlateau(factor=0.5, patience=4, min_lr=1e-7)`, `CSVLogger` — all on `val_loss`.
- **Mixed precision** only when a GPU is present (it is slower on CPU).
- **Reproducibility:** `set_seed(42)` for Python, NumPy and TensorFlow.

### Data pipeline — `data/dataset.py`
- `tf.keras.utils.image_dataset_from_directory` with one folder per class, loaded as single images so cache and shuffle work per image.
- `.cache()` to RAM or to disk; the **cache file name is a hash of every file's name, size and modification time** — `tf.data` silently reuses an old cache otherwise, which would train on a previous split.
- `.shuffle(..., reshuffle_each_iteration=True)`, `.prefetch(AUTOTUNE)`.

### A real bug I found
A **mixed-precision model rebuilt in float32 and loaded with `set_weights` silently lost its input normalisation** (validation accuracy dropped 0.695 → 0.646). Loading through Keras's own `load_weights` fixed it, and a regression test guards it (`models/io.py`).

### Export
`tf2onnx` (opset 17) exports two outputs, `probabilities` and `feature_maps`. Parity tests compare ONNX output with Keras. See [ONNX Runtime](onnx-runtime.md).

### Results (test split, 2,527 images)
Accuracy 0.708 · ROC-AUC 0.935 · macro F1 0.508 · ECE 0.026 after calibration · malignant recall at the alert 0.904.

---

## Interview questions

**Q: Sequential vs Functional API?**
Sequential is a single chain. Functional allows multiple inputs/outputs, nested models and named layers — I needed a nested `backbone` and named `pool`/`logits` layers for Grad-CAM and export.

**Q: Why freeze BatchNorm during fine-tuning?**
Updating BatchNorm statistics with small batches from a small medical dataset destabilises the pretrained features. Keeping them frozen keeps ImageNet statistics.

**Q: How did you handle class imbalance?**
ISIC 2019 is dominated by nevus (1,286 of 2,527 test images). I used square-root balanced class weights — most of the minority-recall gain of full balancing with much less loss of overall accuracy.

**Q: Why `SparseCategoricalCrossentropy`?**
Labels are integer class ids from `image_dataset_from_directory`, not one-hot vectors.

**Q: Why is the softmax layer float32?**
Under mixed precision, float16 softmax can overflow/underflow; keeping the output in float32 is the recommended practice.

**Q: How do you prevent the GPU from waiting for data?**
`cache` + `prefetch(AUTOTUNE)` in `tf.data`, so the next batch is ready while the GPU trains on the current one.
