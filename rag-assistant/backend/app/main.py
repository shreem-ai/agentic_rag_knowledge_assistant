from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import documents, chat
from app.core.database import init_db

app = FastAPI(
    title="Agentic RAG Assistant",
    description="RAG-powered document Q&A with Google ADK agent",
    version="1.0.0",
)

# Allow Angular frontend to call the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://frontend:80"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(documents.router, prefix="/documents", tags=["documents"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])


@app.on_event("startup")
async def startup():
    """Initialize DB tables on startup."""
    await init_db()


@app.get("/health")
async def health():
    return {"status": "ok"}
