# Hugging Face

## 30-second answer
Hugging Face is the main open-source AI platform: the **Hub** hosts models, datasets and demo apps (**Spaces**), and the libraries (`transformers`, `datasets`, `sentence-transformers`, `huggingface_hub`, `tokenizers`) make them easy to use. In my projects: CareFlow's retrieval models — the multilingual embedding model **`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`** and the re-ranker **`BAAI/bge-reranker-v2-m3`** — are open models **downloaded from the Hugging Face Hub** (through the `fastembed` library, which runs them with ONNX Runtime). MedVision AI was **first deployed to a Hugging Face Docker Space** with `huggingface_hub`, before moving to Render when Docker Spaces on free CPU started requiring a PRO plan.

> Be precise in interviews: I did not use the `transformers` library or fine-tune a Hugging Face model in these projects. I used **models from the Hub** and **Spaces** for deployment.

---

## Basics you must know

### The Hub
- Git-based repositories for **models**, **datasets** and **Spaces**, each with a model/dataset card (README) describing intended use, licence, limitations.
- Model ids look like `organisation/model-name` (e.g. `BAAI/bge-reranker-v2-m3`).
- Files are downloaded and cached locally (`~/.cache/huggingface`, or a custom cache dir).

### Key libraries
| Library | Purpose |
|---|---|
| `transformers` | Load/run/fine-tune transformer models: `AutoTokenizer`, `AutoModel`, `pipeline("sentiment-analysis")` |
| `sentence-transformers` | Sentence embeddings and cross-encoders for search |
| `datasets` | Load and process datasets efficiently (Arrow-backed) |
| `tokenizers` | Fast tokenisers (BPE, WordPiece, SentencePiece) |
| `huggingface_hub` | Download/upload files, manage repos and Spaces (`hf_hub_download`, `upload_folder`) |
| `accelerate`, `peft` | Multi-GPU training, parameter-efficient fine-tuning (LoRA) |
| Optimum / ONNX exports | Run models with ONNX Runtime for faster CPU inference |

### Spaces
Host demos with **Gradio**, **Streamlit**, or any **Docker** image. Defaults: the container runs as uid 1000 on port 7860.

### Model cards and licences
Always check the licence (Apache-2.0, MIT, CC BY-NC, Llama licence…) before commercial use.

---

## How I used it

### CareFlow — retrieval models from the Hub (`app/rag/`, `app/config.py`)
```python
embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"   # 384-d, 50+ languages
reranker_model:  str = "BAAI/bge-reranker-v2-m3-int8"                                # multilingual cross-encoder
```
- Loaded with **fastembed** (`TextEmbedding`, `TextCrossEncoder`), which downloads ONNX versions from the Hub and runs them with ONNX Runtime — no PyTorch, so the Docker image stays small.
- `python -m app.rag.preload` downloads them ahead of time; the Dockerfile can bake them in with `--build-arg PRELOAD_MODELS=true` so cold starts don't download.
- `MODEL_CACHE_DIR` controls where they are cached.
- **Fallback when the Hub is unreachable or RAM is limited:** README — "Without access to Hugging Face, set `EMBEDDING_BACKEND=local` and `RERANKER_BACKEND=local`" — switches to a scikit-learn LSA embedder and a lexical re-ranker. The free Render instance (512 MB) uses these, because the neural models need ~1 GB.
- Why these models: both are **multilingual** (English, Hindi, Marathi) and small enough for CPU.

### MedVision — Hugging Face Spaces (decision D43 → D44 in `docs/PROJECT_PLAN.md`)
- The Docker image was designed for a Space: **uid 1000, port 7860** are Hugging Face's defaults (still used in the Dockerfile).
- A deploy workflow uploaded the app with **`huggingface_hub.upload_folder`** (it handles binary sample images that a plain git push to a Space rejects), waited for the Space to rebuild and report `RUNNING`, then smoke-tested the live URL.
- **Moved to Render** (D44) because Hugging Face began requiring PRO for Docker Spaces on free CPU, and the project rule was free hosting.

---

## Interview questions

**Q: What is the Hugging Face Hub?**
A Git-based hosting platform for models, datasets and demo apps, with model cards, versioning and libraries to download and run them.

**Q: Bi-encoder from the Hub vs cross-encoder from the Hub — how did you use each?**
The MiniLM model is a bi-encoder: it embeds chunks once and queries at search time (pgvector). The BGE re-ranker is a cross-encoder: it scores each (query, chunk) pair for the top 12 candidates.

**Q: Why fastembed instead of `sentence-transformers`?**
fastembed runs ONNX models on ONNX Runtime without PyTorch — much smaller image and faster CPU start-up, which matters on a free 512 MB server.

**Q: What is a Space and why did you leave it?**
A hosted app (Gradio, Streamlit or Docker). Docker Spaces on free CPU began requiring PRO, so I moved to Render's free Docker web service using a `render.yaml` Blueprint.

**Q: How would you fine-tune a Hugging Face model?**
`AutoTokenizer` + `AutoModelForSequenceClassification`, a `datasets` dataset, `Trainer` with `TrainingArguments`, or LoRA via `peft` for large models; evaluate on a held-out split; push to the Hub with a model card.
