# Re-ranking

## 30-second answer
Re-ranking is a second, more accurate scoring pass over a small set of candidates from the first retrieval stage. First-stage retrievers (vector search, BM25) are fast but rough; a **cross-encoder** reads the query and each passage *together* and scores relevance much better, but is too slow to run on every document. In CareFlow, the 12 fused candidates go to a **multilingual cross-encoder (BAAI/bge-reranker-v2-m3, int8 ONNX via fastembed)**, scores are squashed to 0–1 with a sigmoid, and anything below a **relevance threshold chosen by 5-fold cross-validation** is not used as a source. On the 512 MB free server a **lexical re-ranker** fallback is used instead.

---

## Basics you must know

### Bi-encoder vs cross-encoder
| | Bi-encoder (embeddings) | Cross-encoder (re-ranker) |
|---|---|---|
| Input | Query and passage encoded **separately** | Query + passage **together** in one input |
| Output | Two vectors → cosine similarity | One relevance score |
| Pre-compute? | Yes, passages embedded once | No, must run per (query, passage) pair |
| Speed | Very fast (vector index) | Slow — only for top-N |
| Accuracy | Good | Better (sees word-level interactions) |

### Two-stage retrieval
```
millions/thousands of docs ──(fast, high recall)──► top 20–100 ──(slow, high precision)──► top 3–5
       first stage: BM25 / vectors                   re-ranker: cross-encoder
```

### Relevance threshold
Re-ranker scores also tell you when **nothing** is relevant. Choosing a cut-off lets the system say "I don't know" instead of answering from a weak passage. The threshold should be chosen on held-out data.

### Other re-rankers
Cohere Rerank (API), ColBERT (late interaction), LLM-as-reranker (expensive), learning-to-rank (LightGBM LambdaMART).

---

## How I built it in CareFlow (`app/rag/rerank.py`)

### Common interface
```python
class Reranker(Protocol):
    name: str
    def score(self, query: str, texts: Sequence[str], prior: Sequence[float]) -> list[float]: ...
```
Scores are always in **[0, 1]** so one threshold logic works for both implementations.

### Neural: `CrossEncoderReranker`
```python
from fastembed.rerank.cross_encoder import TextCrossEncoder
self._model = TextCrossEncoder(model_name="BAAI/bge-reranker-v2-m3-int8", ...)
logits = list(self._model.rerank(query, list(texts)))
return [1.0 / (1.0 + math.exp(-x)) for x in logits]      # sigmoid → 0..1
```
- Multilingual (works for Hindi/Marathi), int8-quantised ONNX for CPU.

### Fallback: `LexicalReranker` ("lexical-v1")
Used when the model can't be downloaded or memory is tight (Render free tier, tests):
- For each query content word, check if the chunk contains it — exact match, same stem, or one stem a prefix of the other (handles inflections like "मुल" / "मुलां").
- Weight each matched word by its **IDF** (rare words count more).
- `score = 0.9 × IDF-weighted coverage + 0.1 × (fused prior / best prior)` — the first-stage score only breaks ties.

### Choosing the backend — `choose_reranker()`
`auto` tries the cross-encoder and falls back to lexical with a warning; `local` forces lexical; `cross-encoder` fails loudly if the model can't load. The neural model is cached per process.

### Threshold — `app/rag/retriever.py`
```python
RELEVANCE_THRESHOLD = {"cross-encoder": 0.15, "lexical-v1": 0.275}
```
The lexical-v1 value was **chosen by 5-fold cross-validation** on the RAG evaluation set (`eval/run_rag.py::threshold_cv`, decision D-54): in each fold, pick the threshold with the best accuracy on 4 folds and score it on the 5th; folds are stratified so answerable and unanswerable questions are spread evenly.

### After re-ranking
- Drop chunks below the threshold.
- Keep only the best chunk per `(doc_key, chunk_index)` — so the English and Hindi copies of the same section don't take two of the four places — with a **+0.05 bonus** for the user's language.
- Return the top 4; swap in the user's-language translation for the citation.

### Why it matters in this project
The threshold is what lets the agent honestly say "the documents don't say" — in the queue-question evaluation, **0 of 4 unanswerable questions** were left with a (wrong) source.

---

## Interview questions

**Q: Why re-rank if you already have hybrid search?**
Hybrid search maximises recall cheaply; the cross-encoder improves precision at the top by reading query and passage together. It is too slow for the whole corpus, so it only sees 12 candidates.

**Q: How did you pick the threshold?**
5-fold cross-validation on a labelled set of answerable and unanswerable questions; the chosen value is stored per re-ranker type because their score distributions differ.

**Q: Why a lexical fallback?**
The neural models need about 1 GB of RAM; the free Render instance has 512 MB. The fallback keeps the feature working, and all published retrieval numbers were measured with the configuration that actually runs in production.

**Q: Why sigmoid the logits?**
Cross-encoder outputs are unbounded logits; sigmoid maps them to 0–1 so a single, interpretable threshold works.

**Q: Latency cost?**
Proportional to number of candidates × passage length. Limiting to 12 candidates and using an int8 ONNX model keeps it small on CPU.
