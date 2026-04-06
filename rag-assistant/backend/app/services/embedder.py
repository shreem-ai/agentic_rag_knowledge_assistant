"""
Embedding service using sentence-transformers.

Model: all-MiniLM-L6-v2
  - 384-dimensional vectors
  - Runs fully locally, no API key needed
  - ~80MB download on first use (cached by HuggingFace)
  - Fast: ~2000 sentences/second on CPU

The model is loaded once at startup (singleton pattern) to avoid
re-loading 80MB on every request.
"""

from __future__ import annotations
import logging
import numpy as np
from typing import List

logger = logging.getLogger(__name__)

# Module-level singleton — loaded once, reused for every request
_embedder = None
_reranker = None


def get_embedder():
    """Return the singleton SentenceTransformer instance, loading it on first call."""
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        from app.core.config import settings
        logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL}")
        _embedder = SentenceTransformer(settings.EMBEDDING_MODEL)
        logger.info("Embedding model loaded.")
    return _embedder


def get_reranker():
    """Return the singleton CrossEncoder instance, loading it on first call."""
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        from app.core.config import settings
        logger.info(f"Loading reranker model: {settings.RERANKER_MODEL}")
        _reranker = CrossEncoder(settings.RERANKER_MODEL)
        logger.info("Reranker model loaded.")
    return _reranker


def embed_texts(texts: List[str]) -> np.ndarray:
    """
    Generate embeddings for a list of text strings.

    Args:
        texts: List of strings to embed.

    Returns:
        numpy array of shape (len(texts), 384) — float32.
    """
    if not texts:
        return np.array([])

    model = get_embedder()
    # normalize_embeddings=True → cosine similarity == dot product
    embeddings = model.encode(
        texts,
        batch_size=64,
        show_progress_bar=False,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    return embeddings.astype(np.float32)


def embed_query(query: str) -> np.ndarray:
    """
    Embed a single query string.

    Returns:
        1-D numpy array of shape (384,) — float32.
    """
    result = embed_texts([query])
    return result[0]


def rerank(query: str, chunks: List[str]) -> List[float]:
    """
    Score each (query, chunk) pair using the cross-encoder reranker.

    Args:
        query:  The user's question.
        chunks: List of candidate chunk texts.

    Returns:
        List of float scores, one per chunk. Higher = more relevant.
    """
    if not chunks:
        return []

    model = get_reranker()
    pairs = [(query, chunk) for chunk in chunks]
    scores = model.predict(pairs, show_progress_bar=False)

    # CrossEncoder returns raw logits; convert to list of Python floats
    return [float(s) for s in scores]
