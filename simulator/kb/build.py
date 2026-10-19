"""Render the synthetic knowledge base to Markdown files under knowledge/<lang>/<collection>/.

python -m simulator.kb.build [--root knowledge]
"""

import argparse
import sys
from pathlib import Path

from simulator.kb import departments, facilities, insurance, policies, test_prep
from simulator.kb.common import LANGS, LAST_VERIFIED, KbDoc

DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "knowledge"
COLLECTIONS = ("policies", "insurance", "departments", "doctors", "test_preparation", "facilities")


def all_documents() -> list[KbDoc]:
    docs = policies.build() + insurance.build() + departments.build() + test_prep.build() + facilities.build()
    keys = [d.doc_key for d in docs]
    duplicates = {k for k in keys if keys.count(k) > 1}
    if duplicates:
        raise ValueError(f"duplicate document keys: {sorted(duplicates)}")
    unknown = {d.collection for d in docs} - set(COLLECTIONS)
    if unknown:
        raise ValueError(f"unknown collections: {sorted(unknown)}")
    return docs


def render(doc: KbDoc, lang: str) -> str:
    title = doc.title[lang]
    lines = [
        "---",
        f"title: {title}",
        f"collection: {doc.collection}",
        f"language: {lang}",
        f"last_verified: {LAST_VERIFIED.isoformat()}",
        f"doc_key: {doc.doc_key}",
        "---",
        f"# {title}",
        "",
    ]
    for heading, body in doc.sections:
        lines += [f"## {heading[lang]}", "", body[lang].strip(), ""]
    return "\n".join(lines)


def build(root: Path = DEFAULT_ROOT) -> dict:
    written = set()
    for doc in all_documents():
        for lang in LANGS:
            path = root / lang / doc.collection / f"{doc.slug}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            content = render(doc, lang)
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                path.write_text(content, encoding="utf-8")
            written.add(path)
    removed = 0
    for path in root.rglob("*.md"):
        if path.name.lower() != "readme.md" and path not in written:
            path.unlink()
            removed += 1
    return {"documents": len(written), "removed": removed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m simulator.kb.build")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args(argv)
    print(build(args.root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
