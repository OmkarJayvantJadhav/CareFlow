"""Load the knowledge base: the shipped templates into kb_document, then chunks and embeddings into kb_chunk.

python -m app.rag.ingest [--if-needed] [--chunker structure|fixed] [--root knowledge]

Documents admins edited, added or hid in the app are kept (app.rag.kb). The policy numbers in force are read
from the database first, so the documents state the hospital's own rules.
"""

import argparse
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.session import session_scope
from app.rag.chunking import Chunk, Document
from app.rag.kb import CHUNKERS, DEFAULT_ROOT, reindex, sync_templates
from app.safety.privacy import install_log_masking
from app.tools.policy_settings import load_policy

__all__ = ["DEFAULT_ROOT", "build_chunks", "ingest"]


def build_chunks(docs: list[Document], chunker: str) -> list[tuple[Document, Chunk]]:
    split = CHUNKERS[chunker]
    pairs = [(doc, chunk) for doc in docs for chunk in split(doc)]
    return sorted(pairs, key=lambda p: (p[0].source_path, p[1].index))


def ingest(db: Session, root: Path = DEFAULT_ROOT, chunker: str = "structure", if_needed: bool = False) -> dict:
    """Load the templates and index them; with ``if_needed`` only what changed is re-embedded."""
    templates = sync_templates(db, root)
    result = reindex(db, chunker, force=not if_needed)
    status = "up to date" if if_needed and not result["reindexed"] and not any(templates.values()) else "ingested"
    return {"status": status, **templates, **result, "chunker": chunker}


def main(argv: list[str] | None = None) -> int:
    install_log_masking()
    parser = argparse.ArgumentParser(prog="python -m app.rag.ingest")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--chunker", choices=sorted(CHUNKERS), default="structure")
    parser.add_argument("--if-needed", action="store_true", help="re-embed only documents that changed")
    args = parser.parse_args(argv)
    with session_scope() as db:
        load_policy(db)
        result = ingest(db, args.root, args.chunker, args.if_needed)
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
