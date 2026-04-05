# Agentic RAG Knowledge Assistant

A full-stack application where users upload documents and ask questions about them using a Retrieval-Augmented Generation (RAG) pipeline orchestrated by a Google ADK agent.

## Quick Start

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd rag-assistant

# 2. Add your Google API key
cp .env.example .env
# Edit .env and set GOOGLE_API_KEY=your_key_here

# 3. Run everything with Docker
docker compose up --build
```

- Frontend: http://localhost:4200
- Backend API: http://localhost:8000
- API Docs (Swagger): http://localhost:8000/docs

---

## Project Structure

```
rag-assistant/
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI route handlers
│   │   │   ├── documents.py   # Upload + list endpoints
│   │   │   └── chat.py        # SSE streaming chat endpoint
│   │   ├── core/
│   │   │   ├── config.py      # App settings (pydantic-settings)
│   │   │   └── database.py    # SQLAlchemy async SQLite setup
│   │   ├── models/
│   │   │   ├── document.py    # DB model: uploaded documents
│   │   │   ├── conversation.py # DB model: chat history
│   │   │   └── schemas.py     # Pydantic request/response schemas
│   │   ├── services/      # RAG pipeline (Phase 3)
│   │   │   ├── embedder.py    # Embedding generation
│   │   │   ├── chunker.py     # Text chunking
│   │   │   ├── vector_store.py # FAISS operations
│   │   │   └── reranker.py    # Cross-encoder reranking
│   │   ├── agent/         # Google ADK agent (Phase 4)
│   │   │   ├── tools.py       # ADK tool definitions
│   │   │   └── agent.py       # Agent orchestration
│   │   └── main.py        # FastAPI app entry point
│   ├── data/
│   │   ├── uploads/       # Raw uploaded files
│   │   └── vector_store/  # FAISS index files
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/app/
│   │   ├── pages/
│   │   │   ├── upload/    # Document upload page
│   │   │   └── chat/      # Chat interface page
│   │   ├── services/
│   │   │   ├── document.service.ts  # HTTP calls for documents
│   │   │   └── chat.service.ts      # SSE streaming chat
│   │   ├── models/types.ts          # TypeScript interfaces
│   │   ├── app.component.ts         # Root component + nav
│   │   ├── app.routes.ts            # Route definitions
│   │   └── app.config.ts            # Angular providers
│   ├── nginx.conf         # Serves Angular + proxies /api to backend
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Architecture & Design Decisions

### RAG Pipeline (Phase 3)

```
User question
     │
     ▼
Embed query  ──►  FAISS similarity search (top-10)
                         │
                         ▼
               Cross-encoder reranking (top-4)
                         │
                         ▼
           LLM call with context + chat history
                         │
                         ▼
         Streamed answer + source references
```

**Chunking strategy:** 500-token chunks with 50-token overlap. Overlap prevents losing context at chunk boundaries (e.g., a sentence split across two chunks).

**Embedding model:** `sentence-transformers/all-MiniLM-L6-v2` — fast, runs locally, no API key needed, strong semantic retrieval.

**Vector store:** FAISS (`faiss-cpu`) — simple, runs in-process, no separate service, persists to disk. Good enough for thousands of documents; swap to Qdrant/Chroma if you need distributed scale.

**Reranking:** `cross-encoder/ms-marco-MiniLM-L-6-v2` — a cross-encoder scores each (query, chunk) pair together, which is more accurate than embedding cosine similarity alone. Retrieve 10 candidates, rerank, keep top 4.

### Agent Design (Phase 4)

Uses **Google ADK** to create an agent with four tools:

| Tool | What it does |
|------|-------------|
| `retrieve_documents` | Embeds query, runs FAISS search, returns top-k chunks |
| `rerank_results` | Runs cross-encoder on retrieved chunks, returns top-4 |
| `summarize_context` | Condenses chunks if total context exceeds token budget |
| `generate_answer` | Calls Gemini with context + history, streams the response |

The agent decides which tools to invoke. For a simple factual question it calls retrieve → rerank → generate. For a vague follow-up question it may call summarize_context first. This is more flexible than a hardcoded RAG pipeline.

### Chat Memory

Every message (user + assistant) is stored in SQLite with a `session_id`. On each `/chat` request, the last 10 messages for that session are prepended to the LLM context. This allows follow-up questions like "can you elaborate on that?" to work correctly.

### Streaming

Backend streams tokens via **Server-Sent Events (SSE)** using FastAPI's `StreamingResponse`. The Angular frontend uses the native `fetch()` API with `ReadableStream` to consume the stream (Angular's `HttpClient` buffers SSE, so raw fetch is used instead). nginx is configured with `proxy_buffering off` so Docker deployments don't buffer the stream either.

Each SSE event is a JSON object with a `type` field:
- `{"type": "token", "data": "word "}` — a single token
- `{"type": "sources", "data": [...]}` — source chunks used
- `{"type": "done"}` — stream complete

### Source Traceability

Every assistant response includes `SourceChunk` objects with:
- `document_id` and `filename` — which document
- `chunk_text` — the exact text used as context
- `score` — the reranker confidence score (0–1)

In the UI, source chips appear below each answer. Clicking a chip expands the exact chunk text used.

---

## Development (without Docker)

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
ng serve                       # runs on http://localhost:4200
```

The Angular dev proxy (`src/proxy.conf.json`) forwards `/api/*` to `http://localhost:8000`.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_API_KEY` | Yes | For Gemini LLM via Google ADK |
| `ENVIRONMENT` | No | `development` or `production` |

---

## Build Phases

| Phase | What gets built |
|-------|----------------|
| ✅ Phase 1 | Project structure, Docker setup, DB models, API stubs, Angular scaffold |
| 🔲 Phase 2 | Full document upload with text extraction, chunking, embedding |
| 🔲 Phase 3 | RAG pipeline: vector search + reranking + LLM call |
| 🔲 Phase 4 | Google ADK agent with tools |
| 🔲 Phase 5 | Chat memory wired into LLM context |
