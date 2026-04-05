from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ── Document schemas ──────────────────────────────────────────────────────────

class DocumentOut(BaseModel):
    id: str
    filename: str
    file_type: str
    file_size: int
    chunk_count: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentListOut(BaseModel):
    documents: List[DocumentOut]
    total: int


# ── Chat schemas ──────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str
    session_id: str                  # client generates this UUID per conversation
    document_ids: Optional[List[str]] = None   # None = search all docs


class SourceChunk(BaseModel):
    document_id: str
    filename: str
    chunk_text: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    sources: List[SourceChunk]
