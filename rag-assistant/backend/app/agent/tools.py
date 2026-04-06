"""
ADK Agent Tools — Phase 4.

Four tools the agent can call to orchestrate the RAG pipeline:

  1. retrieve_documents   — embed query + FAISS vector search
  2. rerank_results       — cross-encoder reranking of candidates
  3. summarize_context    — condense chunks when total context is too long
  4. generate_answer      — call Gemini with context + history

Each tool is a plain Python function. Google ADK inspects the function
signature and docstring to decide when to call it.

Design note:
  ADK tools are synchronous functions that run in a thread pool.
  State (retrieved chunks, reranked results) is passed between tools
  via the AgentContext store, not via global variables.
"""

from __future__ import annotations
import asyncio
import logging
from typing import Optional

from app.core.config import settings
from app.services import vector_store
from app.services.embedder import embed_query, rerank as cross_encoder_rerank
from app.services.prompt_builder import build_prompt

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Tool 1 — retrieve_documents
# ══════════════════════════════════════════════════════════════════════════════

def retrieve_documents(
    query: str,
    document_ids: Optional[str] = None,
) -> dict:
    """
    Search the vector database for chunks relevant to the query.

    Use this tool first whenever the user asks a question about their documents.
    It embeds the query and performs a similarity search over all indexed chunks.

    Args:
        query:        The user's question or search query.
        document_ids: Comma-separated list of document IDs to restrict search to.
                      Pass None or empty string to search all documents.

    Returns:
        A dict with:
          - chunks: list of {doc_id, filename, chunk_index, text, score}
          - total:  number of chunks retrieved
    """
    logger.info(f"[tool:retrieve_documents] query={query!r}")

    # Parse optional comma-separated doc IDs
    doc_ids = None
    if document_ids and document_ids.strip():
        doc_ids = [d.strip() for d in document_ids.split(",") if d.strip()]

    # Embed the query and search
    q_vec = embed_query(query)
    raw   = vector_store.search(
        query_embedding=q_vec,
        top_k=settings.TOP_K_RETRIEVE,
        doc_ids=doc_ids,
    )

    chunks = [
        {
            "doc_id":      r["doc_id"],
            "chunk_index": r["chunk_index"],
            "text":        r["text"],
            "score":       round(r["score"], 4),
            "filename":    r.get("filename", ""),
        }
        for r in raw
    ]

    logger.info(f"[tool:retrieve_documents] found {len(chunks)} chunks")
    return {"chunks": chunks, "total": len(chunks)}


# ══════════════════════════════════════════════════════════════════════════════
# Tool 2 — rerank_results
# ══════════════════════════════════════════════════════════════════════════════

def rerank_results(
    query: str,
    chunks_json: str,
) -> dict:
    """
    Rerank a list of retrieved chunks using a cross-encoder model.

    Call this after retrieve_documents to improve precision.
    The cross-encoder scores each (query, chunk) pair together,
    which is more accurate than embedding similarity alone.

    Args:
        query:       The original user question.
        chunks_json: JSON string of the chunks list returned by retrieve_documents.
                     Each item must have a "text" field.

    Returns:
        A dict with:
          - chunks: reranked list sorted by rerank_score descending (top TOP_K_RERANK only)
          - total:  number of chunks after reranking
    """
    import json as _json

    logger.info(f"[tool:rerank_results] query={query!r}")

    try:
        chunks = _json.loads(chunks_json)
    except Exception as e:
        return {"error": f"Invalid chunks_json: {e}", "chunks": [], "total": 0}

    if not chunks:
        return {"chunks": [], "total": 0}

    texts  = [c["text"] for c in chunks]
    scores = cross_encoder_rerank(query, texts)

    # Attach rerank score and sort descending
    for chunk, score in zip(chunks, scores):
        chunk["rerank_score"] = round(float(score), 4)

    ranked = sorted(chunks, key=lambda c: c["rerank_score"], reverse=True)
    top    = ranked[: settings.TOP_K_RERANK]

    logger.info(
        f"[tool:rerank_results] top score={top[0]['rerank_score']:.3f} "
        f"returning {len(top)} chunks"
    )
    return {"chunks": top, "total": len(top)}


# ══════════════════════════════════════════════════════════════════════════════
# Tool 3 — summarize_context
# ══════════════════════════════════════════════════════════════════════════════

def summarize_context(
    chunks_json: str,
    max_words: int = 600,
) -> dict:
    """
    Condense retrieved chunks when total context exceeds the token budget.

    Call this when the reranked chunks are very long (e.g., each chunk is
    500+ words and you have 4 of them). Truncates each chunk to fit within
    the word budget while preserving the beginning of each chunk where the
    most relevant sentence usually appears after reranking.

    Args:
        chunks_json: JSON string of reranked chunks (from rerank_results).
        max_words:   Target total word count across all chunks.

    Returns:
        A dict with:
          - chunks:     condensed chunks with shortened "text" fields
          - total_words: actual word count of condensed context
    """
    import json as _json

    logger.info(f"[tool:summarize_context] max_words={max_words}")

    try:
        chunks = _json.loads(chunks_json)
    except Exception as e:
        return {"error": f"Invalid chunks_json: {e}", "chunks": [], "total_words": 0}

    if not chunks:
        return {"chunks": [], "total_words": 0}

    # Calculate current total word count
    total_words = sum(len(c["text"].split()) for c in chunks)

    if total_words <= max_words:
        # No condensation needed
        return {"chunks": chunks, "total_words": total_words}

    # Distribute word budget proportionally across chunks
    words_per_chunk = max(50, max_words // len(chunks))
    condensed = []
    running_total = 0

    for chunk in chunks:
        words = chunk["text"].split()
        if len(words) > words_per_chunk:
            truncated_text = " ".join(words[:words_per_chunk]) + "…"
        else:
            truncated_text = chunk["text"]
        condensed_chunk = dict(chunk)
        condensed_chunk["text"] = truncated_text
        condensed_chunk["condensed"] = True
        condensed.append(condensed_chunk)
        running_total += len(truncated_text.split())

    logger.info(
        f"[tool:summarize_context] condensed {total_words} → {running_total} words"
    )
    return {"chunks": condensed, "total_words": running_total}


# ══════════════════════════════════════════════════════════════════════════════
# Tool 4 — generate_answer
# ══════════════════════════════════════════════════════════════════════════════

def generate_answer(
    question: str,
    chunks_json: str,
    history_json: str = "[]",
) -> dict:
    """
    Generate a final answer using Gemini with the provided context chunks.

    Call this as the last step after retrieve_documents and rerank_results
    (and optionally summarize_context). This performs a non-streaming LLM
    call and returns the complete answer text plus structured source references.

    Args:
        question:     The original user question.
        chunks_json:  JSON string of final reranked (and optionally condensed) chunks.
        history_json: JSON string of conversation history as [{role, content}] list.
                      Pass "[]" if no history.

    Returns:
        A dict with:
          - answer:  the full answer text string
          - sources: list of {document_id, filename, chunk_text, score}
          - error:   set only if generation failed
    """
    import json as _json
    import google.generativeai as genai
    from app.services.retriever import RetrievedChunk

    logger.info(f"[tool:generate_answer] question={question!r}")

    try:
        chunks_raw   = _json.loads(chunks_json)
        history_raw  = _json.loads(history_json)
    except Exception as e:
        return {"error": f"JSON parse error: {e}", "answer": "", "sources": []}

    # Convert raw dicts back to RetrievedChunk dataclasses for build_prompt
    chunks = [
        RetrievedChunk(
            doc_id       = c.get("doc_id", ""),
            filename     = c.get("filename", "unknown"),
            chunk_index  = c.get("chunk_index", 0),
            text         = c.get("text", ""),
            vector_score = c.get("score", 0.0),
            rerank_score = c.get("rerank_score", c.get("score", 0.0)),
        )
        for c in chunks_raw
    ]

    history = [(h["role"], h["content"]) for h in history_raw]

    # Build the prompt
    system_prompt, user_message = build_prompt(
        question = question,
        chunks   = chunks,
        history  = history,
    )

    # Call Gemini (non-streaming for tool use)
    try:
        if not settings.GOOGLE_API_KEY:
            raise RuntimeError("GOOGLE_API_KEY not set.")

        genai.configure(api_key=settings.GOOGLE_API_KEY)
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config={"temperature": 0.2, "max_output_tokens": 1024},
        )
        full_prompt = f"{system_prompt}\n\n{user_message}"
        response = model.generate_content(full_prompt)
        answer = response.text

    except Exception as exc:
        logger.exception(f"[tool:generate_answer] LLM error: {exc}")
        return {"error": str(exc), "answer": "", "sources": []}

    sources = [
        {
            "document_id": c.doc_id,
            "filename":    c.filename,
            "chunk_text":  c.text,
            "score":       round(c.rerank_score, 4),
        }
        for c in chunks
    ]

    logger.info(f"[tool:generate_answer] answer length={len(answer)} chars")
    return {"answer": answer, "sources": sources}
