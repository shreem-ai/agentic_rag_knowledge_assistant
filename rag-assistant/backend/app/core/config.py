from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    GOOGLE_API_KEY: str = ""
    ENVIRONMENT: str = "development"

    # Paths (relative to backend root)
    UPLOAD_DIR: Path = Path("data/uploads")
    VECTOR_STORE_DIR: Path = Path("data/vector_store")
    DB_PATH: str = "data/rag_assistant.db"

    # RAG settings
    CHUNK_SIZE: int = 500          # tokens per chunk
    CHUNK_OVERLAP: int = 50        # overlap between chunks
    TOP_K_RETRIEVE: int = 10       # how many chunks to retrieve
    TOP_K_RERANK: int = 4          # how many chunks to keep after reranking

    # Embedding model (runs locally, no API key needed)
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Reranker model
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    class Config:
        env_file = ".env"


settings = Settings()
