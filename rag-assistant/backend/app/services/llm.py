"""
Gemini LLM streaming service.

Uses google-generativeai (not ADK) for direct streaming token generation.
The ADK agent layer (Phase 4) wraps this with tool orchestration.

Streaming approach:
  - Gemini's generate_content() with stream=True yields chunks
  - Each chunk.text is a partial response (one or more tokens)
  - We yield each partial text as an SSE "token" event
  - After the stream is exhausted we yield the sources event + done

Model: gemini-1.5-flash (fast, cheap, good for RAG Q&A)
Fallback: if GOOGLE_API_KEY is missing, yields a clear error message.
"""

from __future__ import annotations
import logging
from typing import AsyncGenerator, List

from app.core.config import settings
from app.services.retriever import RetrievedChunk

logger = logging.getLogger(__name__)

# Singleton Gemini client — initialised on first call
_gemini_model = None


def _get_model():
    global _gemini_model
    if _gemini_model is None:
        if not settings.GOOGLE_API_KEY:
            raise RuntimeError(
                "GOOGLE_API_KEY is not set. "
                "Add it to your .env file to enable LLM responses."
            )
        import google.generativeai as genai
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        _gemini_model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config={
                "temperature": 0.2,      # low temp for factual Q&A
                "max_output_tokens": 1024,
            },
        )
        logger.info("Gemini model initialised.")
    return _gemini_model


async def stream_answer(
    system_prompt: str,
    user_message:  str,
    chunks:        List[RetrievedChunk],
) -> AsyncGenerator[dict, None]:
    """
    Stream answer tokens from Gemini, then yield sources + done.

    Yields dicts (to be JSON-serialised by the caller):
      {"type": "token",   "data": "partial text"}
      {"type": "sources", "data": [...source dicts...]}
      {"type": "done"}
      {"type": "error",   "data": "message"}   # only on failure
    """
    import asyncio

    # ── No documents indexed? Short-circuit with a helpful message ────────────
    if not chunks:
        no_docs_msg = (
            "I couldn't find any relevant content in your uploaded documents "
            "to answer that question. Please make sure you've uploaded documents "
            "and that they've finished processing (status: ready)."
        )
        for word in no_docs_msg.split():
            yield {"type": "token", "data": word + " "}
        yield {"type": "sources", "data": []}
        yield {"type": "done"}
        return

    # ── Call Gemini with streaming ────────────────────────────────────────────
    try:
        model = _get_model()

        # Combine system + user into one message (Flash doesn't take system role)
        full_prompt = f"{system_prompt}\n\n{user_message}"

        # Run the blocking Gemini call in a thread pool
        response_iter = await asyncio.to_thread(
            lambda: model.generate_content(full_prompt, stream=True)
        )

        # Iterate the streaming response
        for chunk in response_iter:
            text = getattr(chunk, "text", None)
            if text:
                yield {"type": "token", "data": text}

    except Exception as exc:
        logger.exception(f"Gemini streaming error: {exc}")
        yield {"type": "error", "data": f"LLM error: {str(exc)}"}
        yield {"type": "done"}
        return

    # ── Emit sources ──────────────────────────────────────────────────────────
    sources = [
        {
            "document_id": c.doc_id,
            "filename":    c.filename,
            "chunk_text":  c.text,
            "score":       round(c.rerank_score, 4),
        }
        for c in chunks
    ]
    yield {"type": "sources", "data": sources}
    yield {"type": "done"}
