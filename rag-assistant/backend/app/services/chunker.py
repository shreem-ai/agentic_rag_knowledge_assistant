"""
Text chunking: splits extracted text into overlapping windows.

Strategy:
  - Split on sentence boundaries (period/newline) to avoid cutting mid-sentence.
  - Accumulate sentences until we reach CHUNK_SIZE words.
  - Keep a sliding overlap of CHUNK_OVERLAP words from the previous chunk
    so context isn't lost at boundaries.

Each chunk is returned as a dict with:
  - text:        the chunk string
  - chunk_index: position in the document (0-based)
  - word_count:  number of words
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import List

from app.core.config import settings


@dataclass
class Chunk:
    text: str
    chunk_index: int
    word_count: int
    doc_id: str       # filled in by caller


def chunk_text(text: str, doc_id: str) -> List[Chunk]:
    """
    Split `text` into overlapping chunks and return a list of Chunk objects.

    Args:
        text:   Full extracted text of the document.
        doc_id: Document UUID (stored on each chunk for later retrieval).

    Returns:
        List of Chunk objects, ordered by position in the document.
    """
    chunk_size    = settings.CHUNK_SIZE     # target words per chunk
    chunk_overlap = settings.CHUNK_OVERLAP  # words carried over from prev chunk

    # 1. Split into sentences
    # Split on: sentence-ending punctuation, paragraph breaks, or long newlines
    sentence_pattern = re.compile(
        r"(?<=[.!?])\s+|(?<=\n)\s*\n+"
    )
    raw_sentences = sentence_pattern.split(text)
    # Filter blank/tiny fragments
    sentences = [s.strip() for s in raw_sentences if len(s.strip()) > 10]

    if not sentences:
        return []

    # 2. Accumulate sentences into chunks
    chunks: List[Chunk] = []
    current_words: List[str] = []
    chunk_index = 0

    for sentence in sentences:
        sentence_words = sentence.split()

        # If a single sentence is longer than chunk_size, split it hard
        if len(sentence_words) > chunk_size:
            # Flush current buffer first
            if current_words:
                chunks.append(_make_chunk(current_words, chunk_index, doc_id))
                chunk_index += 1
                # Keep overlap tail
                current_words = current_words[-chunk_overlap:] if chunk_overlap else []

            # Split the long sentence into sub-chunks
            for i in range(0, len(sentence_words), chunk_size - chunk_overlap):
                sub = sentence_words[i : i + chunk_size]
                if len(sub) < 20:          # too small, fold into next chunk
                    current_words.extend(sub)
                else:
                    chunks.append(_make_chunk(sub, chunk_index, doc_id))
                    chunk_index += 1
            continue

        current_words.extend(sentence_words)

        if len(current_words) >= chunk_size:
            chunks.append(_make_chunk(current_words, chunk_index, doc_id))
            chunk_index += 1
            # Slide the overlap window forward
            current_words = current_words[-chunk_overlap:] if chunk_overlap else []

    # Flush remaining words
    if len(current_words) >= 20:   # ignore tiny trailing fragments
        chunks.append(_make_chunk(current_words, chunk_index, doc_id))

    return chunks


def _make_chunk(words: List[str], index: int, doc_id: str) -> Chunk:
    return Chunk(
        text=" ".join(words),
        chunk_index=index,
        word_count=len(words),
        doc_id=doc_id,
    )
