#!/usr/bin/env bash
# ============================================================
#  RAG Assistant — Demo / smoke-test script
#  Usage:  chmod +x demo.sh && ./demo.sh
# ============================================================
set -euo pipefail

BASE="http://localhost:8000"
FRONT="http://localhost:4200"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}!${NC} $*"; }
fail() { echo -e "${RED}✗${NC} $*"; exit 1; }

echo ""
echo "=================================================="
echo "  Agentic RAG Assistant — Demo Script"
echo "=================================================="
echo ""

# ── 1. Check services are up ──────────────────────────────
echo "1. Checking services…"

if ! curl -sf "$BASE/health" > /dev/null 2>&1; then
    fail "Backend not reachable at $BASE — run: docker compose up"
fi
ok "Backend is healthy"

if ! curl -sf "$FRONT" > /dev/null 2>&1; then
    warn "Frontend not reachable at $FRONT (may still be building)"
else
    ok "Frontend is serving at $FRONT"
fi

# ── 2. Upload a sample document ───────────────────────────
echo ""
echo "2. Uploading sample document…"

# Create a sample text file
cat > /tmp/rag_demo_doc.txt << 'SAMPLE'
Introduction to Retrieval-Augmented Generation

Retrieval-Augmented Generation (RAG) is a technique that combines information
retrieval with language model generation. Instead of relying solely on a
language model's parametric memory, RAG retrieves relevant documents from an
external knowledge base and uses them as context for generation.

Key components of a RAG system:
1. Document ingestion: Text is extracted, chunked, and embedded into vectors.
2. Vector storage: Embeddings are stored in a vector database (e.g., FAISS).
3. Query processing: The user question is embedded using the same model.
4. Retrieval: Top-k nearest chunks are retrieved via similarity search.
5. Reranking: A cross-encoder reranks candidates for higher precision.
6. Generation: The LLM generates an answer grounded in the retrieved context.

Advantages of RAG over fine-tuning:
- No retraining required when knowledge changes
- Sources can be cited and verified
- Works with private, up-to-date, or domain-specific documents
- Lower cost than continually fine-tuning large models

The retrieval step typically uses bi-encoder models for fast approximate search,
followed by a cross-encoder for precise reranking. This two-stage approach
balances speed and accuracy.
SAMPLE

UPLOAD_RESPONSE=$(curl -sf -X POST "$BASE/documents/upload" \
    -F "file=@/tmp/rag_demo_doc.txt" \
    -H "Accept: application/json")

if [ -z "$UPLOAD_RESPONSE" ]; then
    fail "Upload failed — no response from backend"
fi

DOC_ID=$(echo "$UPLOAD_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
STATUS=$(echo "$UPLOAD_RESPONSE"  | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
ok "Uploaded document — ID: $DOC_ID  Status: $STATUS"

# ── 3. Wait for ingestion ─────────────────────────────────
echo ""
echo "3. Waiting for ingestion to complete…"

for i in $(seq 1 20); do
    STATUS=$(curl -sf "$BASE/documents/$DOC_ID" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
    if [ "$STATUS" = "ready" ]; then
        CHUNKS=$(curl -sf "$BASE/documents/$DOC_ID" | python3 -c "import sys,json; print(json.load(sys.stdin)['chunk_count'])")
        ok "Document ready — $CHUNKS chunks indexed"
        break
    elif [ "$STATUS" = "error" ]; then
        fail "Ingestion failed — check docker logs rag_backend"
    else
        echo "   Status: $STATUS (attempt $i/20)…"
        sleep 3
    fi
done

if [ "$STATUS" != "ready" ]; then
    fail "Timed out waiting for ingestion"
fi

# ── 4. Ask a question ─────────────────────────────────────
echo ""
echo "4. Sending test question via chat API…"

SESSION="demo-session-$(date +%s)"
QUESTION="What is RAG and what are its key components?"

echo "   Question: $QUESTION"

RESPONSE_CHUNKS=""
while IFS= read -r line; do
    if [[ "$line" == data:* ]]; then
        JSON="${line#data: }"
        TYPE=$(echo "$JSON" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('type',''))" 2>/dev/null || echo "")
        DATA=$(echo "$JSON" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('data',''))" 2>/dev/null || echo "")
        if [ "$TYPE" = "token" ]; then
            RESPONSE_CHUNKS+="$DATA"
        fi
    fi
done < <(curl -sf -X POST "$BASE/chat" \
    -H "Content-Type: application/json" \
    -d "{\"question\": \"$QUESTION\", \"session_id\": \"$SESSION\"}" \
    --no-buffer 2>/dev/null)

if [ -n "$RESPONSE_CHUNKS" ]; then
    ok "Got streaming response (${#RESPONSE_CHUNKS} chars)"
    echo ""
    echo "   Answer preview: ${RESPONSE_CHUNKS:0:200}…"
else
    warn "No token response received — check GOOGLE_API_KEY in .env"
fi

# ── 5. List documents ─────────────────────────────────────
echo ""
echo "5. Listing uploaded documents…"

DOC_LIST=$(curl -sf "$BASE/documents")
TOTAL=$(echo "$DOC_LIST" | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])")
ok "$TOTAL document(s) in system"

# ── Summary ───────────────────────────────────────────────
echo ""
echo "=================================================="
echo "  Demo complete!"
echo "=================================================="
echo ""
echo "  Open in browser:"
echo "    Frontend:  $FRONT"
echo "    API docs:  $BASE/docs"
echo ""
echo "  To view logs:     docker compose logs -f"
echo "  To stop:          docker compose down"
echo "  To wipe data:     docker compose down -v"
echo ""
