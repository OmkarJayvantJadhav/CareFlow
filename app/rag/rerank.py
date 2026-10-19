"""Re-rankers. Scores are in [0, 1] so one relevance threshold works for both.

* ``CrossEncoderReranker`` - an open-source multilingual cross-encoder
  (default BAAI/bge-reranker-v2-m3, int8 ONNX) run with fastembed.
* ``LexicalReranker`` - fallback when the model cannot be loaded: IDF-weighted
  coverage of the query's content words in the chunk (with prefix matching for
  inflected forms); the first-stage fusion score only breaks ties.
"""

import logging
import math
from collections.abc import Sequence
from typing import Protocol

from app.rag.text import content_tokens, stem

log = logging.getLogger(__name__)


class Reranker(Protocol):
    name: str

    def score(self, query: str, texts: Sequence[str], prior: Sequence[float]) -> list[float]: ...


class CrossEncoderReranker:
    def __init__(self, model_name: str, cache_dir: str | None = None):
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self.name = f"cross-encoder:{model_name}"
        self._model = TextCrossEncoder(model_name=model_name, cache_dir=cache_dir)

    def score(self, query: str, texts: Sequence[str], prior: Sequence[float]) -> list[float]:
        logits = list(self._model.rerank(query, list(texts)))
        return [1.0 / (1.0 + math.exp(-float(x))) for x in logits]


class LexicalReranker:
    name = "lexical-v1"

    def __init__(self, idf: dict[str, float] | None = None, default_idf: float = 1.0):
        self._idf = idf or {}
        self._default_idf = default_idf

    @staticmethod
    def _matches(token: str, vocabulary: set[str], stems: set[str]) -> bool:
        if token in vocabulary:
            return True
        root = stem(token)
        if len(root) < 3:
            return False
        if root in stems:
            return True
        # One stem a prefix of the other: "verifi" ~ "verific", "मुल" ~ "मुलां".
        return any(len(other) >= 3 and (other.startswith(root) or root.startswith(other)) for other in stems)

    def score(self, query: str, texts: Sequence[str], prior: Sequence[float]) -> list[float]:
        terms = list(dict.fromkeys(content_tokens(query)))
        top_prior = max(prior) if prior else 0.0
        scores = []
        for text, p in zip(texts, prior, strict=True):
            vocabulary = set(content_tokens(text))
            stems = {stem(w) for w in vocabulary}
            if not terms:
                coverage = 0.0
            else:
                weights = [self._idf.get(t, self._default_idf) for t in terms]
                matched = sum(w for t, w in zip(terms, weights, strict=True) if self._matches(t, vocabulary, stems))
                coverage = matched / sum(weights)
            scores.append(0.9 * coverage + 0.1 * (p / top_prior if top_prior else 0.0))
        return scores


_cross_cache: dict[str, object] = {}


def choose_reranker(backend: str, model_name: str, cache_dir: str | None, idf: dict[str, float]) -> Reranker:
    if backend not in ("auto", "cross-encoder", "local"):
        raise ValueError(f"unknown reranker backend {backend!r}")
    if backend != "local":
        if model_name not in _cross_cache:
            try:
                _cross_cache[model_name] = CrossEncoderReranker(model_name, cache_dir)
            except Exception as err:  # noqa: BLE001 - offline, blocked download, missing runtime...
                log.warning("cross-encoder %s unavailable (%s); using the lexical re-ranker", model_name, err)
                _cross_cache[model_name] = None
        model = _cross_cache[model_name]
        if model is not None:
            return model  # type: ignore[return-value]
        if backend == "cross-encoder":
            raise RuntimeError(f"re-ranker {model_name} could not be loaded")
    default_idf = max(idf.values()) if idf else 1.0
    return LexicalReranker(idf, default_idf)
