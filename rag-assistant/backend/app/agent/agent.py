"""
Google ADK Agent.

Creates a LlmAgent (Gemini 2.5 Flash Lite) that has access to the four RAG tools.
The agent receives the user question and decides which tools to call
and in what order to produce a grounded answer.

Typical tool call sequence for a new question:
  retrieve_documents → rerank_results → prepare_answer_context

For a long document or complex question:
  retrieve_documents → rerank_results → summarize_context → prepare_answer_context
"""

from __future__ import annotations
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_rag_agent():
    """Build and return the singleton RAG agent. Cached per process."""
    try:
        from google.adk.agents import LlmAgent
        from google.adk.tools import FunctionTool
    except ImportError as e:
        raise ImportError(
            f"google-adk is not installed or incomplete: {e}\n"
            "Run: pip install google-adk"
        ) from e

    from app.core.config import settings
    from app.agent.tools import (
        retrieve_documents,
        rerank_results,
        summarize_context,
        prepare_answer_context,
    )

    if not settings.GOOGLE_API_KEY:
        raise RuntimeError(
            "GOOGLE_API_KEY is not set. Add it to your .env file."
        )

    import os
    os.environ["GOOGLE_API_KEY"] = settings.GOOGLE_API_KEY

    from app.services.model_picker import resolve_gemini_model
    model_name = resolve_gemini_model()

    tools = [
        FunctionTool(retrieve_documents),
        FunctionTool(rerank_results),
        FunctionTool(summarize_context),
        FunctionTool(prepare_answer_context),
    ]

    agent = LlmAgent(
        name="rag_assistant",
        model=model_name,
        description="A RAG-powered document Q&A assistant.",
        instruction=_AGENT_INSTRUCTION,
        tools=tools,
    )
    logger.info("RAG ADK agent initialised with %s and 4 tools.", model_name)
    return agent


_AGENT_INSTRUCTION = """
You are a precise document Q&A assistant. Use these tools in order:

1. retrieve_documents(query) — find relevant chunks from the vector store
2. rerank_results(query, chunks_json) — rerank by relevance using a cross-encoder
3. prepare_answer_context(question, chunks_json, history_json) — builds a formatted context block and returns sources

After calling prepare_answer_context, write the final answer yourself using the "context" field it returns.
Be concise. Cite [Chunk N] for each claim. Do not add information beyond what the context states.
If prepare_answer_context returns an error field, report it to the user.
Never answer from your own knowledge — only from the retrieved context.
"""