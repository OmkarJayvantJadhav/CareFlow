# Hybrid Search

## 30-second answer
Hybrid search combines **dense (semantic) vector search** with **sparse (keyword) search like BM25**, because each misses things the other catches. In CareFlow, each query runs a **pgvector cosine search** and a **BM25 search** (top 20 each), and the two ranked lists are merged with **Reciprocal Rank Fusion (RRF, k = 60)** into 12 candidates that go to the re-ranker. This is part of the pipeline that reached 85.9% recall@5.

---

## Basics you must know

### Dense vs sparse
| | Dense (embeddings) | Sparse (BM25 / TF-IDF) |
|---|---|---|
| Represents text as | 384-d float vector of meaning | Word counts weighted by rarity |
| Good at | Paraphrases, synonyms, cross-language | Exact terms, names, codes, rare words ("HbA1c", "Dr. Pawar") |
| Weak at | Exact tokens, numbers, new jargon | Synonyms ("cost" vs "fee") |
| Storage | Vector index (HNSW, IVF) | Inverted index |

### BM25 in one formula
For each query term *t* in document *d*:

score += IDF(t) × [ f(t,d) × (k1 + 1) ] / [ f(t,d) + k1 × (1 − b + b × |d| / avgdl) ]

- **IDF** rewards rare words; **term frequency** saturates (controlled by k1 ≈ 1.2–2.0); **b ≈ 0.75** normalises for document length.

### Fusing two ranked lists
Scores from different systems are on different scales (cosine ~0–1, BM25 0–30), so adding them directly is unreliable.

**Reciprocal Rank Fusion:**  
`RRF(d) = Σ over lists  1 / (k + rank(d))`, with k = 60 a common default.  
It only uses ranks, needs no score normalisation, and rewards documents that appear high in *both* lists.

Alternatives: weighted score sum after min-max normalisation; learning-to-rank.

---

## How I built it in CareFlow (`app/rag/retriever.py`)

### Dense part — pgvector
```python
def _dense(self, db, query, collection, n):
    vector = self.embedder.embed_query(query)
    distance = KbChunk.embedding.cosine_distance(np.asarray(vector, dtype=np.float32))
    stmt = (select(KbChunk.id)
            .join(KbDocument, KbDocument.id == KbChunk.document_id)
            .where(KbChunk.embedding_model == self.embedder.name, KbChunk.embedding.is_not(None))
            .order_by(distance)          # SQL:  ORDER BY embedding <=> :vector
            .limit(n))
```
Only vectors made by the same embedder are compared. Optional collection filter (e.g. only `insurance`).

### Sparse part — BM25 in memory
`KbIndex` loads all chunks once, tokenises them with `content_tokens()` (normalisation + stop-word removal for 3 languages) and builds `BM25Okapi` from the `rank_bm25` library. It is rebuilt when the knowledge base changes (checked with a cheap signature: chunk count + max id).

### Fusion — RRF
```python
RRF_K = 60
FIRST_STAGE = 20
fused = {}
for ranking in rankings:                       # [dense_ids, sparse_ids]
    for rank, chunk_id in enumerate(ranking):
        fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)
pool = sorted(fused, key=lambda i: -fused[i])[:candidates]    # 12
```
The fused score is also passed to the re-ranker as a "prior" (used only to break ties in the lexical re-ranker).

### After fusion
Re-rank → relevance threshold → one result per translated section with a +0.05 bonus for the user's language → top 4 → cite the user's-language translation. See [Re-ranking](re-ranking.md).

### Why hybrid mattered here
- Users type in **English, Hindi, Marathi and romanised Hindi/Marathi** ("mujhe doctor chahiye"). Dense multilingual embeddings handle meaning across scripts; BM25 handles exact words like test names ("HbA1c", "CRP") and doctor names.
- The evaluation (`eval/run_rag.py`) compares **dense only, BM25 only, hybrid, and hybrid + re-ranker** on the same questions, so the choice is measured, not assumed.

### Also in the schema
`kb_chunk.tsv` is a PostgreSQL `tsvector` column (`to_tsvector('simple', section || ' ' || text)`) with a GIN index — PostgreSQL's built-in full-text search, using the `simple` configuration because there is no Hindi/Marathi stemmer. The live BM25 ranking uses `rank_bm25` in Python.

---

## Interview questions

**Q: Why not only vector search?**
Embeddings blur exact tokens — test codes, doctor names, numbers. BM25 finds them reliably. Combining both gives higher recall than either.

**Q: Why RRF instead of adding scores?**
Cosine and BM25 scores are on different scales and distributions. RRF uses only rank positions, so it needs no tuning or normalisation and is robust.

**Q: What does k = 60 do in RRF?**
It dampens the difference between top ranks so one list can't dominate; 60 is the value from the original RRF paper and a common default.

**Q: Where does BM25 live — the database or Python?**
In Python (`rank_bm25.BM25Okapi`) over all chunks in memory — the corpus is small (a few thousand chunks). For millions of documents I'd use Elasticsearch/OpenSearch or PostgreSQL full-text search.

**Q: How would you scale it?**
Keep pgvector with HNSW for dense; move sparse to PostgreSQL full-text or a search engine; cache embeddings of frequent queries; tune `ef_search` for recall vs speed.
