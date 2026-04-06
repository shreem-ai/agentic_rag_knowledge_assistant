"""
Vector store using FAISS (Facebook AI Similarity Search).

Design:
  - One global FAISS flat index (IndexFlatIP = inner product, works like
    cosine similarity when embeddings are L2-normalised).
  - A parallel metadata list stores chunk text + doc_id + filename per vector.
  - Both are persisted to disk after every write so they survive restarts.
  - The index is loaded into memory once and kept there (fast reads).

Files written to VECTOR_STORE_DIR:
  - index.faiss   — the FAISS binary index
  - metadata.json — list of {doc_id, filename, chunk_index, text, vector_idx}

Thread safety: writes are protected by a threading.Lock.
Reads (search) are lock-free since FAISS reads are thread-safe.
"""

from __future__ import annotations
import json
import logging
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384
INDEX_FILE    = "index.faiss"
META_FILE     = "metadata.json"

_index    = None
_metadata: List[Dict[str, Any]] = []
_lock     = threading.Lock()


def add_chunks(
    doc_id:    str,
    filename:  str,
    chunks:    List[str],
    embeddings: np.ndarray,
) -> None:
    """Add a document's chunks + embeddings to the FAISS index."""
    global _index, _metadata

    if len(chunks) != embeddings.shape[0]:
        raise ValueError("chunks and embeddings length mismatch")

    import faiss

    with _lock:
        _ensure_loaded()

        start_idx = len(_metadata)
        for i, text in enumerate(chunks):
            _metadata.append({
                "doc_id":      doc_id,
                "filename":    filename,
                "chunk_index": i,
                "text":        text,
                "vector_idx":  start_idx + i,
            })

        _index.add(embeddings.astype(np.float32))
        _persist()

    logger.info(f"Added {len(chunks)} chunks for doc {doc_id}. Index size: {_index.ntotal}")


def search(
    query_embedding: np.ndarray,
    top_k: int,
    doc_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Find top_k most similar chunks. Returns list sorted by score desc."""
    _ensure_loaded()

    if _index is None or _index.ntotal == 0:
        return []

    query   = query_embedding.reshape(1, -1).astype(np.float32)
    fetch_k = min(_index.ntotal, top_k * 5 if doc_ids else top_k)
    scores, indices = _index.search(query, fetch_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:
            continue
        meta = _metadata[idx]
        if doc_ids and meta["doc_id"] not in doc_ids:
            continue
        results.append({
            "doc_id":      meta["doc_id"],
            "filename":    meta.get("filename", ""),
            "chunk_index": meta["chunk_index"],
            "text":        meta["text"],
            "score":       float(score),
        })
        if len(results) >= top_k:
            break

    return results


def delete_document(doc_id: str) -> int:
    """Remove all chunks for doc_id. Returns number of vectors removed."""
    global _index, _metadata

    import faiss

    with _lock:
        _ensure_loaded()

        keep    = [m for m in _metadata if m["doc_id"] != doc_id]
        removed = len(_metadata) - len(keep)

        if removed == 0:
            return 0

        new_index = faiss.IndexFlatIP(EMBEDDING_DIM)
        if keep:
            kept_indices = [m["vector_idx"] for m in keep]
            vectors = np.zeros((len(keep), EMBEDDING_DIM), dtype=np.float32)
            for new_pos, old_idx in enumerate(kept_indices):
                _index.reconstruct(int(old_idx), vectors[new_pos])
            new_index.add(vectors)

        for i, m in enumerate(keep):
            m["vector_idx"] = i

        _index    = new_index
        _metadata = keep
        _persist()

    logger.info(f"Deleted {removed} chunks for doc {doc_id}.")
    return removed


def chunk_count_for_doc(doc_id: str) -> int:
    _ensure_loaded()
    return sum(1 for m in _metadata if m["doc_id"] == doc_id)


def _store_dir() -> Path:
    d = Path(settings.VECTOR_STORE_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ensure_loaded() -> None:
    global _index, _metadata

    if _index is not None:
        return

    import faiss

    idx_path  = _store_dir() / INDEX_FILE
    meta_path = _store_dir() / META_FILE

    if idx_path.exists() and meta_path.exists():
        logger.info("Loading existing FAISS index from disk.")
        _index    = faiss.read_index(str(idx_path))
        _metadata = json.loads(meta_path.read_text())
        logger.info(f"FAISS index loaded: {_index.ntotal} vectors.")
    else:
        logger.info("Creating new FAISS index.")
        _index    = faiss.IndexFlatIP(EMBEDDING_DIM)
        _metadata = []


def _persist() -> None:
    import faiss
    d = _store_dir()
    faiss.write_index(_index, str(d / INDEX_FILE))
    (d / META_FILE).write_text(json.dumps(_metadata, ensure_ascii=False))
