"""
Documents API
POST /documents/upload  – upload + process a document
GET  /documents         – list all uploaded documents
"""

import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.config import settings
from app.models.document import Document
from app.models.schemas import DocumentOut, DocumentListOut

router = APIRouter()

ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "text/plain": "txt",
    "text/markdown": "md",
}


@router.post("/upload", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    # Validate file type
    content_type = file.content_type or ""
    if content_type not in ALLOWED_TYPES and not file.filename.endswith((".pdf", ".txt", ".md")):
        raise HTTPException(status_code=400, detail="Only PDF, TXT, and Markdown files are supported.")

    # Determine extension
    ext = ALLOWED_TYPES.get(content_type) or file.filename.rsplit(".", 1)[-1].lower()

    # Save file to disk
    doc_id = str(uuid.uuid4())
    save_path: Path = settings.UPLOAD_DIR / f"{doc_id}.{ext}"
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    contents = await file.read()
    save_path.write_bytes(contents)

    # Persist metadata to DB
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

    # TODO Phase 3: kick off background task to extract text, chunk, embed
    # For now mark as ready with 0 chunks so we can test the endpoint
    doc.status = "ready"
    await db.commit()
    await db.refresh(doc)

    return doc


@router.get("", response_model=DocumentListOut)
async def list_documents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).order_by(Document.created_at.desc()))
    docs = result.scalars().all()
    return DocumentListOut(documents=list(docs), total=len(docs))


@router.get("/{doc_id}", response_model=DocumentOut)
async def get_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc
