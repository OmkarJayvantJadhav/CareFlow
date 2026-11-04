# pgvector

## 30-second answer
pgvector is a PostgreSQL extension that adds a **`vector` data type**, **distance operators** (L2 `<->`, cosine `<=>`, inner product `<#>`) and **approximate nearest-neighbour indexes (HNSW, IVFFlat)** — so you can store embeddings next to your relational data and do semantic search with SQL. In CareFlow, every knowledge-base chunk has a **384-dimensional embedding** in a `vector(384)` column with an **HNSW index using cosine distance**; the dense half of hybrid retrieval is a single SQL query `ORDER BY embedding <=> :query_vector LIMIT 20`, joined with document metadata and filtered by collection and embedding model.

---

## Basics you must know

### Setup
```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE kb_chunk (id serial PRIMARY KEY, text text, embedding vector(384));
INSERT INTO kb_chunk (text, embedding) VALUES ('...', '[0.12, -0.03, ...]');
```

### Distance operators
| Operator | Distance | Use when |
|---|---|---|
| `<->` | Euclidean (L2) | Embeddings not normalised |
| `<=>` | **Cosine distance** (1 − cosine similarity) | Most text embeddings |
| `<#>` | Negative inner product | Normalised vectors (fastest; equals cosine ranking) |
| `<+>` | L1 (newer versions) | |

```sql
SELECT id, text FROM kb_chunk ORDER BY embedding <=> '[...]' LIMIT 5;
```

### Indexes (approximate nearest neighbour)
| | **HNSW** | IVFFlat |
|---|---|---|
| Structure | Multi-layer graph of neighbours | Clusters (lists) of vectors |
| Build | Slower, more memory | Faster; needs data present to choose centroids |
| Query speed/recall | Better trade-off | Good, tune `lists` / `probes` |
| Tuning | `m`, `ef_construction`; query-time `hnsw.ef_search` | `lists`; query-time `ivfflat.probes` |

The index's operator class must match the operator in queries: `vector_cosine_ops` for `<=>`, `vector_l2_ops` for `<->`, `vector_ip_ops` for `<#>`.

Without an index the search is **exact** (sequential scan) — fine for small tables.

### Why pgvector instead of a dedicated vector DB (Pinecone, Weaviate, Qdrant, FAISS)?
- One database: joins, filters, transactions and backups together with relational data.
- No extra service to run or pay for.
- Good enough for up to millions of vectors; dedicated systems win at very large scale or with advanced features.

### Python
`pgvector.sqlalchemy.Vector(dim)` column type; `Column.cosine_distance(vec)`, `.l2_distance(vec)`, `.max_inner_product(vec)` build the operators.

---

## How I used it in CareFlow

### Extension and column (`alembic/versions/0001_initial_schema.py`, `app/db/models.py`)
```python
op.execute("CREATE EXTENSION IF NOT EXISTS vector")

class KbChunk(Base):
    __tablename__ = "kb_chunk"
    __table_args__ = (
        Index("ix_kb_chunk_embedding", "embedding",
              postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"}),
        Index("ix_kb_chunk_tsv", "tsv", postgresql_using="gin"),
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384))
    embedding_model: Mapped[str] = mapped_column(String(120), index=True)   # which embedder made it
```

### Query (`app/rag/retriever.py`)
```python
vector = self.embedder.embed_query(query)                     # 384-d, L2-normalised
distance = KbChunk.embedding.cosine_distance(np.asarray(vector, dtype=np.float32))
stmt = (select(KbChunk.id)
        .join(KbDocument, KbDocument.id == KbChunk.document_id)
        .where(KbChunk.embedding_model == self.embedder.name,   # never compare vectors from different models
               KbChunk.embedding.is_not(None))
        .order_by(distance)
        .limit(20))
if collection:
    stmt = stmt.where(KbDocument.collection == collection)     # metadata filter in the same query
```
These 20 ids are fused with BM25's 20 via reciprocal rank fusion, then re-ranked.

### Where the vectors come from
- **Neural:** `paraphrase-multilingual-MiniLM-L12-v2` via fastembed (ONNX), 384-d. A dimension probe at start-up checks the model really outputs 384 values to match the column.
- **Local fallback:** TF-IDF character n-grams + TruncatedSVD, padded to 384-d.
- Rows are **L2-normalised**, so cosine distance and inner product rank identically.
- The `embedding_model` column lets two embedders coexist safely — switching models never mixes vector spaces.

### Ingestion (`python -m app.rag.ingest [--if-needed]`)
Chunk the 363 documents, embed them, insert rows. In Docker it runs at start-up only when the knowledge base changed, inside `timeout 600` so a slow embed never stops the site from starting.

### Environments
- Local/CI: `pgvector/pgvector:pg16` image.
- Production: **Neon** supports pgvector.

### Scale
A few thousand chunks — exact search would also be fast, but the HNSW index keeps queries fast as hospitals add documents.

---

## Interview questions

**Q: What does pgvector add to Postgres?**
A vector type, distance operators and ANN indexes (HNSW, IVFFlat), so semantic search is a SQL `ORDER BY embedding <=> query LIMIT k`.

**Q: Cosine vs L2 vs inner product?**
Cosine compares direction (good for text embeddings). For L2-normalised vectors, cosine, inner product and L2 give the same ranking; inner product is cheapest.

**Q: HNSW vs IVFFlat?**
HNSW is a navigable small-world graph — better recall/speed and no training step, but slower to build and more memory. IVFFlat clusters vectors — faster to build, needs representative data, tune `probes`.

**Q: Why not Pinecone/FAISS?**
One database for everything: joins with document metadata, filtering by collection, transactions and backups, no extra service — and it was free on Neon.

**Q: Why store the embedding model name?**
Vectors from different models live in different spaces; filtering by `embedding_model` prevents comparing incompatible vectors when switching between the neural model and the local fallback.

**Q: Exact vs approximate search?**
Without an index pgvector scans every row (exact). With HNSW/IVFFlat the search is approximate — much faster, slightly lower recall, tunable with `ef_search` / `probes`.
