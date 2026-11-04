# Transfer Learning

## 30-second answer
Transfer learning reuses a model trained on a large dataset (like ImageNet's 1.2 M images) as the starting point for a new task, so you need far less data and compute. In MedVision AI I took **EfficientNet-B0 pretrained on ImageNet**, removed its classifier, added a new head for **8 skin-lesion classes**, and trained in **two stages**: first only the new head with the backbone frozen (lr 1e-4), then **fine-tuned the top 40 backbone layers** with a 10× lower learning rate (1e-5), keeping **BatchNorm frozen**. The best weights by validation loss across both stages are kept.

---

## Basics you must know

### Why it works
Early CNN layers learn generic features (edges, colours, textures) that are useful for almost any image task. Only the later, task-specific layers need to change.

### Two main strategies
| Strategy | What you train | When |
|---|---|---|
| **Feature extraction** | Only the new head; backbone frozen | Small dataset, very different from nothing / quick baseline |
| **Fine-tuning** | Head + some/all backbone layers, with a small learning rate | More data, or the domain differs from ImageNet (medical images do) |

### Standard recipe
1. Load a pretrained backbone with `include_top=False`.
2. Freeze it (`backbone.trainable = False`).
3. Add a new head (pooling → dropout → dense).
4. Train the head until validation loss stops improving.
5. Unfreeze the top N layers, **recompile** with a much lower learning rate, train again.
6. Monitor validation loss and stop early.

### Pitfalls
- **High learning rate when fine-tuning** destroys pretrained features ("catastrophic forgetting").
- **Forgetting to recompile** after changing `trainable` — the change doesn't take effect.
- **BatchNorm layers** updating their statistics on small batches → unstable; keep them in inference mode.
- **Different preprocessing** from what the backbone was trained with.
- **Domain gap:** ImageNet photos vs dermoscopy images — fine-tuning is needed, not just feature extraction.

### Other forms of transfer learning
- NLP: pretrained transformers (BERT, LLMs) fine-tuned or used with prompting.
- Embeddings reused for search — CareFlow's multilingual MiniLM embedder is a pretrained model used as-is for retrieval.
- Domain adaptation, multi-task learning, knowledge distillation.

---

## How I used it in MedVision AI

### Configuration (`ml/configs/skin.yaml`)
```yaml
model:
  backbone: efficientnetb0
  dropout: 0.30
  pretrained: true        # ImageNet weights
training:
  epochs: 50
  learning_rate: 1.0e-4
  fine_tune_epochs: 15
  fine_tune_learning_rate: 1.0e-5
  fine_tune_layers: 40    # final backbone layers unfrozen in stage 2
  class_weighting: sqrt
  mixed_precision: true
  early_stopping_patience: 10
```

### Unfreezing (`ml/src/medvision_ml/models/builder.py`)
```python
def unfreeze_top_layers(model, num_layers):
    backbone = get_backbone(model)
    backbone.trainable = True
    for index, layer in enumerate(backbone.layers):
        layer.trainable = (index >= len(backbone.layers) - num_layers
                           and not isinstance(layer, keras.layers.BatchNormalization))
```
And the backbone is always called with `training=False`, so BatchNorm uses its ImageNet statistics.

### Two stages (`ml/src/medvision_ml/training/trainer.py`)
```python
_compile(model, 1e-4); stage1 = model.fit(...)            # head only
stage1_weights = model.get_weights()
unfreeze_top_layers(model, 40)
_compile(model, 1e-5); stage2 = model.fit(..., initial_epoch=len(stage1.history["loss"]))
if min(stage2.history["val_loss"]) >= min(stage1.history["val_loss"]):
    model.set_weights(stage1_weights)                    # fine-tuning didn't help → keep stage 1
```
`initial_epoch` continues the epoch counter so the logged history is one continuous curve (`history.png`).

### Data and compute
ISIC 2019, 25,331 images, 8 classes, trained on a **Kaggle T4 GPU** with mixed precision via `notebooks/train_kaggle.ipynb`, which only calls the tested `medvision-ml` CLI.

### What's next (roadmap)
Larger backbone, higher resolution and **full fine-tuning** to improve lesion-type accuracy (macro F1 0.508 today), accepted only if malignant recall stays ≥ 0.90.

---

## Interview questions

**Q: Why two stages instead of fine-tuning everything at once?**
The new head starts random. Training everything together would send large, noisy gradients into the pretrained layers and damage them. Training the head first gives sensible gradients before unfreezing.

**Q: Why a 10× lower learning rate in stage 2?**
To adjust pretrained weights gently instead of overwriting them.

**Q: Why not unfreeze the whole backbone?**
With ~25k images, unfreezing only the top layers adapts high-level features to dermoscopy while keeping generic low-level features; it's also faster. Full fine-tuning is on the roadmap with a stronger setup.

**Q: Is ImageNet a good source for medical images?**
The domains differ, but low-level features still transfer, and pretrained starts consistently beat training from scratch on datasets of this size. Fine-tuning closes part of the domain gap.

**Q: How do you know fine-tuning helped?**
The trainer compares the best validation loss of stage 2 with stage 1 and restores stage-1 weights if stage 2 didn't improve.
