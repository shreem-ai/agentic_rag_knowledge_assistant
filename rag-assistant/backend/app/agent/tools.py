"""
ADK Agent Tools — Phase 4.

Four tools the agent can call to orchestrate the RAG pipeline:

  1. retrieve_documents     — embed query + FAISS vector search
  2. rerank_results         — cross-encoder reranking of candidates
  3. summarize_context      — condense chunks when total context is too long
  4. prepare_answer_context — build prompt context + sources; agent writes the final answer itself

Each tool is a plain Python function. Google ADK inspects the function
signature and docstring to decide when to call it.

Design note:
  ADK tools are synchronous functions that run in a thread pool.
  State (retrieved chunks, reranked results) is passed between tools
  via the AgentContext store, not via global variables.
"""

import logging
import re

from app.core.config import settings
from app.services import vector_store
from app.services.embedder import embed_query, rerank as cross_encoder_rerank

logger = logging.getLogger(__name__)


def _clean(text: str, max_len: int = 500) -> str:
    # strip zero-width spaces, combining keycap chars and emoji so the model
    # doesn't choke when it serializes chunk text into a JSON function argument
    text = re.sub(r'[\u200b\u200c\u200d\u200e\u200f\ufeff\u00ad]', '', text)
    text = re.sub(r'[\u20d0-\u20ff]', '', text)
    text = re.sub(r'[\U0001F300-\U0001FFFF]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:max_len] if len(text) > max_len else text


def retrieve_documents(query: str, document_ids: str = "") -> dict:
    """Search the vector store for chunks relevant to the query.

    Call this first. Pass document_ids as a comma-separated string to restrict
    search to specific documents, or leave empty to search everything.
    Returns a list of chunk dicts with doc_id, chunk_index, text, score, filename.
    """
    logger.info(f"[retrieve_documents] query={query!r}")

    doc_ids = None
    if document_ids and document_ids.strip():
        doc_ids = [d.strip() for d in document_ids.split(",") if d.strip()]

    q_vec = embed_query(query)
    raw = vector_store.search(
        query_embedding=q_vec,
        top_k=settings.TOP_K_RETRIEVE,
        doc_ids=doc_ids,
    )

    chunks = [
        {
            "doc_id": r["doc_id"],
            "chunk_index": r["chunk_index"],
            "text": _clean(r["text"]),
            "score": round(r["score"], 4),
            "filename": r.get("filename", ""),
        }
        for r in raw
    ]

    logger.info(f"[retrieve_documents] found {len(chunks)} chunks")
    return {"chunks": chunks, "total": len(chunks)}


def rerank_results(query: str, chunks_json: str) -> dict:
    """Rerank retrieved chunks using a cross-encoder model.

    Call this after retrieve_documents. The cross-encoder scores each
    (query, chunk) pair together which is more accurate than cosine similarity alone.
    Returns the top TOP_K_RERANK chunks sorted by rerank_score.
    """
    logger.info(f"[rerank_results] query={query!r}")

    try:
        chunks = json.loads(chunks_json)
    except Exception as e:
        return {"error": f"Invalid chunks_json: {e}", "chunks": [], "total": 0}

    if not chunks:
        return {"chunks": [], "total": 0}

    texts = [c["text"] for c in chunks]
    # cross-encoder scores can be negative (raw logits) — that's normal
    scores = cross_encoder_rerank(query, texts)

    for chunk, score in zip(chunks, scores):
        chunk["rerank_score"] = round(float(score), 4)

    ranked = sorted(chunks, key=lambda c: c["rerank_score"], reverse=True)
    top = ranked[:settings.TOP_K_RERANK]

    if top:
        logger.info(f"[rerank_results] top={top[0]['rerank_score']:.3f}, returning {len(top)} chunks")
    return {"chunks": top, "total": len(top)}


def summarize_context(chunks_json: str, max_words: int = 600) -> dict:
    """Trim chunks proportionally when total context exceeds the word budget.

    Call this when reranked chunks are very long. Keeps the beginning of each
    chunk since the most relevant sentence usually appears there after reranking.
    """
    logger.info(f"[summarize_context] max_words={max_words}")

    try:
        chunks = json.loads(chunks_json)
    except Exception as e:
        return {"error": f"Invalid chunks_json: {e}", "chunks": [], "total_words": 0}

    if not chunks:
        return {"chunks": [], "total_words": 0}

    total_words = sum(len(c["text"].split()) for c in chunks)

    if total_words <= max_words:
        return {"chunks": chunks, "total_words": total_words}

    words_per_chunk = max(50, max_words // len(chunks))
    condensed = []
    running_total = 0

    for chunk in chunks:
        words = chunk["text"].split()
        trimmed = " ".join(words[:words_per_chunk]) + "…" if len(words) > words_per_chunk else chunk["text"]
        c = dict(chunk)
        c["text"] = trimmed
        c["condensed"] = True
        condensed.append(c)
        running_total += len(trimmed.split())

    logger.info(f"[summarize_context] {total_words} -> {running_total} words")
    return {"chunks": condensed, "total_words": running_total}


def prepare_answer_context(question: str, chunks_json: str, history_json: str = "[]") -> dict:
    """Build the context block and sources list so the agent can write its final answer.

    This tool doesn't call an LLM. It formats the retrieved chunks into a structured
    context string and returns sources. The agent reads the 'context' field and
    writes the answer itself — this keeps the actual generation inside ADK's loop
    where streaming works correctly.

    Call this last, after retrieve_documents and rerank_results.
    """
    logger.info(f"[prepare_answer_context] question={question!r}")

    try:
        chunks_raw = json.loads(chunks_json)
        history_raw = json.loads(history_json)
    except Exception as e:
        return {"error": f"JSON parse error: {e}", "context": "", "sources": [], "question": question}

    if not chunks_raw:
        return {
            "context": "No relevant chunks found in the documents.",
            "sources": [],
            "question": question,
        }

    context_lines = []
    for i, c in enumerate(chunks_raw, start=1):
        context_lines.append(f"[Chunk {i}] (from: {c.get('filename', 'unknown')})\n{c.get('text', '')}")
    context_block = "\n\n---\n\n".join(context_lines)

    history_block = ""
    if history_raw:
        lines = []
        for h in history_raw[-4:]:
            label = "User" if h["role"] == "user" else "Assistant"
            text = h["content"][:200] + "…" if len(h["content"]) > 200 else h["content"]
            lines.append(f"{label}: {text}")
        history_block = "Prior conversation:\n" + "\n".join(lines) + "\n\n"

    context = (
        f"{history_block}"
        f"Context from documents:\n\n{context_block}\n\n"
        f"Answer ONLY from the context above. Cite [Chunk N] where used. "
        f"If the answer is not in the context, say so clearly."
    )

    sources = [
        {
            "document_id": c.get("doc_id", ""),
            "filename": c.get("filename", "unknown"),
            "chunk_index": c.get("chunk_index", 0),
            "chunk_text": c.get("text", ""),
            "score": round(c.get("rerank_score", c.get("score", 0.0)), 4),
        }
        for c in chunks_raw
    ]

    logger.info(f"[prepare_answer_context] built context from {len(chunks_raw)} chunks")
    return {"context": context, "sources": sources, "question": question}
