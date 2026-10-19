"""Download the neural retrieval models ahead of time (used while building the Docker image).

    python -m app.rag.preload

Never fails: where the models cannot be downloaded, the app falls back to the
local embedder and re-ranker at run time.
"""

import sys

from app.config import get_settings
from app.rag.embeddings import load_neural_embedder
from app.rag.rerank import choose_reranker


def main() -> int:
    settings = get_settings()
    embedder = load_neural_embedder(settings.embedding_model, settings.model_cache_dir)
    reranker = choose_reranker("auto", settings.reranker_model, settings.model_cache_dir, {})
    print(f"embedder: {embedder.name if embedder else 'unavailable (local fallback will be used)'}")
    print(f"reranker: {reranker.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
