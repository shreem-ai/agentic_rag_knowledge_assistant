"""
RAG ingestion pipeline orchestrator.

Called by the documents API after a file is saved to disk.
Runs the full pipeline:
  1. Extract text from the file
  2. Chunk the text into overlapping windows
  3. Embed all chunks with sentence-transformers
  4. Store embeddings + metadata in the FAISS index
"""

from __future__ import annotations
import asyncio
import logging
from pathlib import Path

from app.services.extractor   import extract_text
from app.services.chunker     import chunk_text
from app.services.embedder    import embed_texts
from app.services import vector_store

logger = logging.getLogger(__name__)


async def ingest_document(
    doc_id:    str,
    filename:  str,
    file_path: Path,
    file_type: str,
) -> int:
    """
    Full ingestion pipeline for one document.
    Returns number of chunks indexed.
    """
    logger.info(f"Starting ingestion for doc {doc_id} ({file_type})")
    chunk_count = await asyncio.to_thread(
        _ingest_sync, doc_id, filename, file_path, file_type
    )
    logger.info(f"Ingestion complete for doc {doc_id}: {chunk_count} chunks.")
    return chunk_count


def _ingest_sync(doc_id: str, filename: str, file_path: Path, file_type: str) -> int:
    # Step 1: extract
    logger.info(f"[{doc_id}] Extracting text…")
    text = extract_text(file_path, file_type)
    if not text.strip():
        raise RuntimeError("Document appears to be empty or unreadable.")
    logger.info(f"[{doc_id}] Extracted {len(text)} characters.")

    # Step 2: chunk
    logger.info(f"[{doc_id}] Chunking…")
    chunks = chunk_text(text, doc_id)
    if not chunks:
        raise RuntimeError("No chunks produced — document may be too short.")
    logger.info(f"[{doc_id}] Produced {len(chunks)} chunks.")

    # Step 3: embed
    logger.info(f"[{doc_id}] Embedding {len(chunks)} chunks…")
    chunk_texts = [c.text for c in chunks]
    embeddings  = embed_texts(chunk_texts)

    # Step 4: store (now includes filename)
    logger.info(f"[{doc_id}] Adding to vector store…")
    vector_store.add_chunks(
        doc_id     = doc_id,
        filename   = filename,
        chunks     = chunk_texts,
        embeddings = embeddings,
    )

    return len(chunks)
