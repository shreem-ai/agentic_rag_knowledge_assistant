import re
from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime

_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)


# Document schemas

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


# Chat schemas

class ChatRequest(BaseModel):
    question: str
    session_id: str
    document_ids: Optional[List[str]] = None

    @field_validator('session_id')
    @classmethod
    def session_id_must_be_uuid(cls, v: str) -> str:
        if not _UUID_RE.match(v):
            raise ValueError("session_id must be a valid UUID")
        return v


class SourceChunk(BaseModel):
    document_id: str
    filename: str
    chunk_index: int = 0
    chunk_text: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    sources: List[SourceChunk]
