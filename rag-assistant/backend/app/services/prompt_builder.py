"""
Prompt builder for the RAG answer generation step.
"""

from __future__ import annotations
from typing import List, Tuple

from app.services.retriever import RetrievedChunk

# Keywords that indicate the user wants a synthesis/overview rather than a specific fact
_SYNTHESIS_KEYWORDS = {
    "summary", "summarize", "summarise", "overview", "about", "describe",
    "what is this", "what does this", "what is the document", "explain",
    "tell me about", "key points", "main points", "highlights", "outline",
    "what topics", "what does it cover", "introduction",
}

SYSTEM_PROMPT_QA = """You are a precise document Q&A assistant.
Answer the user's question using ONLY the context chunks provided below.
Rules:
- Always cite which chunk(s) you used by referencing [Chunk N] in your answer.
- Be concise and factual.
- If the question is a follow-up, use the conversation history to understand pronouns like "it", "that", or "they".
- Only say "I could not find information about that" if the chunks are genuinely unrelated to the question.
"""

SYSTEM_PROMPT_SUMMARY = """You are a helpful document assistant.
The user wants an overview or summary. Use ALL the context chunks below to write a comprehensive answer.
Rules:
- Synthesize information across all chunks — do not quote chunks verbatim.
- Cite [Chunk N] when referring to specific points.
- Structure your answer clearly (use bullet points or short paragraphs).
- Base your answer entirely on the provided chunks.
"""


def _is_synthesis_query(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in _SYNTHESIS_KEYWORDS)


def build_prompt(
    question: str,
    chunks:   List[RetrievedChunk],
    history:  List[Tuple[str, str]],
) -> Tuple[str, str]:
    """
    Build the (system_prompt, user_message) pair for Gemini.
    Uses a synthesis-friendly prompt for summary/overview questions.
    """
    # Pick the right system prompt
    system_prompt = (
        SYSTEM_PROMPT_SUMMARY if _is_synthesis_query(question) else SYSTEM_PROMPT_QA
    )

    # Format context chunks
    context_lines = []
    for i, chunk in enumerate(chunks, start=1):
        context_lines.append(f"[Chunk {i}] (from: {chunk.filename})\n{chunk.text}")
    context_block = "\n\n---\n\n".join(context_lines)

    # Format conversation history (last 4 turns, truncated)
    history_block = ""
    if history:
        lines = []
        for role, content in history[-4:]:
            label = "User" if role == "user" else "Assistant"
            text  = content[:400] + "…" if len(content) > 400 else content
            lines.append(f"{label}: {text}")
        history_block = (
            "--- Previous conversation ---\n"
            + "\n".join(lines)
            + "\n--- End of previous conversation ---\n\n"
        )

    user_message = (
        f"{history_block}"
        f"Context from uploaded documents:\n\n"
        f"{context_block}\n\n"
        f"Question: {question}"
    )

    return system_prompt, user_message