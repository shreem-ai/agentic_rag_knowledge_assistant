import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import documents, chat
from app.core.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Agentic RAG Assistant",
    description="RAG-powered document Q&A with Google ADK agent + SSE streaming",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://localhost:80", "http://frontend"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router, prefix="/documents", tags=["documents"])
app.include_router(chat.router,      prefix="/chat",      tags=["chat"])


@app.on_event("startup")
async def startup():
    await init_db()


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}


@app.get("/", tags=["health"])
async def root():
    return {"message": "RAG Assistant API", "docs": "/docs"}
