from sqlalchemy import Column, String, Integer, DateTime, Text
from sqlalchemy.sql import func
from app.core.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True)          # UUID
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)      # pdf, txt, md
    file_size = Column(Integer, nullable=False)     # bytes
    chunk_count = Column(Integer, default=0)
    status = Column(String, default="processing")   # processing | ready | error
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
