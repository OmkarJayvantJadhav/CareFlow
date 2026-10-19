"""Hybrid retrieval over the knowledge base (FR-17 – FR-19).

dense (pgvector, cosine) + sparse (BM25)  ->  reciprocal rank fusion  ->
re-ranker  ->  one result per translated section, preferring the user's
language  ->  relevance threshold  ->  top k.
"""

import hashlib
import logging
import math
import threading
from dataclasses import asdict, dataclass
from datetime import date

import numpy as np
from rank_bm25 import BM25Okapi
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import KbChunk, KbDocument
from app.rag.embeddings import Embedder, choose_embedder
from app.rag.rerank import Reranker, choose_reranker
from app.rag.text import content_tokens

log = logging.getLogger(__name__)

RRF_K = 60
FIRST_STAGE = 20
LANGUAGE_BONUS = 0.05
# Below this re-ranker score a chunk is not considered a source for the answer (FR-19).
RELEVANCE_THRESHOLD = {"cross-encoder": 0.15, "lexical-v1": 0.55}


@dataclass
class RetrievedChunk:
    chunk_id: int
    document_id: int
    doc_key: str
    chunk_index: int
    title: str
    section: str
    text: str
    collection: str
    language: str
    source_path: str
    last_verified: date
    score: float = 0.0

    def citation(self) -> dict:
        return {
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "title": self.title,
            "section": self.section,
            "collection": self.collection,
            "language": self.language,
            "source_path": self.source_path,
            "last_verified": self.last_verified.isoformat(),
        }


def corpus_fingerprint(rows: list[tuple[str, int, str]]) -> str:
    digest = hashlib.sha256()
    for source_path, index, text in rows:
        digest.update(f"{source_path}\x1f{index}\x1f{text}\x1e".encode())
    return digest.hexdigest()


class KbIndex:
    """All chunks in memory with a BM25 index; rebuilt when the knowledge base changes."""

    def __init__(self, chunks: list[RetrievedChunk], signature: tuple):
        self.signature = signature
        self.chunks = chunks
        self.by_id = {c.chunk_id: c for c in chunks}
        # Translations share doc_key and chunk_index (the knowledge base is generated that way).
        self.by_translation = {(c.doc_key, c.chunk_index, c.language): c for c in chunks}
        self.texts = [c.text for c in chunks]
        tokenized = [content_tokens(t) or ["∅"] for t in self.texts]
        self.bm25 = BM25Okapi(tokenized) if chunks else None
        n = len(tokenized)
        df: dict[str, int] = {}
        for tokens in tokenized:
            for t in set(tokens):
                df[t] = df.get(t, 0) + 1
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    @classmethod
    def load(cls, db: Session) -> "KbIndex":
        rows = db.execute(
            select(KbChunk, KbDocument)
            .join(KbDocument, KbDocument.id == KbChunk.document_id)
            .order_by(KbDocument.source_path, KbChunk.chunk_index)
        ).all()
        chunks = [
            RetrievedChunk(
                chunk_id=c.id,
                document_id=d.id,
                doc_key=d.doc_key,
                chunk_index=c.chunk_index,
                title=d.title,
                section=c.section,
                text=c.text,
                collection=d.collection,
                language=d.language,
                source_path=d.source_path,
                last_verified=d.last_verified,
            )
            for c, d in rows
        ]
        return cls(chunks, kb_signature(db))


def kb_signature(db: Session) -> tuple:
    count, max_id = db.execute(select(func.count(KbChunk.id), func.coalesce(func.max(KbChunk.id), 0))).one()
    return (count, max_id)


class Retriever:
    def __init__(self, index: KbIndex, embedder: Embedder, reranker: Reranker):
        self.index = index
        self.embedder = embedder
        self.reranker = reranker

    def _dense(self, db: Session, query: str, collection: str | None, n: int) -> list[int]:
        vector = self.embedder.embed_query(query)
        distance = KbChunk.embedding.cosine_distance(np.asarray(vector, dtype=np.float32))
        stmt = (
            select(KbChunk.id)
            .join(KbDocument, KbDocument.id == KbChunk.document_id)
            .where(KbChunk.embedding_model == self.embedder.name, KbChunk.embedding.is_not(None))
            .order_by(distance)
            .limit(n)
        )
        if collection:
            stmt = stmt.where(KbDocument.collection == collection)
        return list(db.scalars(stmt))

    def _sparse(self, query: str, collection: str | None, n: int) -> list[int]:
        tokens = content_tokens(query)
        if not tokens or self.index.bm25 is None:
            return []
        scores = self.index.bm25.get_scores(tokens)
        order = np.argsort(-scores)
        out = []
        for i in order:
            if scores[i] <= 0 or len(out) >= n:
                break
            chunk = self.index.chunks[i]
            if collection is None or chunk.collection == collection:
                out.append(chunk.chunk_id)
        return out

    def search(
        self,
        db: Session,
        query: str,
        collection: str | None = None,
        language: str | None = None,
        top_k: int | None = None,
        candidates: int | None = None,
        use_dense: bool = True,
        use_sparse: bool = True,
        use_reranker: bool = True,
    ) -> list[RetrievedChunk]:
        settings = get_settings()
        top_k = top_k or settings.rag_top_k
        candidates = candidates or settings.rag_candidates
        rankings = []
        if use_dense:
            rankings.append(self._dense(db, query, collection, FIRST_STAGE))
        if use_sparse:
            rankings.append(self._sparse(query, collection, FIRST_STAGE))
        fused: dict[int, float] = {}
        for ranking in rankings:
            for rank, chunk_id in enumerate(ranking):
                fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)
        pool = sorted(fused, key=lambda i: -fused[i])[:candidates]
        if not pool:
            return []
        chunks = [self.index.by_id[i] for i in pool if i in self.index.by_id]
        prior = [fused[c.chunk_id] for c in chunks]
        if use_reranker:
            scores = self.reranker.score(query, [c.text for c in chunks], prior)
            threshold = RELEVANCE_THRESHOLD.get(self.reranker.name.split(":")[0], 0.0)
        else:
            top = max(prior)
            scores = [p / top for p in prior]
            threshold = 0.0

        best: dict[tuple[str, int], tuple[float, RetrievedChunk]] = {}
        for chunk, score in zip(chunks, scores, strict=True):
            adjusted = score + (LANGUAGE_BONUS if language and chunk.language == language else 0.0)
            key = (chunk.doc_key, chunk.chunk_index)
            if score >= threshold and (key not in best or adjusted > best[key][0]):
                best[key] = (adjusted, RetrievedChunk(**{**asdict(chunk), "score": round(float(score), 4)}))
        ranked = sorted(best.values(), key=lambda pair: -pair[0])
        results = []
        for _, chunk in ranked[:top_k]:
            # Cite the section in the user's language when a translation of it exists.
            translated = (
                self.index.by_translation.get((chunk.doc_key, chunk.chunk_index, language)) if language else None
            )
            if translated is not None and translated.chunk_id != chunk.chunk_id:
                chunk = RetrievedChunk(**{**asdict(translated), "score": chunk.score})
            results.append(chunk)
        return results


_lock = threading.Lock()
_retriever: Retriever | None = None


def get_retriever(db: Session) -> Retriever:
    """The process-wide retriever, rebuilt whenever the knowledge base changes."""
    global _retriever
    signature = kb_signature(db)
    with _lock:
        if _retriever is None or _retriever.index.signature != signature:
            settings = get_settings()
            index = KbIndex.load(db)
            embedder = choose_embedder(
                settings.embedding_backend, settings.embedding_model, settings.model_cache_dir, index.texts or ["∅"]
            )
            reranker = choose_reranker(
                settings.reranker_backend, settings.reranker_model, settings.model_cache_dir, index.idf
            )
            _retriever = Retriever(index, embedder, reranker)
            log.info(
                "retriever ready: %d chunks, embedder=%s, reranker=%s", len(index.chunks), embedder.name, reranker.name
            )
        return _retriever


def reset_retriever() -> None:
    global _retriever
    with _lock:
        _retriever = None
