"""Knowledge-base documents: front matter parsing and chunking.

Documents are Markdown with a small front matter block (FR-20):

    ---
    title: Lipid profile
    collection: test_preparation
    language: en
    last_verified: 2026-10-01
    doc_key: test_preparation/lipid-profile
    ---
    # Lipid profile
    ## Before the test
    ...

Two chunkers are provided: structure-aware (one chunk per ``##`` section, long
sections split on paragraph boundaries) is the default; fixed-size windows are
kept for the chunking experiment in the evaluation plan.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

REQUIRED_META = ("title", "collection", "language", "last_verified", "doc_key")
MAX_CHUNK_CHARS = 900


@dataclass
class Section:
    heading: str
    body: str


@dataclass
class Document:
    source_path: str
    title: str
    collection: str
    language: str
    last_verified: date
    doc_key: str
    sections: list[Section] = field(default_factory=list)
    raw: str = ""

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.raw.encode()).hexdigest()


@dataclass(frozen=True)
class Chunk:
    index: int
    section: str
    text: str


def parse_document(raw: str, source_path: str) -> Document:
    match = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", raw, re.S)
    if not match:
        raise ValueError(f"{source_path}: missing front matter")
    meta = {}
    for line in match.group(1).splitlines():
        if line.strip():
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    missing = [k for k in REQUIRED_META if not meta.get(k)]
    if missing:
        raise ValueError(f"{source_path}: front matter lacks {', '.join(missing)}")
    if meta["language"] not in ("en", "hi", "mr"):
        raise ValueError(f"{source_path}: unsupported language {meta['language']}")

    sections: list[Section] = []
    heading, lines = "", []
    for line in match.group(2).splitlines():
        if line.startswith("## "):
            if heading or "".join(lines).strip():
                sections.append(Section(heading or meta["title"], "\n".join(lines).strip()))
            heading, lines = line[3:].strip(), []
        elif line.startswith("# "):
            continue
        else:
            lines.append(line)
    if heading or "".join(lines).strip():
        sections.append(Section(heading or meta["title"], "\n".join(lines).strip()))
    return Document(
        source_path=source_path,
        title=meta["title"],
        collection=meta["collection"],
        language=meta["language"],
        last_verified=date.fromisoformat(meta["last_verified"]),
        doc_key=meta["doc_key"],
        sections=[s for s in sections if s.body],
        raw=raw,
    )


PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def render(raw: str) -> str:
    """Fill the policy placeholders (``{{cancel_hours}}``) with the numbers in force."""
    from app.tools import policy

    values = policy.current()
    return PLACEHOLDER.sub(lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), raw)


def unknown_placeholders(raw: str) -> list[str]:
    from app.tools import policy

    return sorted({m for m in PLACEHOLDER.findall(raw) if m not in policy.current()})


def read_templates(root: Path) -> list[tuple[str, str]]:
    """(source path, Markdown with placeholders) for every document file under ``root``."""
    return [
        (path.relative_to(root.parent).as_posix(), path.read_text(encoding="utf-8"))
        for path in sorted(root.rglob("*.md"))
        if path.name.lower() != "readme.md"
    ]


def load_documents(root: Path) -> list[Document]:
    """The documents under ``root`` as readers see them: placeholders filled with the numbers in force."""
    return [parse_document(render(raw), source) for source, raw in read_templates(root)]


def _split_long(text: str, limit: int) -> list[str]:
    parts, current = [], ""
    for para in re.split(r"\n\s*\n|\n(?=- )", text):
        para = para.strip()
        if not para:
            continue
        if current and len(current) + len(para) + 1 > limit:
            parts.append(current)
            current = para
        else:
            current = f"{current}\n{para}" if current else para
    if current:
        parts.append(current)
    return parts


def structure_chunks(doc: Document, max_chars: int = MAX_CHUNK_CHARS) -> list[Chunk]:
    """One chunk per section, prefixed with the document title so each chunk stands alone."""
    chunks: list[Chunk] = []
    for section in doc.sections:
        for part in _split_long(section.body, max_chars):
            chunks.append(Chunk(len(chunks), section.heading, f"{doc.title} — {section.heading}\n{part}"))
    return chunks


def fixed_chunks(doc: Document, size: int = 500, overlap: int = 100) -> list[Chunk]:
    """Fixed character windows over the whole document (baseline for the chunking experiment)."""
    text = "\n".join(f"{s.heading}\n{s.body}" for s in doc.sections)
    chunks, start = [], 0
    while start < len(text):
        chunks.append(Chunk(len(chunks), doc.title, f"{doc.title}\n{text[start : start + size]}"))
        if start + size >= len(text):
            break
        start += size - overlap
    return chunks
