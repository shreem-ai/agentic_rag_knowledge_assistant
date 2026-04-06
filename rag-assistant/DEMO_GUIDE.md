# Demo Guide — Step by Step

## Prerequisites

| Requirement | Version | Check |
|-------------|---------|-------|
| Docker Desktop | 24+ | `docker --version` |
| Docker Compose | 2.20+ | `docker compose version` |
| Google API Key | — | https://aistudio.google.com/app/apikey |
| Free disk space | 3 GB | For ML models baked into image |
| Free RAM | 4 GB | For FAISS + sentence-transformers |

---

## Setup (one-time, ~10 minutes)

```bash
# 1. Unzip the project
unzip rag-assistant-final.zip
cd rag-assistant

# 2. Add your Google API key
cp .env.example .env
nano .env           # or any text editor
# Set:  GOOGLE_API_KEY=AIzaSy...

# 3. Build and start (downloads ~300MB of ML models — takes 5-10 min)
docker compose up --build

# You should see:
#   rag_backend   | INFO:     Application startup complete.
#   rag_frontend  | /docker-entrypoint.sh: Configuration complete; ready for start up
```

---

## Demo Flow

### Part 1 — Upload a document

1. Open **http://localhost:4200**
2. You land on the **Upload** page
3. Drag a PDF onto the drop zone (or click to browse)
   - Good test documents: any research paper, manual, or report in PDF
4. The badge shows **⏳ processing** — refreshes automatically every 3 seconds
5. After 10–30 seconds it shows **✓ ready** with a chunk count

**What's happening behind the scenes:**
- PyMuPDF extracts text page by page
- Text is split into 500-word overlapping chunks
- `all-MiniLM-L6-v2` embeds each chunk → 384-dim float vector
- Vectors stored in FAISS index + written to `data/vector_store/`

---

### Part 2 — Ask a question

1. Click **Go to Chat →** or the Chat nav link
2. Type a question about your document, e.g.:
   - *"What is the main argument of this paper?"*
   - *"Summarise the methodology section"*
   - *"What datasets were used?"*
3. Press Enter and watch:
   - **Thinking steps** appear first (small purple badges):
     - `⚙ Agent starting RAG pipeline…`
     - `⚙ Called: retrieve_documents`
     - `⚙ Called: rerank_results`
     - `⚙ Called: generate_answer`
   - **Answer tokens stream in** word by word
   - **Source chips** appear below the answer

4. Click a **source chip** (e.g. `📄 myfile.pdf  87%`) to expand the exact chunk of text used

---

### Part 3 — Follow-up questions

Ask a follow-up that references the previous answer:

```
You:  What is the main contribution of this work?
Bot:  [answer citing chunks 1 and 3]

You:  Can you elaborate on that first point?
Bot:  [answer with context from previous turn — knows what "that first point" is]
```

The system stores the last 10 messages in SQLite and injects them into the LLM prompt.

---

### Part 4 — Multiple documents

1. Upload a second (different) document
2. Go to Chat
3. Leave all sidebar checkboxes **unchecked** → searches both documents
4. Check only one document → restricts search to that document
5. Ask a question that spans both documents:
   - *"Compare the approaches described in both documents"*

---

### Part 5 — API Explorer

Open **http://localhost:8000/docs** (Swagger UI) to explore:

- `POST /documents/upload` — try uploading directly
- `GET /documents` — see all uploaded documents
- `POST /chat` — send a raw chat request (note: SSE won't render in Swagger)
- `GET /chat/history/{session_id}` — view stored conversation

---

## Automated Smoke Test

```bash
./demo.sh
```

This script:
1. Checks backend + frontend health
2. Uploads a sample TXT document
3. Waits for ingestion
4. Sends a test question
5. Verifies streaming response arrives
6. Prints a summary

---

## Troubleshooting

**Build takes too long / fails on model download:**
```bash
# Build just the backend to see errors
docker compose build backend
```

**"GOOGLE_API_KEY is not set" error:**
```bash
# Check your .env file
cat .env
# Rebuild after changing .env
docker compose up --build
```

**Frontend shows blank page:**
```bash
# Check nginx logs
docker compose logs frontend
# Re-build Angular
docker compose build frontend
```

**"No documents are ready yet" in chat:**
- Make sure you uploaded a file and the badge shows ✓ ready
- Check ingestion logs: `docker logs rag_backend | grep -i ingest`

**Port 4200 already in use:**
```bash
# Change port in docker-compose.yml
ports:
  - "3000:80"   # use port 3000 instead
```

**Wipe all data and start fresh:**
```bash
docker compose down -v   # removes the named volume too
docker compose up --build
```

---

## Useful Commands

```bash
# View live logs
docker compose logs -f

# View only backend logs
docker compose logs -f backend

# Open a shell in the backend container
docker exec -it rag_backend bash

# Inspect the FAISS metadata
docker exec rag_backend python3 -c "
import json
data = json.load(open('data/vector_store/metadata.json'))
print(f'Total chunks indexed: {len(data)}')
for d in data[:3]:
    print(f'  doc={d[\"doc_id\"][:8]}… chunk={d[\"chunk_index\"]} words={len(d[\"text\"].split())}')
"

# Check SQLite conversation history
docker exec rag_backend python3 -c "
import sqlite3
conn = sqlite3.connect('data/rag_assistant.db')
rows = conn.execute('SELECT role, substr(content,1,80) FROM conversations ORDER BY created_at DESC LIMIT 10').fetchall()
for r in rows: print(r[0].upper(), ':', r[1])
"

# Stop everything
docker compose down

# Stop and remove data volumes
docker compose down -v
```
