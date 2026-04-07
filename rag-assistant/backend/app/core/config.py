from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    GOOGLE_API_KEY: str = ""
    ENVIRONMENT: str = "development"

    # Paths (relative to backend root)
    UPLOAD_DIR: Path = Path("data/uploads")
    VECTOR_STORE_DIR: Path = Path("data/vector_store")
    DB_PATH: str = "data/rag_assistant.db"

    # Upload limits
    MAX_UPLOAD_BYTES: int = 50 * 1024 * 1024  # 50 MB

    # RAG settings
    CHUNK_SIZE: int = 500          # words per chunk
    CHUNK_OVERLAP: int = 50        # overlap between chunks
    TOP_K_RETRIEVE: int = 10       # how many chunks to retrieve
    TOP_K_RERANK: int = 4          # how many chunks to keep after reranking

    # LLM output limit
    MAX_OUTPUT_TOKENS: int = 1024

    # Embedding model (runs locally, no API key needed)
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Reranker model
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Gemini model — leave blank to auto-pick from GEMINI_MODEL_PREFERENCE
    GEMINI_MODEL: str = ""

    # Preference order for auto-pick (first available wins)
    GEMINI_MODEL_PREFERENCE: list = [
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.0-flash",
        "gemini-flash-lite-latest",
        "gemini-flash-latest",
    ]

    class Config:
        env_file = (".env", "../.env")
        extra = "ignore"


settings = Settings()

# Propagate to os.environ so google.genai (used by ADK) can find the key
import os as _os
if settings.GOOGLE_API_KEY:
    _os.environ.setdefault("GOOGLE_API_KEY", settings.GOOGLE_API_KEY)