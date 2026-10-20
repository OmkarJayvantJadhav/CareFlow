"""RAG evaluation (docs §14.2) on eval/datasets/rag_questions.jsonl.

    python -m eval.run_rag                  # retrieval experiments (no LLM)
    python -m eval.run_rag --answers --llm groq:openai/gpt-oss-120b --judge gemini:gemini-3.5-flash-lite

Retrieval (no LLM):
* recall@5 - share of answerable questions with a gold section among the top 5 chunks (a chunk in any
  language counts, since translations have the same sections in the same order); MRR@5 alongside;
* retrieval configurations: dense only, BM25 only, hybrid (RRF), hybrid + re-ranker (production,
  with and without its relevance threshold);
* chunking: structure-aware (one chunk per section, production) vs fixed 500-character windows with
  100 characters of overlap, ingested into a second database (a window is credited with the section
  it overlaps most and with any section at least 80% inside it);
* unanswerable questions: share for which the production retriever returns no source (the agent
  then says it does not know), and answerable questions wrongly left without a source.

Answers (--answers, uses an LLM): each question is asked through the real chat (the agent decides to
search); a judge model grades correctness against the reference answer and faithfulness to the
cited sources; unanswerable questions must be declined.
"""

import argparse
import json
import statistics
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

import app.rag.retriever as retriever_module
from app.config import get_settings
from app.db.session import normalize_url
from app.rag.chunking import load_documents
from app.rag.embeddings import choose_embedder
from app.rag.ingest import DEFAULT_ROOT, build_chunks, ingest
from app.rag.rerank import choose_reranker
from app.rag.retriever import KbIndex, Retriever
from eval.common import isolated, load_jsonl, prepare_world, run_header, write_result

QUESTIONS = "eval/datasets/rag_questions.jsonl"
TOP_K = 5
FIXED_SIZE, FIXED_OVERLAP = 500, 100
CONFIGS = {
    "dense": {"use_dense": True, "use_sparse": False, "use_reranker": False},
    "bm25": {"use_dense": False, "use_sparse": True, "use_reranker": False},
    "hybrid": {"use_dense": True, "use_sparse": True, "use_reranker": False},
    "hybrid+rerank (no threshold)": {"use_dense": True, "use_sparse": True, "use_reranker": True, "threshold": False},
    "hybrid+rerank": {"use_dense": True, "use_sparse": True, "use_reranker": True},
}


class SectionMap:
    """Which document sections (by position) a retrieved chunk covers, for either chunker."""

    def __init__(self, root: Path = DEFAULT_ROOT):
        self.docs = {(d.doc_key, d.language): d for d in load_documents(root)}

    def gold(self, item: dict) -> set[tuple[str, int]]:
        out = set()
        for g in item["gold"]:
            doc = self.docs[(g["doc_key"], "en")]
            headings = [s.heading for s in doc.sections]
            out.add((g["doc_key"], headings.index(g["section"])))
        return out

    def covered(self, chunk, chunker: str) -> set[tuple[str, int]]:
        doc = self.docs.get((chunk.doc_key, chunk.language))
        if doc is None:
            return set()
        if chunker == "structure":
            headings = [s.heading for s in doc.sections]
            return {(chunk.doc_key, headings.index(chunk.section))} if chunk.section in headings else set()
        # Fixed windows over "\n".join(heading + body): a window is credited with the section it
        # overlaps most, and with any section that lies at least 80% inside it.
        spans, offset = [], 0
        for s in doc.sections:
            block = f"{s.heading}\n{s.body}"
            spans.append((offset, offset + len(block)))
            offset += len(block) + 1
        start = chunk.chunk_index * (FIXED_SIZE - FIXED_OVERLAP)
        end = start + FIXED_SIZE
        overlaps = [min(b, end) - max(a, start) for a, b in spans]
        best = max(range(len(spans)), key=lambda i: overlaps[i])
        out = {(chunk.doc_key, best)} if overlaps[best] > 0 else set()
        out |= {(chunk.doc_key, i) for i, (a, b) in enumerate(spans) if overlaps[i] >= 0.8 * (b - a)}
        return out


@contextmanager
def threshold_off():
    saved = dict(retriever_module.RELEVANCE_THRESHOLD)
    retriever_module.RELEVANCE_THRESHOLD.clear()
    try:
        yield
    finally:
        retriever_module.RELEVANCE_THRESHOLD.update(saved)


def build_retriever(db: Session) -> Retriever:
    settings = get_settings()
    index = KbIndex.load(db)
    embedder = choose_embedder(
        settings.embedding_backend, settings.embedding_model, settings.model_cache_dir, index.texts or ["∅"]
    )
    reranker = choose_reranker(settings.reranker_backend, settings.reranker_model, settings.model_cache_dir, index.idf)
    return Retriever(index, embedder, reranker)


def fixed_database() -> sessionmaker:
    """A second database with the same documents cut into fixed windows."""
    base = get_settings().database_url
    url = base.rsplit("/", 1)[0] + "/careflow_eval_fixed"
    admin = create_engine(normalize_url(base.rsplit("/", 1)[0] + "/postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        if not conn.execute(text("SELECT 1 FROM pg_database WHERE datname = 'careflow_eval_fixed'")).first():
            conn.execute(text("CREATE DATABASE careflow_eval_fixed"))
    admin.dispose()
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", normalize_url(url))
    command.upgrade(cfg, "head")
    factory = sessionmaker(bind=create_engine(normalize_url(url)), expire_on_commit=False)
    with factory() as db:
        stored = db.scalar(text("SELECT count(*) FROM kb_chunk"))
        if stored != len(build_chunks(load_documents(DEFAULT_ROOT), "fixed")):
            ingest(db, chunker="fixed")
            db.commit()
    return factory


def evaluate(db, retriever: Retriever, questions: list[dict], sections: SectionMap, chunker: str, config: dict) -> dict:
    options = {k: v for k, v in config.items() if k != "threshold"}
    rows = []
    for q in questions:
        started = time.perf_counter()
        if config.get("threshold", True):
            chunks = retriever.search(db, q["question"], language=q["language"], top_k=TOP_K, **options)
        else:
            with threshold_off():
                chunks = retriever.search(db, q["question"], language=q["language"], top_k=TOP_K, **options)
        latency = (time.perf_counter() - started) * 1000
        gold = sections.gold(q) if q["answerable"] else set()
        rank = None
        for i, chunk in enumerate(chunks, 1):
            if sections.covered(chunk, chunker) & gold:
                rank = i
                break
        rows.append(
            {
                "id": q["id"],
                "language": q["language"],
                "collection": q["collection"],
                "answerable": q["answerable"],
                "hit_rank": rank,
                "returned": len(chunks),
                "top": [f"{c.doc_key}#{c.chunk_index}:{c.language}" for c in chunks],
                "latency_ms": round(latency, 1),
            }
        )
    answerable = [r for r in rows if r["answerable"]]
    unanswerable = [r for r in rows if not r["answerable"]]

    def recall(subset):
        return round(sum(r["hit_rank"] is not None for r in subset) / len(subset), 4) if subset else None

    by_language = {lang: recall([r for r in answerable if r["language"] == lang]) for lang in ("en", "hi", "mr")}
    by_collection = {
        c: recall([r for r in answerable if r["collection"] == c])
        for c in sorted({r["collection"] for r in answerable})
    }
    return {
        "recall_at_5": recall(answerable),
        "mrr_at_5": round(sum(1 / r["hit_rank"] for r in answerable if r["hit_rank"]) / len(answerable), 4),
        "recall_by_language": by_language,
        "recall_by_collection": by_collection,
        "unanswerable_no_source": round(sum(r["returned"] == 0 for r in unanswerable) / len(unanswerable), 4),
        "answerable_no_source": round(sum(r["returned"] == 0 for r in answerable) / len(answerable), 4),
        "median_latency_ms": round(statistics.median(r["latency_ms"] for r in rows), 1),
        "questions": len(rows),
        "rows": rows,
    }


def threshold_cv(db, retriever: Retriever, questions: list[dict], sections: SectionMap, folds: int = 5) -> dict:
    """Choose the re-ranker's relevance threshold by k-fold cross-validation.

    A question counts as handled correctly if it is answerable and a gold section is among the
    top 5 chunks that clear the threshold, or unanswerable and no chunk clears it. The threshold
    with the best accuracy on k-1 folds is scored on the held-out fold.
    """
    scored = []
    for q in questions:
        with threshold_off():
            chunks = retriever.search(db, q["question"], language=q["language"], top_k=TOP_K)
        gold = sections.gold(q) if q["answerable"] else set()
        scored.append(
            {
                "answerable": q["answerable"],
                "top": max((c.score for c in chunks), default=0.0),
                "gold": max((c.score for c in chunks if sections.covered(c, "structure") & gold), default=None),
            }
        )
    grid = [round(0.2 + 0.025 * i, 3) for i in range(17)]

    def correct(row: dict, t: float) -> bool:
        if row["answerable"]:
            return row["gold"] is not None and row["gold"] >= t
        return row["top"] < t

    def accuracy(rows: list[dict], t: float) -> float:
        return sum(correct(r, t) for r in rows) / len(rows)

    # Stratified folds: answerable and unanswerable questions dealt round-robin.
    order = [i for i, r in enumerate(scored) if r["answerable"]] + [
        i for i, r in enumerate(scored) if not r["answerable"]
    ]
    fold_of = {i: n % folds for n, i in enumerate(order)}
    per_fold, held_out = [], []
    for k in range(folds):
        train = [r for i, r in enumerate(scored) if fold_of[i] != k]
        test = [r for i, r in enumerate(scored) if fold_of[i] == k]
        best = max(grid, key=lambda t: (accuracy(train, t), -t))
        per_fold.append(best)
        held_out.extend((r, best) for r in test)
    answerable = [(r, t) for r, t in held_out if r["answerable"]]
    unanswerable = [(r, t) for r, t in held_out if not r["answerable"]]
    final = max(grid, key=lambda t: (accuracy(scored, t), -t))
    return {
        "reranker": retriever.reranker.name,
        "grid": grid,
        "chosen_per_fold": per_fold,
        "chosen_on_all_questions": final,
        "cross_validated": {
            "accuracy": round(sum(correct(r, t) for r, t in held_out) / len(held_out), 4),
            "recall_at_5": round(sum(correct(r, t) for r, t in answerable) / len(answerable), 4),
            "unanswerable_no_source": round(sum(correct(r, t) for r, t in unanswerable) / len(unanswerable), 4),
        },
    }


def retrieval_experiments(questions: list[dict]) -> dict:
    sections = SectionMap()
    out: dict = {"structure": {}, "fixed": {}}
    with isolated() as db:
        retriever = build_retriever(db)
        models = {"embedder": retriever.embedder.name, "reranker": retriever.reranker.name}
        for name, config in CONFIGS.items():
            out["structure"][name] = evaluate(db, retriever, questions, sections, "structure", config)
            print(f"structure {name:30} recall@5={out['structure'][name]['recall_at_5']}", file=sys.stderr)
        out["threshold_cv"] = threshold_cv(db, retriever, questions, sections)
        print(f"threshold CV: {out['threshold_cv']}", file=sys.stderr)
    factory = fixed_database()
    with factory() as db:
        retriever = build_retriever(db)
        for name, config in CONFIGS.items():
            out["fixed"][name] = evaluate(db, retriever, questions, sections, "fixed", config)
            print(f"fixed     {name:30} recall@5={out['fixed'][name]['recall_at_5']}", file=sys.stderr)
    out["models"] = models
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.run_rag")
    parser.add_argument("--answers", action="store_true", help="also grade answers with an LLM")
    parser.add_argument("--llm", default="groq:openai/gpt-oss-120b")
    parser.add_argument("--judge", default="gemini:gemini-3.5-flash-lite")
    parser.add_argument("--limit", type=int, default=None, help="grade only the first N questions")
    args = parser.parse_args(argv)
    prepare_world()
    questions = load_jsonl(QUESTIONS)
    results = {
        "header": run_header(questions=len(questions), top_k=TOP_K),
        "retrieval": retrieval_experiments(questions),
    }
    summary = {
        chunker: {name: {k: v[k] for k in ("recall_at_5", "mrr_at_5", "unanswerable_no_source", "answerable_no_source")}
                  for name, v in results["retrieval"][chunker].items()}
        for chunker in ("structure", "fixed")
    }  # fmt: skip
    results["summary"] = summary
    if args.answers:
        from eval.rag_answers import grade_answers

        results["answers"] = grade_answers(questions[: args.limit] if args.limit else questions, args.llm, args.judge)
    path = write_result("rag.json", results)
    print(json.dumps({"summary": summary, "models": results["retrieval"]["models"]}, indent=2))
    print(f"written to {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
