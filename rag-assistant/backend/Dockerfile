FROM python:3.11-slim

WORKDIR /app

# System dependencies for PDF processing and native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (better Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Pre-download HuggingFace models into the image
# This avoids a slow cold-start on the very first request
RUN python -c "\
from sentence_transformers import SentenceTransformer, CrossEncoder; \
print('Downloading embedding model...'); \
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2'); \
print('Downloading reranker model...'); \
CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2'); \
print('Done.')"

# Copy application source
COPY . .

# Ensure data directories exist (volume will overlay these at runtime)
RUN mkdir -p data/uploads data/vector_store

EXPOSE 8000

# Healthcheck using curl (more reliable on Windows Docker Desktop)
HEALTHCHECK --interval=20s --timeout=10s --start-period=90s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
