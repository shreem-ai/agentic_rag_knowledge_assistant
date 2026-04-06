"""
ADK Agent Runner — bridges the agent execution loop to SSE streaming.

Tries the ADK agent first; falls back to the direct Phase 3 RAG pipeline
automatically so the app never breaks due to ADK issues.
"""

from __future__ import annotations
import asyncio
import json
import logging
from typing import AsyncGenerator, List, Optional, Tuple

logger = logging.getLogger(__name__)


async def run_agent_stream(
    question:     str,
    history:      List[Tuple[str, str]],
    doc_map:      dict,
    document_ids: Optional[List[str]],
) -> AsyncGenerator[dict, None]:
    """
    Run the RAG agent and yield SSE event dicts.
    Falls back to direct RAG if ADK fails.
    """
    try:
        async for event in _agent_stream(question, history, doc_map, document_ids):
            yield event
    except Exception as exc:
        logger.warning(f"ADK agent failed ({exc}), falling back to direct RAG.")
        async for event in _fallback_stream(question, history, doc_map, document_ids):
            yield event


# ── ADK agent path ────────────────────────────────────────────────────────────

async def _agent_stream(
    question:     str,
    history:      List[Tuple[str, str]],
    doc_map:      dict,
    document_ids: Optional[List[str]],
) -> AsyncGenerator[dict, None]:
    from app.agent.agent import get_rag_agent

    agent        = get_rag_agent()
    history_json = json.dumps([{"role": r, "content": c} for r, c in history])

    user_msg = question
    if document_ids:
        user_msg += f"\n[Search only in document IDs: {', '.join(document_ids)}]"

    yield {"type": "thinking", "data": "Agent starting RAG pipeline…"}

    result = await asyncio.to_thread(_run_agent_sync, agent, user_msg, history_json)

    for step in result.get("tool_calls", []):
        yield {"type": "thinking", "data": f"Called: {step}"}

    answer  = result.get("answer", "")
    sources = result.get("sources", [])

    if not answer:
        raise RuntimeError("Agent returned empty answer.")

    words = answer.split()
    for i, word in enumerate(words):
        sep = " " if i < len(words) - 1 else ""
        yield {"type": "token", "data": word + sep}
        if i % 5 == 0:
            await asyncio.sleep(0)

    yield {"type": "sources", "data": sources}
    yield {"type": "done"}


def _run_agent_sync(agent, user_msg: str, history_json: str) -> dict:
    try:
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.adk.types import Content, Part
        import uuid

        session_service = InMemorySessionService()
        runner = Runner(
            agent           = agent,
            app_name        = "rag_assistant",
            session_service = session_service,
        )

        session_id = str(uuid.uuid4())
        session_service.create_session(
            app_name   = "rag_assistant",
            user_id    = "user",
            session_id = session_id,
        )

        user_content  = Content(role="user", parts=[Part(text=user_msg)])
        tool_calls    = []
        final_text    = ""
        last_sources  = []

        for event in runner.run(
            user_id    = "user",
            session_id = session_id,
            new_message= user_content,
        ):
            if hasattr(event, "tool_call") and event.tool_call:
                tool_calls.append(event.tool_call.name)
                if event.tool_call.name == "generate_answer":
                    try:
                        import json as _j
                        rs = getattr(event.tool_call, "result", "{}")
                        r  = _j.loads(rs) if isinstance(rs, str) else rs
                        last_sources = r.get("sources", [])
                        if r.get("answer"):
                            final_text = r["answer"]
                    except Exception:
                        pass

            if hasattr(event, "content") and event.content:
                for part in (event.content.parts or []):
                    if hasattr(part, "text") and part.text:
                        final_text = part.text

        return {"answer": final_text, "sources": last_sources, "tool_calls": tool_calls}

    except Exception as exc:
        logger.exception(f"ADK runner error: {exc}")
        raise


# ── Direct RAG fallback ───────────────────────────────────────────────────────

async def _fallback_stream(
    question:     str,
    history:      List[Tuple[str, str]],
    doc_map:      dict,
    document_ids: Optional[List[str]],
) -> AsyncGenerator[dict, None]:
    from app.services.retriever     import retrieve_and_rerank
    from app.services.prompt_builder import build_prompt
    from app.services.llm            import stream_answer

    yield {"type": "thinking", "data": "Retrieving relevant chunks…"}

    chunks = await retrieve_and_rerank(
        query              = question,
        doc_id_to_filename = doc_map,
        document_ids       = document_ids,
    )

    yield {"type": "thinking", "data": f"Reranked to {len(chunks)} chunks. Generating answer…"}

    system_prompt, user_message = build_prompt(
        question = question,
        chunks   = chunks,
        history  = history,
    )

    async for event in stream_answer(system_prompt, user_message, chunks):
        yield event
