"""
RAG Retriever — query side of the pipeline.
"""

from __future__ import annotations
import asyncio
import logging
from typing import List, Optional
from dataclasses import dataclass

from app.core.config import settings
from app.services import vector_store
from app.services.embedder import embed_query, rerank

logger = logging.getLogger(__name__)

_SYNTHESIS_KEYWORDS = {
    "summary", "summarize", "summarise", "overview", "about",
    "what is this", "what does this", "explain", "tell me about",
    "key points", "main points", "highlights", "what topics", "introduction",
}


@dataclass
class RetrievedChunk:
    doc_id:       str
    filename:     str
    chunk_index:  int
    text:         str
    vector_score: float
    rerank_score: float


def _is_synthesis_query(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in _SYNTHESIS_KEYWORDS)


async def retrieve_and_rerank(
    query:              str,
    doc_id_to_filename: dict,
    document_ids:       Optional[List[str]] = None,
) -> List[RetrievedChunk]:
    # For summary/overview queries fetch more chunks so the LLM sees the full document
    top_k_retrieve = settings.TOP_K_RETRIEVE * 2 if _is_synthesis_query(query) else settings.TOP_K_RETRIEVE
    top_k_rerank   = settings.TOP_K_RERANK   * 2 if _is_synthesis_query(query) else settings.TOP_K_RERANK

    results = await asyncio.to_thread(_retrieve_sync, query, document_ids, top_k_retrieve)

    if not results:
        return []

    chunks_text = [r["text"] for r in results]
    scores      = await asyncio.to_thread(rerank, query, chunks_text)

    ranked = sorted(zip(results, scores), key=lambda x: x[1], reverse=True)
    top    = ranked[: top_k_rerank]

    retrieved = []
    for result, rscore in top:
        # Use filename from FAISS metadata (stored at index time)
        filename = result.get("filename") or doc_id_to_filename.get(result["doc_id"], "unknown")
        retrieved.append(RetrievedChunk(
            doc_id       = result["doc_id"],
            filename     = filename,
            chunk_index  = result["chunk_index"],
            text         = result["text"],
            vector_score = result["score"],
            rerank_score = rscore,
        ))

    if retrieved:
        logger.info(
            f"Retrieved {len(retrieved)} chunks (top rerank: {retrieved[0].rerank_score:.3f})"
        )
    return retrieved


def _retrieve_sync(query: str, document_ids: Optional[List[str]], top_k: int = None) -> list:
    q_vec = embed_query(query)
    return vector_store.search(
        query_embedding=q_vec,
        top_k=top_k or settings.TOP_K_RETRIEVE,
        doc_ids=document_ids,
    )
