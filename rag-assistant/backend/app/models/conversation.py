from sqlalchemy import Column, String, Text, DateTime, JSON
from sqlalchemy.sql import func
from app.core.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True)           # UUID
    session_id = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False)           # user | assistant
    content = Column(Text, nullable=False)
    sources = Column(JSON, nullable=True)           # chunk sources used in this response
    created_at = Column(DateTime, server_default=func.now())
