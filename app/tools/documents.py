"""Admins keep the hospital's information documents (phase 7D): edit, add, translate, hide and restore them.

A document is Markdown: ``## `` headings with text under them; lines starting with "- " are a list. Policy
numbers are written as placeholders (``{{cancel_hours}}``) so they follow the hospital's rules. Every change
re-indexes the knowledge base, so the assistant answers from the new text straight away. What an admin
changes is never overwritten by the shipped templates.
"""

import re
import unicodedata
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import LANGUAGES, AppUser, KbDocument
from app.rag.chunking import parse_document, render, unknown_placeholders
from app.rag.kb import DEFAULT_ROOT, reindex
from app.timeutil import iso, resolve_now
from app.tools import policy
from app.tools.audit import write_tool
from app.tools.errors import ToolError
from app.tools.permissions import Actor, require_role

COLLECTIONS = ("policies", "insurance", "departments", "doctors", "test_preparation", "facilities")
MAX_BODY = 30_000
MAX_LISTED = 400


def _slug(row: KbDocument) -> str:
    return Path(row.source_path).stem


def _body(template: str) -> str:
    """The part an admin edits: everything after the front matter and the "# title" line."""
    match = re.match(r"\A---\n.*?\n---\n(.*)\Z", template, re.S)
    text = match.group(1) if match else template
    return re.sub(r"\A#\s[^\n]*\n+", "", text.lstrip("\n")).rstrip() + "\n"


def _row_view(row: KbDocument) -> dict:
    return {
        "document_id": row.id,
        "title": row.title,
        "collection": row.collection,
        "language": row.language,
        "slug": _slug(row),
        "doc_key": row.doc_key,
        "origin": row.origin,
        "hidden": row.hidden_at is not None,
        "last_verified": row.last_verified.isoformat(),
        "edited_at": iso(row.edited_at) if row.edited_at else None,
        "edited_by": row.edited_by,
    }


def list_documents(
    db: Session, actor: Actor, language: str | None = None, collection: str | None = None, q: str | None = None
) -> dict:
    require_role(actor, "admin")
    query = select(KbDocument).order_by(KbDocument.collection, KbDocument.title)
    if language:
        query = query.where(KbDocument.language == language)
    if collection:
        query = query.where(KbDocument.collection == collection)
    for word in (q or "").casefold().split():
        query = query.where(or_(func.lower(KbDocument.title).contains(word, autoescape=True),
                                func.lower(KbDocument.doc_key).contains(word, autoescape=True)))  # fmt: skip
    rows = list(db.scalars(query.limit(MAX_LISTED + 1)))
    counts = dict(db.execute(select(KbDocument.origin, func.count()).group_by(KbDocument.origin)).all())
    hidden = db.scalar(select(func.count()).select_from(KbDocument).where(KbDocument.hidden_at.is_not(None)))
    return {
        "documents": [_row_view(r) for r in rows[:MAX_LISTED]],
        "more": len(rows) > MAX_LISTED,
        "counts": {
            "template": counts.get("template", 0),
            "edited": counts.get("edited", 0),
            "added": counts.get("added", 0),
            "hidden": hidden,
        },  # fmt: skip
        "placeholders": {k: {"value": v, "unit": policy.SETTINGS[k][3]} for k, v in policy.current().items()},
    }


def get_document(db: Session, actor: Actor, document_id: int) -> dict:
    require_role(actor, "admin")
    row = _row(db, document_id)
    translations = db.execute(
        select(KbDocument.id, KbDocument.language).where(KbDocument.doc_key == row.doc_key, KbDocument.id != row.id)
    ).all()
    return {
        **_row_view(row),
        "body": _body(row.template or ""),
        "translations": [{"document_id": i, "language": lang} for i, lang in translations],
        "missing_languages": [
            lang for lang in LANGUAGES if lang != row.language and lang not in {other for _, other in translations}
        ],
    }


def _row(db: Session, document_id: int, for_update: bool = False) -> KbDocument:
    query = select(KbDocument).where(KbDocument.id == document_id)
    row = db.scalars(query.with_for_update() if for_update else query).first()
    if row is None:
        raise ToolError("NOT_FOUND", "There is no such document.")
    return row


def _clean_title(title: str) -> str:
    clean = " ".join((title or "").split())
    if not 3 <= len(clean) <= 200:
        raise ToolError("VALIDATION_ERROR", "Give a title of 3–200 characters.")
    return clean


def _compose(title: str, collection: str, language: str, doc_key: str, verified: date, body: str) -> str:
    body = body.replace("\r\n", "\n").strip()
    if len(body) > MAX_BODY:
        raise ToolError("VALIDATION_ERROR", f"A document can be at most {MAX_BODY:,} characters long.")
    if not body.startswith("## "):
        raise ToolError("VALIDATION_ERROR", 'Start the text with a section heading: a line beginning with "## ".')
    raw = (
        f"---\ntitle: {title}\ncollection: {collection}\nlanguage: {language}\n"
        f"last_verified: {verified.isoformat()}\ndoc_key: {doc_key}\n---\n# {title}\n\n{body}\n"
    )
    unknown = unknown_placeholders(raw)
    if unknown:
        raise ToolError("VALIDATION_ERROR", f"Unknown placeholder {{{{{unknown[0]}}}}}; see the list of placeholders.")
    doc = parse_document(render(raw), "check")
    if not doc.sections:
        raise ToolError("VALIDATION_ERROR", "Every section needs some text under its heading.")
    return raw


def _ascii_slug(title: str) -> str:
    text = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def _new_slug(db: Session, title: str, collection: str) -> str:
    base = _ascii_slug(title) or "document"
    taken = {
        Path(p).stem for p in db.scalars(select(KbDocument.source_path).where(KbDocument.collection == collection))
    }
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1
    return slug


def _username(db: Session, actor: Actor) -> str | None:
    return db.scalar(select(AppUser.username).where(AppUser.id == actor.user_id))


@write_tool("save_document")
def save_document(
    db: Session,
    actor: Actor,
    document_id: int | None,
    title: str,
    body: str,
    collection: str | None = None,
    language: str | None = None,
    translation_of: int | None = None,
    checked_today: bool = True,
    now: datetime | None = None,
) -> dict:
    """Change a document, add a new one, or add a translation of one (``translation_of``)."""
    now = resolve_now(now)
    require_role(actor, "admin")
    title = _clean_title(title)
    if document_id is not None:
        row = _row(db, document_id, for_update=True)
        verified = now.date() if checked_today else row.last_verified
        row.template = _compose(title, row.collection, row.language, row.doc_key, verified, body)
        if row.origin == "template":
            row.origin = "edited"
    else:
        if translation_of is not None:
            base = _row(db, translation_of)
            collection, doc_key, slug = base.collection, base.doc_key, _slug(base)
            if language not in LANGUAGES:
                raise ToolError("VALIDATION_ERROR", "Choose the language of the translation.")
            taken = db.scalar(
                select(KbDocument.id).where(KbDocument.doc_key == doc_key, KbDocument.language == language)
            )
            if taken is not None:
                raise ToolError("DUPLICATE", "This document already has a version in that language.")
        else:
            if collection not in COLLECTIONS:
                raise ToolError("VALIDATION_ERROR", "Choose the collection the document belongs to.")
            if language not in LANGUAGES:
                raise ToolError("VALIDATION_ERROR", "Choose the document's language.")
            slug = _new_slug(db, title, collection)
            doc_key = f"{collection}/{slug}"
        row = KbDocument(
            source_path=f"custom/{language}/{collection}/{slug}.md",
            origin="added",
            content_hash="",
            template=_compose(title, collection, language, doc_key, now.date(), body),
        )
        db.add(row)
    doc = parse_document(render(row.template), row.source_path)
    row.title, row.collection, row.language = doc.title, doc.collection, doc.language
    row.last_verified, row.doc_key = doc.last_verified, doc.doc_key
    row.edited_at, row.edited_by, row.updated_at = now, _username(db, actor), now
    db.flush()
    index = reindex(db, refit=False)
    return {**get_document(db, actor, row.id), "index": index}


@write_tool("hide_document")
def hide_document(db: Session, actor: Actor, document_id: int, now: datetime | None = None) -> dict:
    """Take a document out of the library and the assistant's search. A shipped one can be restored; one an
    admin added is deleted."""
    now = resolve_now(now)
    require_role(actor, "admin")
    row = _row(db, document_id, for_update=True)
    view = _row_view(row)
    if row.origin == "added":
        db.execute(delete(KbDocument).where(KbDocument.id == row.id))  # its chunks go with it (ON DELETE CASCADE)
        db.expunge(row)
        view["deleted"] = True
    else:
        row.hidden_at, row.edited_at, row.edited_by, row.updated_at = now, now, _username(db, actor), now
        view["hidden"] = True
    db.flush()
    return {**view, "index": reindex(db, refit=False)}


@write_tool("restore_document")
def restore_document(db: Session, actor: Actor, document_id: int, now: datetime | None = None) -> dict:
    now = resolve_now(now)
    require_role(actor, "admin")
    row = _row(db, document_id, for_update=True)
    if row.hidden_at is None:
        raise ToolError("INVALID_STATE", "This document is not hidden.")
    row.hidden_at, row.updated_at = None, now
    db.flush()
    return {**_row_view(row), "index": reindex(db, refit=False)}


@write_tool("revert_document")
def revert_document(
    db: Session, actor: Actor, document_id: int, root: Path = DEFAULT_ROOT, now: datetime | None = None
) -> dict:
    """Undo an admin's changes to a shipped document: back to the template as shipped."""
    now = resolve_now(now)
    require_role(actor, "admin")
    row = _row(db, document_id, for_update=True)
    if row.origin != "edited":
        raise ToolError("INVALID_STATE", "Only a shipped document that was edited can be reverted.")
    path = root.parent / row.source_path
    if not path.is_file():
        raise ToolError("NOT_FOUND", "The shipped version of this document no longer exists.")
    row.template = path.read_text(encoding="utf-8")
    doc = parse_document(render(row.template), row.source_path)
    row.title, row.last_verified = doc.title, doc.last_verified
    row.origin, row.edited_at, row.edited_by, row.updated_at = "template", now, _username(db, actor), now
    db.flush()
    return {**get_document(db, actor, row.id), "index": reindex(db, refit=False)}
