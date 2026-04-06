# Agentic RAG Knowledge Assistant

A full-stack application where users upload documents (PDF, TXT, Markdown) and ask questions about them. Uses a Retrieval-Augmented Generation (RAG) pipeline orchestrated by a Google ADK agent, with real-time SSE streaming responses.

---

## Quick Start

```bash
# 1. Clone / unzip the project
cd rag-assistant

# 2. Set your Google API key
cp .env.example .env
# Open .env and set:  GOOGLE_API_KEY=your_key_here

# 3. Build and run (first build takes 5-10 min — downloads ML models)
docker compose up --build

# 4. Open the app
#    Frontend:  http://localhost:4200
#    API docs:  http://localhost:8000/docs
```

> **Note:** The first `docker build` pre-downloads the sentence-transformer (~80 MB) and cross-encoder (~70 MB) models into the image so there is no cold-start delay on first use.

---

## Demo Walkthrough

### Step 1 — Upload a document

1. Open **http://localhost:4200**
2. Go to the **Upload** page
3. Drag and drop a PDF, TXT, or Markdown file onto the drop zone
4. Watch the badge change: **processing → ready** (takes 5–30 seconds depending on file size)
5. The chunk count shows how many pieces the document was split into

### Step 2 — Ask questions

1. Go to the **Chat** page
2. (Optional) Check specific documents in the sidebar to restrict search scope
3. Type a question and press **Enter**
4. Watch tokens stream in real time — you'll see agent thinking steps appear first:
   ```
   ⚙ Agent starting RAG pipeline…
   ⚙ Called: retrieve_documents
   ⚙ Called: rerank_results
   ⚙ Called: generate_answer
   ```
5. After the answer, click any **source chip** to see the exact chunk of text used

### Step 3 — Follow-up questions

Ask follow-up questions that reference previous answers — the system maintains conversation memory:
```
You:  What is the main argument of the paper?
Bot:  [detailed answer citing chunks]

You:  Can you give me more detail on that second point?
Bot:  [answer using previous context — no need to re-specify what "that" is]
```

---

## Project Structure

```
rag-assistant/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── documents.py      # POST /documents/upload, GET, DELETE
│   │   │   └── chat.py           # POST /chat (SSE), GET /chat/history
│   │   ├── core/
│   │   │   ├── config.py         # All settings via pydantic-settings
│   │   │   └── database.py       # Async SQLite via SQLAlchemy
│   │   ├── models/
│   │   │   ├── document.py       # DB table: uploaded documents
│   │   │   ├── conversation.py   # DB table: chat history
│   │   │   └── schemas.py        # Pydantic request/response shapes
│   │   ├── services/
│   │   │   ├── extractor.py      # PDF/TXT/MD text extraction
│   │   │   ├── chunker.py        # Overlapping sentence-boundary chunking
│   │   │   ├── embedder.py       # Singleton sentence-transformer + reranker
│   │   │   ├── vector_store.py   # FAISS index CRUD + persistence
│   │   │   ├── pipeline.py       # Ingestion orchestrator (extract→chunk→embed→store)
│   │   │   ├── retriever.py      # Query embed + FAISS search + rerank
│   │   │   ├── memory.py         # Load/save conversation history
│   │   │   ├── prompt_builder.py # Assemble LLM prompt from chunks + history
│   │   │   └── llm.py            # Gemini streaming (fallback direct call)
│   │   ├── agent/
│   │   │   ├── tools.py          # 4 ADK tool functions
│   │   │   ├── agent.py          # LlmAgent definition + system instruction
│   │   │   └── runner.py         # Agent execution + SSE bridge + fallback
│   │   └── main.py               # FastAPI app entry point
│   ├── data/
│   │   ├── uploads/              # Raw uploaded files (Docker volume)
│   │   └── vector_store/         # FAISS index + metadata (Docker volume)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/app/
│   │   ├── pages/
│   │   │   ├── upload/           # Drag-and-drop upload + live status polling
│   │   │   └── chat/             # SSE streaming chat + source viewer
│   │   ├── services/
│   │   │   ├── document.service.ts   # HTTP upload/list/delete
│   │   │   └── chat.service.ts       # fetch() + ReadableStream SSE consumer
│   │   ├── models/types.ts           # TypeScript interfaces
│   │   ├── app.component.ts          # Root + nav bar
│   │   ├── app.routes.ts             # Lazy-loaded routes
│   │   └── app.config.ts             # Angular providers
│   ├── nginx.conf                    # Serve Angular + proxy /api → backend
│   └── Dockerfile                    # Multi-stage: ng build → nginx
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Architecture

```
Browser (Angular)
      │  SSE stream (text/event-stream)
      ▼
nginx :80  ──/api/──►  FastAPI :8000
                             │
                    ┌────────▼────────┐
                    │  Google ADK     │
                    │  Agent          │
                    │                 │
                    │  ┌──────────┐   │
                    │  │retrieve_ │   │
                    │  │documents │   │
                    │  └────┬─────┘   │
                    │       │FAISS    │
                    │  ┌────▼─────┐   │
                    │  │rerank_   │   │
                    │  │results   │   │
                    │  └────┬─────┘   │
                    │       │cross-   │
                    │       │encoder  │
                    │  ┌────▼─────┐   │
                    │  │generate_ │   │
                    │  │answer    │   │
                    │  └────┬─────┘   │
                    └───────┼─────────┘
                            │ Gemini 1.5 Flash
                    ┌───────▼─────────┐
                    │   SQLite        │
                    │   (chat memory) │
                    └─────────────────┘
```

---

## RAG Pipeline

### Ingestion (on upload)

```
File upload
    │
    ▼
Text extraction
    PDF   → PyMuPDF (page-by-page, preserves page numbers)
    TXT   → read_text (UTF-8 / Latin-1 fallback)
    MD    → markdown→HTML→strip tags (preserves structure)
    │
    ▼
Chunking (sentence-boundary splitting)
    - Target: 500 words per chunk
    - Overlap: 50 words carried into next chunk
    - Reason: overlap prevents losing context at boundaries
    │
    ▼
Embedding  (sentence-transformers/all-MiniLM-L6-v2)
    - 384-dimensional float32 vectors
    - L2-normalised → cosine similarity = dot product
    - Runs fully locally, no API key needed
    │
    ▼
FAISS IndexFlatIP
    - In-memory index + metadata.json on disk
    - Persists across Docker restarts via named volume
```

### Retrieval (on question)

```
User question
    │
    ▼
Embed query   (same all-MiniLM-L6-v2 model)
    │
    ▼
FAISS search  (top-10 by cosine similarity)
    │
    ▼
Cross-encoder reranking  (cross-encoder/ms-marco-MiniLM-L-6-v2)
    - Scores each (query, chunk) pair together
    - More accurate than embedding similarity alone
    - Returns top-4 chunks
    │
    ▼
LLM prompt assembly
    - System: "answer only from context, cite [Chunk N]"
    - Context: numbered chunks with filenames
    - History: last 10 messages (5 turns)
    - Question: user's question
    │
    ▼
Gemini 1.5 Flash  (streaming)
    │
    ▼
SSE token stream → Angular
```

---

## Agent Design

### Tools

| Tool | When called | What it does |
|------|------------|--------------|
| `retrieve_documents` | Always first | Embed query → FAISS search → return top-10 chunks |
| `rerank_results` | After retrieve | Cross-encoder score all pairs → return top-4 |
| `summarize_context` | When context > 600 words | Trim chunks proportionally to stay in token budget |
| `generate_answer` | Last step | Build prompt → call Gemini → return answer + sources |

### Reasoning flow

```
Standard question:
  retrieve_documents → rerank_results → generate_answer

Long document:
  retrieve_documents → rerank_results → summarize_context → generate_answer

Follow-up question:
  retrieve_documents → rerank_results → generate_answer (with history_json populated)
```

### Fallback

If the ADK agent fails for any reason (import error, API rate limit, empty response), the runner automatically falls back to the **direct Phase 3 RAG pipeline** (`retriever → prompt_builder → llm`). The user sees the same interface either way — the fallback is transparent.

---

## Chat Memory

- Every user message and assistant response is stored in SQLite (`conversations` table)
- Each conversation has a `session_id` (UUID generated in the browser per tab)
- On each `/chat` request, the last **10 messages** (5 turns) are loaded and injected into the LLM prompt
- This enables follow-up questions that reference previous answers
- History is visible at `GET /chat/history/{session_id}`

---

## Source Traceability

Every answer includes `SourceChunk` objects:
```json
{
  "document_id": "uuid",
  "filename": "report.pdf",
  "chunk_text": "The exact text used as context...",
  "score": 0.87
}
```
In the UI: source chips appear below each answer. Clicking expands the exact chunk. The score shows cross-encoder confidence (0–1).

---

## SSE Streaming Protocol

Events sent from backend to browser:
```
data: {"type": "thinking", "data": "Agent starting RAG pipeline…"}
data: {"type": "thinking", "data": "Called: retrieve_documents"}
data: {"type": "token",    "data": "The "}
data: {"type": "token",    "data": "answer "}
data: {"type": "token",    "data": "is... "}
data: {"type": "sources",  "data": [{...}, {...}]}
data: {"type": "done"}
```

The Angular frontend uses raw `fetch()` with `ReadableStream` (not Angular's `HttpClient`, which buffers SSE). nginx is configured with `proxy_buffering off` so Docker deployments don't buffer the stream.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_API_KEY` | **Yes** | — | Google AI Studio key for Gemini + ADK |
| `ENVIRONMENT` | No | `production` | `development` enables uvicorn `--reload` |

Get a free API key at: https://aistudio.google.com/app/apikey

---

## Development (without Docker)

### Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm start          # runs on http://localhost:4200, proxies /api → :8000
```

---

## Tuning Parameters

All in `backend/app/core/config.py`:

| Setting | Default | Effect |
|---------|---------|--------|
| `CHUNK_SIZE` | 500 | Words per chunk — larger = more context per chunk |
| `CHUNK_OVERLAP` | 50 | Words shared between consecutive chunks |
| `TOP_K_RETRIEVE` | 10 | Candidates fetched from FAISS before reranking |
| `TOP_K_RERANK` | 4 | Final chunks sent to LLM after reranking |

---

## Build Phases

| Phase | Status | What was built |
|-------|--------|---------------|
| 1 | ✅ | Project scaffold, Docker, DB models, API stubs, Angular skeleton |
| 2 | ✅ | Text extraction, chunking, embedding, FAISS vector store, background ingestion |
| 3 | ✅ | RAG query pipeline, reranking, Gemini streaming, chat memory, source tracing |
| 4 | ✅ | Google ADK agent with 4 tools, fallback to direct RAG, thinking steps UI |
