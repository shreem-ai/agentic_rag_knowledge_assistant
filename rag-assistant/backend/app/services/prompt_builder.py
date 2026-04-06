"""
Prompt builder for the RAG answer generation step.

Builds the system + user prompt that is sent to Gemini.
The prompt is structured to:
  1. Instruct the model to answer ONLY from provided context
  2. Include numbered source chunks so the model can cite them
  3. Inject conversation history for follow-up question support
  4. Ask for a clear, factual answer with source references
"""

from __future__ import annotations
from typing import List, Tuple

from app.services.retriever import RetrievedChunk


SYSTEM_PROMPT = """You are a precise document Q&A assistant.
Answer the user's question using ONLY the context chunks provided below.
Rules:
- If the answer is not in the provided context, say "I could not find information about that in the uploaded documents."
- Always cite which chunk(s) you used by referencing [Chunk N] in your answer.
- Be concise and factual. Do not add information beyond what the context states.
- If the question is a follow-up, use the conversation history to understand what "it", "that", or "they" refer to.
"""


def build_prompt(
    question:        str,
    chunks:          List[RetrievedChunk],
    history:         List[Tuple[str, str]],   # (role, content) pairs
) -> Tuple[str, str]:
    """
    Build the (system_prompt, user_message) pair for Gemini.

    Returns:
        (system_prompt, user_message)
    """
    # ── Format context chunks ────────────────────────────────────────────────
    context_lines = []
    for i, chunk in enumerate(chunks, start=1):
        context_lines.append(
            f"[Chunk {i}] (from: {chunk.filename})\n{chunk.text}"
        )
    context_block = "\n\n---\n\n".join(context_lines)

    # ── Format conversation history ──────────────────────────────────────────
    history_block = ""
    if history:
        history_lines = []
        for role, content in history:
            label = "User" if role == "user" else "Assistant"
            truncated = content[:600] + "…" if len(content) > 600 else content
            history_lines.append(f"{label}: {truncated}")
        history_block = (
            "--- Previous conversation ---\n"
            + "\n".join(history_lines)
            + "\n--- End of previous conversation ---\n\n"
        )

    # ── Assemble user message ────────────────────────────────────────────────
    user_message = (
        f"{history_block}"
        f"Context from uploaded documents:\n\n"
        f"{context_block}\n\n"
        f"Question: {question}"
    )

    return SYSTEM_PROMPT, user_message
