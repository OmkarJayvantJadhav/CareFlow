"""The knowledge base in the database (phase 7D): templates from knowledge/, admins' changes, and the index.

The documents' source of truth is ``kb_document.template`` (Markdown with policy placeholders). The files in
``knowledge/`` are the shipped templates: loading them adds new ones and updates unchanged ones, but never
touches a document an admin edited, added or hid. ``reindex`` then brings the chunks and embeddings in line
with what readers see (placeholders filled with the numbers in force), re-embedding only what changed, or
everything when the embedder itself changed (the local LSA embedder is fitted on the whole corpus).
"""

import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import KbChunk, KbDocument
from app.rag.chunking import Document, fixed_chunks, parse_document, render, structure_chunks
from app.rag.embeddings import choose_embedder, embedder_for_index
from app.rag.retriever import reset_retriever
from app.rag.setup_docs import same_apart_from_date, templates_for
from app.timeutil import now_ist

DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "knowledge"
CHUNKERS = {"structure": structure_chunks, "fixed": fixed_chunks}
BATCH = 2048


def _describe(row: KbDocument, doc: Document) -> None:
    row.collection, row.title, row.language = doc.collection, doc.title[:200], doc.language
    row.last_verified, row.doc_key = doc.last_verified, doc.doc_key


def sync_templates(db: Session, root: Path = DEFAULT_ROOT, today: date | None = None) -> dict:
    """Load the shipped templates. Documents admins edited, added or hid are left as they are. On a hospital's
    own deployment the department, doctor and some facility pages come from its setup (app.rag.setup_docs)."""
    templates, from_setup = templates_for(db, root, today or now_ist().date())
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
            if source in from_setup and same_apart_from_date(row.template, raw):
                continue
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


@dataclass
class _Plan:
    """What re-indexing needs from the database, read in one go."""

    rows: list[KbDocument]
    visible: list[tuple[KbDocument, Document, list]]
    hidden: list[int]
    stored: dict[int, set[str]]

    @property
    def texts(self) -> list[str]:
        return [c.text for _, _, chunks in self.visible for c in chunks] or ["∅"]


def _plan(db: Session, chunker: str) -> _Plan:
    split = CHUNKERS[chunker]
    rows = list(db.scalars(select(KbDocument).order_by(KbDocument.source_path)))
    visible = []
    for row in rows:
        if row.hidden_at is None and row.template is not None:
            doc = parse_document(render(row.template), row.source_path)
            visible.append((row, doc, split(doc)))
    stored: dict[int, set[str]] = defaultdict(set)
    for doc_id, model in db.execute(select(KbChunk.document_id, KbChunk.embedding_model).distinct()):
        stored[doc_id].add(model)
    return _Plan(rows, visible, [r.id for r in rows if r.hidden_at is not None], stored)


def _embed(plan: _Plan, embedder, force: bool) -> tuple[list, list]:
    """The documents to re-index and their chunks' vectors. No database access: this is the slow part."""
    todo = [
        (row, doc, chunks)
        for row, doc, chunks in plan.visible
        if force or row.content_hash != doc.content_hash or plan.stored.get(row.id) != {embedder.name}
    ]
    pending = [(row.id, chunk) for row, _, chunks in todo for chunk in chunks]
    vectors = []
    # Large batches: the LSA embedder has a high fixed cost per call.
    for start in range(0, len(pending), BATCH):
        vectors.extend(embedder.embed_documents([chunk.text for _, chunk in pending[start : start + BATCH]]))
    return todo, list(zip(pending, vectors, strict=True))


def _write(db: Session, plan: _Plan, todo: list, embedded: list, embedder_name: str) -> None:
    if plan.hidden:
        db.execute(delete(KbChunk).where(KbChunk.document_id.in_(plan.hidden)))
    if todo:
        db.execute(delete(KbChunk).where(KbChunk.document_id.in_([row.id for row, _, _ in todo])))
        db.add_all(
            KbChunk(
                document_id=doc_id,
                chunk_index=chunk.index,
                section=chunk.section[:200],
                text=chunk.text,
                embedding=vector.tolist(),
                embedding_model=embedder_name,
            )
            for (doc_id, chunk), vector in embedded
        )
        for row, doc, _ in todo:
            row = row if row in db else db.get(KbDocument, row.id)
            _describe(row, doc)
            row.content_hash = doc.content_hash
    db.flush()


def _result(plan: _Plan, todo: list, embedder_name: str, started: float) -> dict:
    if todo or plan.hidden:
        reset_retriever()
    return {
        "documents": len(plan.visible),
        "reindexed": len(todo),
        "chunks": sum(len(c) for _, _, c in plan.visible),
        "embedder": embedder_name,
        "seconds": round(time.perf_counter() - started, 1),
    }


def reindex(db: Session, chunker: str = "structure", force: bool = False, refit: bool = True) -> dict:
    """Chunk and embed every visible document whose text (as readers see it) or embedder changed.

    ``refit=False`` (changes made in the app): keep the embedder the stored chunks were made with, so the
    server never fits the LSA embedder (D-67); new words are still found by the BM25 index, which is rebuilt
    from every chunk. The ingest step at the next deployment refits on the whole corpus."""
    started = time.perf_counter()
    settings = get_settings()
    plan = _plan(db, chunker)
    args = (settings.embedding_backend, settings.embedding_model, settings.model_cache_dir, plan.texts)
    if refit:
        embedder = choose_embedder(*args)
    else:
        embedder = embedder_for_index(*args, set().union(*plan.stored.values()) if plan.stored else set())
    todo, embedded = _embed(plan, embedder, force)
    _write(db, plan, todo, embedded, embedder.name)
    return _result(plan, todo, embedder.name, started)


def reindex_without_holding_a_transaction(
    factory: sessionmaker, chunker: str = "structure", force: bool = False
) -> dict:
    """``reindex`` for the start-up step, in three parts: read, then fit and embed with no transaction open,
    then write in one short transaction. Fitting the LSA embedder can take minutes on a small instance, and
    a transaction left idle that long is ended by the database (Neon); through its pooler the next COMMIT then
    failed with "received 2 results from command 'COMMIT'" (D-130)."""
    started = time.perf_counter()
    settings = get_settings()
    with factory() as db:  # closing (not committing) keeps the rows' loaded values
        plan = _plan(db, chunker)
    # Progress lines, so a deployment log shows where a slow start-up is (D-138).
    print(f"knowledge base: preparing the search model on {len(plan.texts)} passages", flush=True)
    embedder = choose_embedder(
        settings.embedding_backend, settings.embedding_model, settings.model_cache_dir, plan.texts
    )
    print("knowledge base: embedding the changed documents", flush=True)
    todo, embedded = _embed(plan, embedder, force)
    print(f"knowledge base: saving {len(embedded)} passages", flush=True)
    with factory() as db:
        _write(db, plan, todo, embedded, embedder.name)
        db.commit()
    return _result(plan, todo, embedder.name, started)
