"""
POST /chat              — ask a question, streams SSE tokens via ADK agent
GET  /chat/history/{id} — return conversation history for a session
"""

from __future__ import annotations
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas import ChatRequest
from app.models.document import Document
from app.models.conversation import Conversation
from app.services.memory import load_history, save_turn
from app.agent.runner import run_agent_stream

logger = logging.getLogger(__name__)
router = APIRouter()


# POST /chat

@router.post("")
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    return StreamingResponse(
        _agent_sse_stream(request, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _agent_sse_stream(
    request: ChatRequest,
    db:      AsyncSession,
) -> AsyncGenerator[str, None]:
    """
    Orchestrate the agent run and forward its events as SSE lines.

    Flow:
      1. Load conversation history from SQLite
      2. Build doc_id → filename map for source labels
      3. Call run_agent_stream() — tries ADK agent, falls back to direct RAG
      4. Forward every event as an SSE line
      5. Save completed turn to memory
    """

    question   = request.question.strip()
    session_id = request.session_id

    history = await load_history(session_id, db)

    if request.document_ids:
        stmt = select(Document).where(
            Document.id.in_(request.document_ids),
            Document.status == "ready",
        )
    else:
        stmt = select(Document).where(Document.status == "ready")

    result  = await db.execute(stmt)
    docs    = result.scalars().all()
    doc_map = {d.id: d.filename for d in docs}

    if not doc_map:
        msg = (
            "No documents are ready yet. "
            "Please upload a document and wait for it to finish processing."
        )
        for word in msg.split():
            yield _sse({"type": "token", "data": word + " "})
        yield _sse({"type": "sources", "data": []})
        yield _sse({"type": "done"})
        return

    full_answer  = ""
    sources_list = []

    async for event in run_agent_stream(
        question     = question,
        history      = history,
        doc_map      = doc_map,
        document_ids = request.document_ids,
    ):
        if event["type"] == "token":
            full_answer += event["data"]
        elif event["type"] == "sources":
            sources_list = event["data"]

        # Save turn BEFORE yielding done, while DB session is still open
        if event["type"] == "done" and full_answer.strip():
            try:
                await save_turn(
                    session_id = session_id,
                    question   = question,
                    answer     = full_answer.strip(),
                    sources    = sources_list,
                    db         = db,
                )
            except Exception as exc:
                logger.warning(f"Failed to save conversation turn: {exc}")

        yield _sse(event)

# GET /chat/history/{session_id}

@router.get("/history/{session_id}")
async def get_history(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.session_id == session_id)
        .order_by(Conversation.created_at.asc())
    )
    messages = result.scalars().all()
    return {
        "session_id": session_id,
        "messages": [
            {
                "role":       m.role,
                "content":    m.content,
                "sources":    m.sources or [],
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
    }


# Helper

def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"
