"""Load the Markdown knowledge base into kb_document / kb_chunk with embeddings.

python -m app.rag.ingest [--if-needed] [--chunker structure|fixed] [--root knowledge]
"""

import argparse
import logging
import sys
import time
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import KbChunk, KbDocument
from app.db.session import session_scope
from app.rag.chunking import Chunk, Document, fixed_chunks, load_documents, structure_chunks
from app.rag.embeddings import choose_embedder
from app.rag.retriever import reset_retriever
from app.safety.privacy import install_log_masking

log = logging.getLogger(__name__)
DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "knowledge"
CHUNKERS = {"structure": structure_chunks, "fixed": fixed_chunks}
BATCH = 64


def build_chunks(docs: list[Document], chunker: str) -> list[tuple[Document, Chunk]]:
    split = CHUNKERS[chunker]
    pairs = [(doc, chunk) for doc in docs for chunk in split(doc)]
    return sorted(pairs, key=lambda p: (p[0].source_path, p[1].index))


def is_current(db: Session, docs: list[Document], embedder_name: str) -> bool:
    stored = dict(db.execute(select(KbDocument.source_path, KbDocument.content_hash)).all())
    if stored != {d.source_path: d.content_hash for d in docs}:
        return False
    models = set(db.scalars(select(KbChunk.embedding_model).distinct()))
    return models == {embedder_name}


def ingest(db: Session, root: Path = DEFAULT_ROOT, chunker: str = "structure", if_needed: bool = False) -> dict:
    settings = get_settings()
    docs = load_documents(root)
    if not docs:
        raise SystemExit(f"no documents found under {root}")
    pairs = build_chunks(docs, chunker)
    embedder = choose_embedder(
        settings.embedding_backend, settings.embedding_model, settings.model_cache_dir, [c.text for _, c in pairs]
    )
    if if_needed and is_current(db, docs, embedder.name):
        return {"status": "up to date", "documents": len(docs), "chunks": len(pairs), "embedder": embedder.name}

    started = time.perf_counter()
    db.execute(delete(KbChunk))
    db.execute(delete(KbDocument))
    rows: dict[str, KbDocument] = {}
    for doc in docs:
        row = KbDocument(
            collection=doc.collection,
            title=doc.title,
            language=doc.language,
            last_verified=doc.last_verified,
            source_path=doc.source_path,
            doc_key=doc.doc_key,
            content_hash=doc.content_hash,
        )
        db.add(row)
        rows[doc.source_path] = row
    db.flush()
    for start in range(0, len(pairs), BATCH):
        batch = pairs[start : start + BATCH]
        vectors = embedder.embed_documents([c.text for _, c in batch])
        for (doc, chunk), vector in zip(batch, vectors, strict=True):
            db.add(
                KbChunk(
                    document_id=rows[doc.source_path].id,
                    chunk_index=chunk.index,
                    section=chunk.section[:200],
                    text=chunk.text,
                    embedding=vector.tolist(),
                    embedding_model=embedder.name,
                )
            )
        db.flush()
    reset_retriever()
    return {
        "status": "ingested",
        "documents": len(docs),
        "chunks": len(pairs),
        "chunker": chunker,
        "embedder": embedder.name,
        "seconds": round(time.perf_counter() - started, 1),
    }


def main(argv: list[str] | None = None) -> int:
    install_log_masking()
    parser = argparse.ArgumentParser(prog="python -m app.rag.ingest")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--chunker", choices=sorted(CHUNKERS), default="structure")
    parser.add_argument("--if-needed", action="store_true", help="skip when documents and embedder are unchanged")
    args = parser.parse_args(argv)
    with session_scope() as db:
        result = ingest(db, args.root, args.chunker, args.if_needed)
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
