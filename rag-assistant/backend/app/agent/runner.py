"""
ADK Agent Runner — bridges the agent execution loop to SSE streaming.

Tries the ADK agent first; falls back to the direct RAG pipeline
automatically so the app never breaks due to ADK issues.
"""

from __future__ import annotations
import asyncio
import json
import logging
from typing import AsyncGenerator, List, Optional, Tuple

logger = logging.getLogger(__name__)


async def run_agent_stream(
    question: str,
    history: List[Tuple[str, str]],
    doc_map: dict,
    document_ids: Optional[List[str]],
) -> AsyncGenerator[dict, None]:
    """Run the RAG agent and yield SSE event dicts. Falls back to direct RAG if ADK fails."""
    try:
        async for event in _agent_stream(question, history, doc_map, document_ids):
            yield event
    except Exception as exc:
        logger.warning(f"ADK agent failed ({exc!r}), falling back to direct RAG.")
        yield {"type": "thinking", "data": "ADK agent unavailable — switching to direct RAG pipeline."}
        async for event in _fallback_stream(question, history, doc_map, document_ids):
            yield event


async def _agent_stream(
    question: str,
    history: List[Tuple[str, str]],
    doc_map: dict,
    document_ids: Optional[List[str]],
) -> AsyncGenerator[dict, None]:
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai.types import Content, Part
    import uuid

    from app.agent.agent import get_rag_agent
    agent = get_rag_agent()

    user_msg = question
    if document_ids:
        user_msg += f"\n[Search only in document IDs: {', '.join(document_ids)}]"

    # Include only the last 1 turn of history (truncated) to avoid ballooning
    # the prompt — flash-lite stops mid-pipeline above ~5k tokens
    if history:
        last_pairs = history[-1:]  # last (user, assistant) pair only
        compact = []
        for role, content in last_pairs:
            short = content[:200] + "…" if len(content) > 200 else content
            compact.append(f"{role}: {short}")
        user_msg += "\n[Prior turn: " + " | ".join(compact) + "]"

    history_json = json.dumps([{"role": r, "content": c} for r, c in history[-2:]])

    yield {"type": "thinking", "data": "Agent starting RAG pipeline…"}

    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
        app_name="rag_assistant",
        session_service=session_service,
    )

    session_id = str(uuid.uuid4())
    session_service.create_session(
        app_name="rag_assistant",
        user_id="user",
        session_id=session_id,
    )

    user_content = Content(role="user", parts=[Part(text=user_msg)])

    tool_calls = []
    final_text = ""
    last_sources = []

    async for event in runner.run_async(
        user_id="user",
        session_id=session_id,
        new_message=user_content,
    ):
        for fc in event.get_function_calls():
            tool_calls.append(fc.name)
            yield {"type": "thinking", "data": f"Called: {fc.name}"}

        # extract sources from prepare_answer_context response
        for fr in event.get_function_responses():
            if fr.name == "prepare_answer_context":
                try:
                    resp = fr.response or {}
                    if isinstance(resp, str):
                        resp = json.loads(resp)
                    last_sources = resp.get("sources", [])
                except Exception:
                    pass

        if event.is_final_response() and event.content:
            for part in (event.content.parts or []):
                if hasattr(part, "text") and part.text:
                    final_text += part.text

    if not final_text:
        raise RuntimeError("Agent returned empty answer.")

    words = final_text.split()
    for i, word in enumerate(words):
        sep = " " if i < len(words) - 1 else ""
        yield {"type": "token", "data": word + sep}
        if i % 5 == 0:
            await asyncio.sleep(0)

    yield {"type": "sources", "data": last_sources}
    yield {"type": "done"}


async def _fallback_stream(
    question: str,
    history: List[Tuple[str, str]],
    doc_map: dict,
    document_ids: Optional[List[str]],
) -> AsyncGenerator[dict, None]:
    from app.services.retriever import retrieve_and_rerank
    from app.services.prompt_builder import build_prompt
    from app.services.llm import stream_answer

    yield {"type": "thinking", "data": "Retrieving relevant chunks…"}

    chunks = await retrieve_and_rerank(
        query=question,
        doc_id_to_filename=doc_map,
        document_ids=document_ids,
    )

    yield {"type": "thinking", "data": f"Reranked to {len(chunks)} chunks. Generating answer…"}

    system_prompt, user_message = build_prompt(
        question=question,
        chunks=chunks,
        history=history,
    )

    async for event in stream_answer(system_prompt, user_message, chunks):
        yield event
