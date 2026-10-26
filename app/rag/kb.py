"""The knowledge base in the database (phase 7D): templates from knowledge/, admins' changes, and the index.

The documents' source of truth is ``kb_document.template`` (Markdown with policy placeholders). The files in
``knowledge/`` are the shipped templates: loading them adds new ones and updates unchanged ones, but never
touches a document an admin edited, added or hid. ``reindex`` then brings the chunks and embeddings in line
with what readers see (placeholders filled with the numbers in force), re-embedding only what changed, or
everything when the embedder itself changed (the local LSA embedder is fitted on the whole corpus).
"""

import time
from collections import defaultdict
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import KbChunk, KbDocument
from app.rag.chunking import Document, fixed_chunks, parse_document, read_templates, render, structure_chunks
from app.rag.embeddings import choose_embedder, embedder_for_index
from app.rag.retriever import reset_retriever
from app.timeutil import now_ist

DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "knowledge"
CHUNKERS = {"structure": structure_chunks, "fixed": fixed_chunks}
BATCH = 2048


def _describe(row: KbDocument, doc: Document) -> None:
    row.collection, row.title, row.language = doc.collection, doc.title[:200], doc.language
    row.last_verified, row.doc_key = doc.last_verified, doc.doc_key


def sync_templates(db: Session, root: Path = DEFAULT_ROOT) -> dict:
    """Load the shipped templates. Documents admins edited, added or hid are left as they are."""
    templates = dict(read_templates(root))
    if not templates:
        raise SystemExit(f"no documents found under {root}")
    rows = {row.source_path: row for row in db.scalars(select(KbDocument))}
    added = updated = removed = 0
    for source, raw in templates.items():
        row = rows.get(source)
        if row is None:
            row = KbDocument(source_path=source, template=raw, origin="template", content_hash="")
            _describe(row, parse_document(render(raw), source))
            db.add(row)
            added += 1
        elif row.origin == "template" and row.template != raw:
            row.template = raw
            _describe(row, parse_document(render(raw), source))
            row.updated_at = now_ist()
            updated += 1
    for source, row in rows.items():
        if row.origin == "template" and source not in templates:
            db.execute(delete(KbDocument).where(KbDocument.id == row.id))  # chunks: ON DELETE CASCADE
            db.expunge(row)
            removed += 1
    db.flush()
    return {"added": added, "updated": updated, "removed": removed}


def reindex(db: Session, chunker: str = "structure", force: bool = False, refit: bool = True) -> dict:
    """Chunk and embed every visible document whose text (as readers see it) or embedder changed.

    ``refit=False`` (changes made in the app): keep the embedder the stored chunks were made with, so the
    server never fits the LSA embedder (D-67); new words are still found by the BM25 index, which is rebuilt
    from every chunk. The ingest step at the next deployment refits on the whole corpus."""
    started = time.perf_counter()
    settings = get_settings()
    split = CHUNKERS[chunker]
    rows = list(db.scalars(select(KbDocument).order_by(KbDocument.source_path)))
    hidden = [r.id for r in rows if r.hidden_at is not None]
    if hidden:
        db.execute(delete(KbChunk).where(KbChunk.document_id.in_(hidden)))
    visible = []
    for row in rows:
        if row.hidden_at is None and row.template is not None:
            doc = parse_document(render(row.template), row.source_path)
            visible.append((row, doc, split(doc)))
    texts = [c.text for _, _, chunks in visible for c in chunks] or ["∅"]
    stored: dict[int, set[str]] = defaultdict(set)
    for doc_id, model in db.execute(select(KbChunk.document_id, KbChunk.embedding_model).distinct()):
        stored[doc_id].add(model)
    args = (settings.embedding_backend, settings.embedding_model, settings.model_cache_dir, texts)
    if refit:
        embedder = choose_embedder(*args)
    else:
        embedder = embedder_for_index(*args, set().union(*stored.values()) if stored else set())
    todo = [
        (row, doc, chunks)
        for row, doc, chunks in visible
        if force or row.content_hash != doc.content_hash or stored.get(row.id) != {embedder.name}
    ]
    if todo:
        db.execute(delete(KbChunk).where(KbChunk.document_id.in_([row.id for row, _, _ in todo])))
        pending = [(row, chunk) for row, _, chunks in todo for chunk in chunks]
        # One large batch: the LSA embedder has a high fixed cost per call.
        for start in range(0, len(pending), BATCH):
            batch = pending[start : start + BATCH]
            vectors = embedder.embed_documents([chunk.text for _, chunk in batch])
            db.add_all(
                KbChunk(
                    document_id=row.id,
                    chunk_index=chunk.index,
                    section=chunk.section[:200],
                    text=chunk.text,
                    embedding=vector.tolist(),
                    embedding_model=embedder.name,
                )
                for (row, chunk), vector in zip(batch, vectors, strict=True)
            )
        for row, doc, _ in todo:
            _describe(row, doc)
            row.content_hash = doc.content_hash
    changed = len(todo)
    db.flush()
    if changed or hidden:
        reset_retriever()
    return {
        "documents": len(visible),
        "reindexed": changed,
        "chunks": sum(len(c) for _, _, c in visible),
        "embedder": embedder.name,
        "seconds": round(time.perf_counter() - started, 1),
    }
