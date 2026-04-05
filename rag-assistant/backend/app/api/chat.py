"""
Chat API
POST /chat  – ask a question, returns SSE stream of tokens
"""

import json
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.schemas import ChatRequest
from app.models.conversation import Conversation

router = APIRouter()


async def _token_stream(question: str, session_id: str, db: AsyncSession):
    """
    Placeholder stream generator.
    Phase 3 will replace this with the real RAG + ADK agent call.
    """
    # Save user message to conversation history
    user_msg = Conversation(
        id=str(uuid.uuid4()),
        session_id=session_id,
        role="user",
        content=question,
    )
    db.add(user_msg)
    await db.commit()

    # ── Placeholder response (replace in Phase 3) ──────────────────────────
    placeholder = (
        f"[Phase 1 stub] You asked: '{question}'. "
        "Real RAG + agent responses will stream here in Phase 3."
    )

    full_answer = ""
    for word in placeholder.split():
        token_payload = json.dumps({"type": "token", "data": word + " "})
        yield f"data: {token_payload}\n\n"
        full_answer += word + " "

    # Send sources (empty for now)
    sources_payload = json.dumps({"type": "sources", "data": []})
    yield f"data: {sources_payload}\n\n"

    # Send done signal
    yield f"data: {json.dumps({'type': 'done'})}\n\n"

    # Save assistant response to conversation history
    assistant_msg = Conversation(
        id=str(uuid.uuid4()),
        session_id=session_id,
        role="assistant",
        content=full_answer.strip(),
        sources=[],
    )
    db.add(assistant_msg)
    await db.commit()


@router.post("")
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    return StreamingResponse(
        _token_stream(request.question, request.session_id, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",     # prevents nginx from buffering SSE
        },
    )


@router.get("/history/{session_id}")
async def get_history(session_id: str, db: AsyncSession = Depends(get_db)):
    """Return full conversation history for a session."""
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
                "role": m.role,
                "content": m.content,
                "sources": m.sources or [],
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
    }
