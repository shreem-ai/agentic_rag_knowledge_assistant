"""
Documents API
POST /documents/upload  – upload + process a document
GET  /documents         – list all uploaded documents
GET  /documents/{id}    – get single document
DELETE /documents/{id}  – remove document + its vectors
"""

import uuid
import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.config import settings
from app.models.document import Document
from app.models.schemas import DocumentOut, DocumentListOut
from app.services.pipeline import ingest_document
from app.services import vector_store

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_EXTENSIONS = {"pdf", "txt", "md"}


@router.post("/upload", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
):
    # Determine extension
    name_lower = (file.filename or "").lower()
    ext = name_lower.rsplit(".", 1)[-1] if "." in name_lower else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '.{ext}'. Allowed: PDF, TXT, Markdown (.md).",
        )

    # Save raw file
    doc_id    = str(uuid.uuid4())
    save_path = Path(settings.UPLOAD_DIR) / f"{doc_id}.{ext}"
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

    contents = await file.read()
    save_path.write_bytes(contents)

    # Persist DB record
    doc = Document(
        id=doc_id,
        filename=file.filename,
        file_type=ext,
        file_size=len(contents),
        status="processing",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # Kick off background ingestion
    background_tasks.add_task(_run_ingestion, doc_id, file.filename, save_path, ext)

    return doc


async def _run_ingestion(doc_id: str, filename: str, file_path: Path, file_type: str):
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()
        if not doc:
            return

        try:
            chunk_count = await ingest_document(doc_id, filename, file_path, file_type)
            doc.status      = "ready"
            doc.chunk_count = chunk_count
        except Exception as exc:
            logger.exception(f"Ingestion failed for {doc_id}: {exc}")
            doc.status        = "error"
            doc.error_message = str(exc)

        await db.commit()


@router.get("", response_model=DocumentListOut)
async def list_documents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).order_by(Document.created_at.desc()))
    docs   = result.scalars().all()
    return DocumentListOut(documents=list(docs), total=len(docs))


@router.get("/{doc_id}", response_model=DocumentOut)
async def get_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc    = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{doc_id}")
async def delete_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc    = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    removed = await asyncio.to_thread(vector_store.delete_document, doc_id)

    await db.delete(doc)
    await db.commit()

    raw_file = Path(settings.UPLOAD_DIR) / f"{doc_id}.{doc.file_type}"
    if raw_file.exists():
        raw_file.unlink()

    return {"deleted": True, "doc_id": doc_id, "vectors_removed": removed}
