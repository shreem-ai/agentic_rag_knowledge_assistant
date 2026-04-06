"""
Conversation memory service.

Loads the last N messages for a session from SQLite and formats
them into a string that can be injected into the LLM prompt.

Design decisions:
  - We keep the last MEMORY_WINDOW messages (default 10 = 5 turns).
  - Older messages are silently dropped to stay within token budget.
  - The formatted history is plain text, not JSON, so it's readable
    by both Gemini and the ADK agent's system prompt.
"""

from __future__ import annotations
from typing import List, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation

MEMORY_WINDOW = 10   # number of messages to keep (user + assistant combined)


async def load_history(
    session_id: str,
    db: AsyncSession,
) -> List[Tuple[str, str]]:
    """
    Load the last MEMORY_WINDOW messages for a session.

    Returns:
        List of (role, content) tuples, oldest first.
        e.g. [("user", "What is X?"), ("assistant", "X is ...")]
    """
    result = await db.execute(
        select(Conversation)
        .where(Conversation.session_id == session_id)
        .order_by(Conversation.created_at.desc())
        .limit(MEMORY_WINDOW)
    )
    messages = result.scalars().all()
    # Reverse so oldest is first
    return [(m.role, m.content) for m in reversed(messages)]


def format_history_for_prompt(history: List[Tuple[str, str]]) -> str:
    """
    Convert history tuples to a readable string block for the LLM prompt.

    Example output:
        User: What is FAISS?
        Assistant: FAISS is a library for efficient similarity search...
        User: How does it compare to Chroma?
    """
    if not history:
        return ""

    lines = []
    for role, content in history:
        label = "User" if role == "user" else "Assistant"
        # Truncate very long messages to save tokens
        truncated = content[:800] + "…" if len(content) > 800 else content
        lines.append(f"{label}: {truncated}")

    return "\n".join(lines)


async def save_turn(
    session_id: str,
    question: str,
    answer: str,
    sources: list,
    db: AsyncSession,
) -> None:
    """
    Persist one user + assistant turn to the conversation table.
    """
    import uuid

    user_msg = Conversation(
        id=str(uuid.uuid4()),
        session_id=session_id,
        role="user",
        content=question,
    )
    assistant_msg = Conversation(
        id=str(uuid.uuid4()),
        session_id=session_id,
        role="assistant",
        content=answer,
        sources=sources,
    )
    db.add(user_msg)
    db.add(assistant_msg)
    await db.commit()
