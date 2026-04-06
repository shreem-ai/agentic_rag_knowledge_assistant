"""
Google ADK Agent — Phase 4.

Creates a LlmAgent that has access to the four RAG tools.
The agent receives the user question and decides which tools to call
and in what order to produce a grounded answer.

Typical tool call sequence for a new question:
  retrieve_documents → rerank_results → generate_answer

For a long document or complex question:
  retrieve_documents → rerank_results → summarize_context → generate_answer

For a follow-up question that references the previous answer:
  (agent uses history from session state, may skip retrieve if context sufficient)
  generate_answer (directly, with cached chunks)

ADK version compatibility:
  This targets google-adk>=0.1.0. The ADK API is still evolving;
  if you get import errors, check: pip show google-adk
"""

from __future__ import annotations
import logging
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_rag_agent():
    """
    Build and return the singleton RAG agent.
    Cached so the agent (and its underlying Gemini client) is only
    initialised once per process.
    """
    try:
        from google.adk.agents import LlmAgent
        from google.adk.tools import FunctionTool
        import google.generativeai as genai
    except ImportError as e:
        raise ImportError(
            f"google-adk is not installed or incomplete: {e}\n"
            "Run: pip install google-adk google-generativeai"
        ) from e

    from app.core.config import settings
    from app.agent.tools import (
        retrieve_documents,
        rerank_results,
        summarize_context,
        generate_answer,
    )

    if not settings.GOOGLE_API_KEY:
        raise RuntimeError(
            "GOOGLE_API_KEY is not set. Add it to your .env file."
        )

    genai.configure(api_key=settings.GOOGLE_API_KEY)

    # Wrap each plain Python function as an ADK FunctionTool.
    # ADK reads the function's docstring and type annotations to
    # auto-generate the tool schema that Gemini uses for function calling.
    tools = [
        FunctionTool(retrieve_documents),
        FunctionTool(rerank_results),
        FunctionTool(summarize_context),
        FunctionTool(generate_answer),
    ]

    agent = LlmAgent(
        name        = "rag_assistant",
        model       = "gemini-1.5-flash",
        description = "A RAG-powered document Q&A assistant.",
        instruction = _AGENT_INSTRUCTION,
        tools       = tools,
    )

    logger.info("RAG ADK agent initialised with 4 tools.")
    return agent


# ── Agent system instruction ──────────────────────────────────────────────────

_AGENT_INSTRUCTION = """
You are a precise, helpful document Q&A assistant.
You have access to four tools that implement a RAG (Retrieval-Augmented Generation) pipeline.

## Your workflow for answering questions:

### Standard question:
1. Call retrieve_documents(query=<question>) to find relevant chunks.
2. Call rerank_results(query=<question>, chunks_json=<json of retrieved chunks>) to improve precision.
3. Call generate_answer(question=<question>, chunks_json=<reranked chunks json>, history_json=<session history json>) to produce the final answer.

### Long or complex documents (chunks total > 600 words):
1. retrieve_documents
2. rerank_results
3. Call summarize_context(chunks_json=<reranked chunks json>) to condense context.
4. generate_answer with the condensed chunks.

### Follow-up question that depends on previous answer:
- Always include the conversation history in the history_json argument to generate_answer.
- This lets the model resolve pronouns like "it", "that", "they".

## Rules:
- Always call retrieve_documents first — never answer from your own knowledge.
- Always call rerank_results after retrieve_documents.
- Only call summarize_context if the total word count of reranked chunks exceeds ~600 words.
- Pass the full chunks JSON string between tools — do not modify it.
- Your final response to the user should be the "answer" field from generate_answer.
- If generate_answer returns an error, tell the user clearly what went wrong.
- Never make up sources. Only cite chunks that were actually returned by the tools.
"""
