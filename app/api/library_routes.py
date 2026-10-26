"""The hospital's information library: every knowledge-base document, readable by anyone without signing in.

These are the same approved Markdown documents the assistant searches and cites (``knowledge/``), served
section by section in English, Hindi or Marathi, with a plain-text search.
"""

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Query

from app.rag.chunking import Document, load_documents
from app.rag.ingest import DEFAULT_ROOT
from app.tools.errors import ToolError

router = APIRouter(prefix="/api/v1/library", tags=["library"])

COLLECTIONS = ("policies", "insurance", "departments", "doctors", "test_preparation", "facilities")
SUMMARY_CHARS = 160
SNIPPET_CHARS = 90
MAX_RESULTS = 60
Language = Literal["en", "hi", "mr"]


def _slug(doc: Document) -> str:
    return Path(doc.source_path).stem


@lru_cache(maxsize=1)
def _library(root: Path = DEFAULT_ROOT) -> dict[tuple[str, str, str], Document]:
    """(language, collection, slug) -> document. The files only change with a new deployment."""
    return {(d.language, d.collection, _slug(d)): d for d in load_documents(root)}


def _plain(text: str) -> str:
    return " ".join(re.sub(r"^\s*-\s+", "", line) for line in text.splitlines()).strip()


def _shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def _snippet(doc: Document, words: list[str]) -> str:
    """The passage that shows why the document matched: the section with the most search words, around a
    word that is not already in the title."""
    bodies = [_plain(sec.body) for sec in doc.sections]
    if not bodies:
        return ""
    title = doc.title.casefold()
    best = max(
        bodies,
        key=lambda b: (sum(w in b.casefold() for w in words if w not in title), sum(w in b.casefold() for w in words)),
    )
    folded = best.casefold()
    hits = [folded.find(w) for w in words if w in folded]
    telling = [folded.find(w) for w in words if w in folded and w not in title]
    if not hits:
        return _shorten(bodies[0], SUMMARY_CHARS)
    start = max(0, min(telling or hits) - SNIPPET_CHARS // 2)
    return ("…" if start else "") + _shorten(best[start : start + SNIPPET_CHARS * 2], SNIPPET_CHARS * 2)


def _view(doc: Document) -> dict:
    return {
        "collection": doc.collection,
        "slug": _slug(doc),
        "title": doc.title,
        "last_verified": doc.last_verified.isoformat(),
    }


@router.get("")
def library(
    language: Language = "en",
    collection: str | None = Query(None, max_length=40),
    q: str | None = Query(None, max_length=100),
) -> dict:
    """Documents in one language, optionally one collection, optionally matching every word of ``q``."""
    if collection is not None and collection not in COLLECTIONS:
        raise ToolError("VALIDATION_ERROR", f"Unknown collection {collection!r}.")
    docs = [d for (lang, _, _), d in _library().items() if lang == language]
    counts = {c: sum(1 for d in docs if d.collection == c) for c in COLLECTIONS}
    if collection:
        docs = [d for d in docs if d.collection == collection]
    words = [w for w in (q or "").casefold().split() if w]
    rows = []
    for doc in docs:
        title = doc.title.casefold()
        body = " ".join(f"{s.heading} {s.body}" for s in doc.sections).casefold()
        if words and not all(w in title or w in body for w in words):
            continue
        score = sum(3 * (w in title) + body.count(w) for w in words)
        summary = _snippet(doc, words) if words else _shorten(_plain(doc.sections[0].body), SUMMARY_CHARS)
        rows.append((-score, COLLECTIONS.index(doc.collection), doc.title, {**_view(doc), "summary": summary}))
    rows.sort(key=lambda r: r[:3])
    found = [r[3] for r in rows]
    return {
        "language": language,
        "query": q or "",
        "collections": [{"collection": c, "count": n} for c, n in counts.items()],
        "total": len(rows),
        "documents": found[:MAX_RESULTS] if words else found,
    }


@router.get("/{collection}/{slug}")
def document(collection: str, slug: str, language: Language = "en") -> dict:
    doc = _library().get((language, collection, slug))
    if doc is None:
        raise ToolError("NOT_FOUND", "This document does not exist.")
    languages = [lang for lang in ("en", "hi", "mr") if (lang, collection, slug) in _library()]
    return {
        **_view(doc),
        "language": language,
        "doc_key": doc.doc_key,
        "languages": languages,
        "sections": [{"heading": s.heading, "body": s.body} for s in doc.sections],
    }
