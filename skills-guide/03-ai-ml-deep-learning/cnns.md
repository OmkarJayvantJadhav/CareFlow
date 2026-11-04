# CNNs (Convolutional Neural Networks)

## 30-second answer
A CNN is a neural network for grid-shaped data like images. Convolution layers slide small learned filters over the image to detect local patterns (edges → textures → shapes → objects), sharing the same weights across positions, and pooling reduces spatial size. MedVision AI uses the CNN **EfficientNet-B0**: a 224×224 dermoscopy image goes through the network to a **7×7×1280 feature map**, which is **global-average-pooled** to 1,280 numbers and passed to a **dense layer** that scores 8 lesion types. That last feature map is also what powers the Grad-CAM heatmap and the out-of-distribution detector.

---

## Basics you must know

### Why not a plain fully-connected network?
A 224×224×3 image has 150,528 inputs; a dense layer would need millions of weights per neuron and ignore that nearby pixels are related. Convolutions use **local connectivity** and **weight sharing**, giving far fewer parameters and **translation equivariance** (a lesion is detected wherever it is).

### Building blocks
| Layer | What it does | Key parameters |
|---|---|---|
| **Convolution** | Dot product of a k×k filter with each image patch → feature map | Filters, kernel size, stride, padding |
| **Activation** | Non-linearity: ReLU `max(0, x)`, Swish/SiLU (EfficientNet) | — |
| **Pooling** | Downsample: max or average | Pool size, stride |
| **Batch normalisation** | Normalises activations per batch → faster, stabler training | Momentum, epsilon |
| **Dropout** | Randomly zeroes units during training → less overfitting | Rate (0.3 in MedVision) |
| **Global average pooling** | Averages each channel over all positions → one number per channel | — |
| **Dense** | Fully connected classifier head | Units = number of classes |

### Output size of a convolution
`out = floor((in + 2·padding − kernel) / stride) + 1`

### Parameters in a conv layer
`(k × k × C_in + 1) × C_out` — e.g. a 3×3 conv from 32 to 64 channels has (9·32 + 1)·64 = 18,496.

### Receptive field
Deeper layers "see" larger parts of the image, so they detect bigger, more abstract patterns.

### Famous architectures
LeNet → AlexNet (ReLU, GPUs) → VGG (stacked 3×3) → **ResNet** (skip connections, very deep) → Inception → MobileNet (depthwise separable convs, mobile) → **EfficientNet** (compound scaling) → ConvNeXt (modernised CNN). Vision Transformers (ViT) are the main non-CNN alternative.

### EfficientNet in one paragraph
Built from **MBConv** blocks (inverted residuals with depthwise separable convolutions and squeeze-and-excitation channel attention) using the Swish activation. **Compound scaling** grows depth, width and input resolution together with fixed ratios; B0 is the smallest base model (~5.3 M parameters) — accurate and cheap enough for CPU serving.

### Softmax and logits
The dense layer outputs **logits** (unbounded scores); **softmax** turns them into probabilities that sum to 1: `p_i = exp(z_i) / Σ exp(z_j)`.

---

## How I used it in MedVision AI

### Architecture (`ml/src/medvision_ml/models/builder.py`)
```
image (224×224×3, raw 0–255)
  → augmentation (flip, rotation, zoom, contrast — training only)
  → EfficientNet-B0 backbone (ImageNet weights, include_top=False)   → feature maps 7×7×1280
  → GlobalAveragePooling2D "pool"                                    → 1280
  → Dropout(0.3)
  → Dense(8) "logits"
  → Softmax (float32) "probabilities"
```
224 / 32 = 7 — EfficientNet downsamples by 32, giving the 7×7 grid.

### Why the head is deliberately simple
With **GAP → Dense**, the class score is a weighted sum of channel averages. That means Grad-CAM for class *c* is exactly `ReLU(Σ_k W[k,c] · A_k)` — computable in NumPy from the feature maps and the dense weights, no gradients needed at serving time. See [Grad-CAM](grad-cam.md).

### One forward pass, three uses
The exported ONNX model returns both `probabilities` and `feature_maps`. From the 7×7×1280 feature maps the backend derives:
1. **Logits** = mean(feature maps) @ kernel + bias → temperature-scaled probabilities.
2. **Out-of-distribution distance** = Mahalanobis distance of the pooled 1,280-d vector from the training features.
3. **Heatmap** = ReLU(feature maps @ kernel[:, c]).

### Other CNN backbones supported by config
`efficientnetv2s`, `convnext_tiny`, `mobilenetv2` (`ml/configs/skin.yaml`); the roadmap plans a larger backbone at higher resolution for better lesion-type accuracy.

---

## Interview questions

**Q: What does a convolution layer learn?**
A set of filters; early layers learn edges and colours, deeper layers learn textures and shapes specific to the task (lesion borders, pigment networks).

**Q: Why global average pooling instead of flatten?**
Far fewer parameters, works with any spatial size, less overfitting, and it keeps a direct link between channels and class scores — which makes CAM/Grad-CAM straightforward.

**Q: What are depthwise separable convolutions?**
A depthwise conv (one filter per input channel) followed by a 1×1 pointwise conv — similar expressiveness with ~8–9× fewer computations for 3×3 kernels. Used in MobileNet and EfficientNet.

**Q: Why EfficientNet-B0?**
Good accuracy per parameter, small ONNX file (16 MB), ~30 ms per image on CPU — fits a free 512 MB server.

**Q: What is batch normalisation?**
Normalising each channel's activations by the batch mean and variance, then scaling and shifting with learned parameters; it stabilises and speeds up training.

**Q: Where does overfitting show up and how did you fight it?**
Gap between train and validation loss. I used augmentation, dropout 0.3, a frozen backbone first, low fine-tuning learning rate, frozen BatchNorm and early stopping on validation loss.
