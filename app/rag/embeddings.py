"""Text embedders for dense retrieval.

* ``FastEmbedEmbedder`` - a multilingual sentence-embedding model run with ONNX
  Runtime (default: paraphrase-multilingual-MiniLM-L12-v2, 384 dimensions).
* ``LsaEmbedder`` - a deterministic local fallback (character n-gram TF-IDF
  reduced with truncated SVD) for environments where the neural model cannot be
  downloaded. It is fitted on the knowledge-base chunks themselves.

Every stored vector records the embedder's ``name``; queries only compare
vectors made by the same embedder.
"""

import hashlib
import logging
import os
import pickle
from collections.abc import Sequence
from typing import Protocol

import numpy as np

from app.db.models import EMBEDDING_DIM
from app.rag.text import normalize

log = logging.getLogger(__name__)


class Embedder(Protocol):
    name: str
    dim: int

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray: ...


def _normalize_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(np.float32)


class FastEmbedEmbedder:
    dim = EMBEDDING_DIM

    def __init__(self, model_name: str, cache_dir: str | None = None):
        from fastembed import TextEmbedding

        self.model_name = model_name
        self.name = f"fastembed:{model_name}"
        self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)
        probe = self._embed(["dimension probe"])
        if probe.shape[1] != self.dim:
            raise ValueError(f"{model_name} produces {probe.shape[1]}-d vectors; the schema stores {self.dim}")

    def _embed(self, texts: Sequence[str]) -> np.ndarray:
        return _normalize_rows(np.array(list(self._model.embed(list(texts))), dtype=np.float32))

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed(texts)

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed([text])[0]


class LsaEmbedder:
    """Character n-gram TF-IDF + truncated SVD, padded to the schema dimension."""

    dim = EMBEDDING_DIM
    version = "local-lsa-v1"

    def __init__(self, corpus: Sequence[str]):
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        if not corpus:
            raise ValueError("the LSA embedder needs a non-empty corpus")
        self.name = self.name_for(corpus)
        self._vectorizer = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True, min_df=1, preprocessor=normalize
        )
        tfidf = self._vectorizer.fit_transform(corpus)
        components = max(1, min(self.dim, tfidf.shape[0] - 1, tfidf.shape[1] - 1))
        self._svd = TruncatedSVD(n_components=components, algorithm="randomized", n_iter=7, random_state=0)
        self._svd.fit(tfidf)

    @classmethod
    def name_for(cls, corpus: Sequence[str]) -> str:
        digest = hashlib.sha256("\x1e".join(corpus).encode()).hexdigest()[:12]
        return f"{cls.version}:{digest}"

    def _project(self, texts: Sequence[str]) -> np.ndarray:
        reduced = self._svd.transform(self._vectorizer.transform(list(texts)))
        padded = np.zeros((reduced.shape[0], self.dim), dtype=np.float32)
        padded[:, : reduced.shape[1]] = reduced
        return _normalize_rows(padded)

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        return self._project(texts)

    def embed_query(self, text: str) -> np.ndarray:
        return self._project([text])[0]


# The last LSA embedder fitted or loaded in this process (one at a time: each holds tens of megabytes).
_lsa_memo: dict[str, LsaEmbedder] = {}


def _remember(embedder: LsaEmbedder) -> None:
    _lsa_memo.clear()
    _lsa_memo[embedder.name] = embedder


def _lsa_path(name: str, cache_dir: str) -> str:
    import sklearn

    return os.path.join(cache_dir, f"{name.replace(':', '-')}-sklearn{sklearn.__version__}.pkl")


def lsa_by_name(name: str, cache_dir: str | None) -> LsaEmbedder | None:
    """An LSA embedder already fitted, by its name: from this process or from ``cache_dir``. Never fits, so it
    is safe inside the 512 MB server (phase 7D: edited documents are embedded with the deployed embedder)."""
    if name in _lsa_memo:
        return _lsa_memo[name]
    if not cache_dir:
        return None
    path = _lsa_path(name, cache_dir)
    try:
        with open(path, "rb") as f:
            cached = pickle.load(f)
    except FileNotFoundError:
        return None
    except Exception as err:  # noqa: BLE001 - a damaged cache file is refitted
        log.warning("ignoring the cached LSA embedder %s (%s)", path, err)
        return None
    if not isinstance(cached, LsaEmbedder) or cached.name != name:
        return None
    _remember(cached)
    return cached


def load_or_fit_lsa(corpus: Sequence[str], cache_dir: str | None) -> LsaEmbedder:
    """The LSA embedder for this corpus, fitted once and kept in ``cache_dir`` when one is set.

    Fitting peaks at ~450 MB, so in the container it happens in the ingest step that runs before the
    server starts; the server then loads the fitted embedder (the fit is deterministic, so the vectors
    are the same either way) and stays within a 512 MB free-tier instance.
    """
    name = LsaEmbedder.name_for(corpus)
    known = lsa_by_name(name, cache_dir)
    if known is not None:
        return known
    embedder = LsaEmbedder(corpus)
    _remember(embedder)
    if not cache_dir:
        return embedder
    path = _lsa_path(name, cache_dir)
    try:
        os.makedirs(cache_dir, exist_ok=True)
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "wb") as f:
            pickle.dump(embedder, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, path)
    except OSError as err:
        log.warning("could not cache the LSA embedder in %s (%s)", cache_dir, err)
    return embedder


_neural_cache: dict[str, object] = {}


def load_neural_embedder(model_name: str, cache_dir: str | None) -> FastEmbedEmbedder | None:
    """Load (once) the neural embedder; None if it cannot be loaded here."""
    if model_name not in _neural_cache:
        try:
            _neural_cache[model_name] = FastEmbedEmbedder(model_name, cache_dir)
        except Exception as err:  # noqa: BLE001 - offline, blocked download, missing runtime...
            log.warning("neural embedder %s unavailable (%s); using the local fallback", model_name, err)
            _neural_cache[model_name] = None
    return _neural_cache[model_name]  # type: ignore[return-value]


def choose_embedder(backend: str, model_name: str, cache_dir: str | None, corpus: Sequence[str]) -> Embedder:
    """``auto``: neural if loadable, else local. ``fastembed``: neural or error. ``local``: local."""
    if backend not in ("auto", "fastembed", "local"):
        raise ValueError(f"unknown embedding backend {backend!r}")
    if backend != "local":
        neural = load_neural_embedder(model_name, cache_dir)
        if neural is not None:
            return neural
        if backend == "fastembed":
            raise RuntimeError(f"embedding model {model_name} could not be loaded")
    return load_or_fit_lsa(corpus, cache_dir)


def embedder_for_index(
    backend: str, model_name: str, cache_dir: str | None, corpus: Sequence[str], stored_models: set[str]
) -> Embedder:
    """The embedder that matches the stored chunks when it can be had without fitting; otherwise as
    ``choose_embedder``. Used by the server, which must not fit the LSA embedder (D-67)."""
    if backend == "local" or (backend == "auto" and load_neural_embedder(model_name, cache_dir) is None):
        if len(stored_models) == 1:
            (name,) = stored_models
            known = lsa_by_name(name, cache_dir) if name.startswith(LsaEmbedder.version) else None
            if known is not None:
                return known
    return choose_embedder(backend, model_name, cache_dir, corpus)
