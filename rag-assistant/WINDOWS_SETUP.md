# Windows Setup Guide

## The error you saw

```
unable to get image 'rag-assistant-backend': request returned 500 Internal Server Error
```

This is caused by:
1. The obsolete `version:` key in `docker-compose.yml` (now removed)
2. Stale Docker Desktop state / pipe connection issue
3. `container_name` conflicting with a cached image name (now removed)

All three are fixed in this updated version.

---

## Prerequisites

1. **Docker Desktop for Windows** — version 4.25 or newer
   - Download: https://www.docker.com/products/docker-desktop/
   - During install: enable **"Use WSL 2 based engine"** (recommended)
   - After install: Settings → Resources → set at least **4 GB RAM**

2. **WSL 2** (Windows Subsystem for Linux)
   ```powershell
   # Run in PowerShell as Administrator if not already installed:
   wsl --install
   wsl --set-default-version 2
   ```

3. **Google API Key**
   - Go to: https://aistudio.google.com/app/apikey
   - Click "Create API Key" → copy the key

---

## Step-by-step setup

### 1. Clean up any stale Docker state first

Open **PowerShell** and run:

```powershell
# Stop and remove any old containers/volumes from previous attempts
docker compose down -v 2>$null
docker system prune -f
```

### 2. Set your API key

In the project folder, create a `.env` file:

```powershell
cd C:\Users\Dell\Desktop\agentic_rag_knowledge_assistant\rag-assistant

# Copy the example file
copy .env.example .env

# Open it in Notepad and set your key
notepad .env
```

The `.env` file should look like:
```
GOOGLE_API_KEY=AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXX
ENVIRONMENT=production
```

### 3. Build and run

```powershell
docker compose up --build
```

**Expected output sequence:**
```
 => [backend] FROM python:3.11-slim                           ✓
 => [backend] RUN apt-get update ...                          ✓  (~30s)
 => [backend] RUN pip install ...                             ✓  (~3 min)
 => [backend] RUN python -c "... SentenceTransformer ..."    ✓  (~2 min, downloads models)
 => [frontend builder] FROM node:20-alpine                    ✓
 => [frontend builder] RUN npm install                        ✓  (~1 min)
 => [frontend builder] RUN npm run build                      ✓  (~1 min)

rag-assistant-backend-1   | INFO: Application startup complete.
rag-assistant-frontend-1  | nginx: ready
```

**First build takes 8–15 minutes** — it's downloading ~400 MB of ML models.
Subsequent `docker compose up` (without `--build`) starts in under 20 seconds.

### 4. Open the app

- **Frontend:** http://localhost:4200
- **API Docs:** http://localhost:8000/docs

---

## If you still get errors

### Error: "port is already allocated"
```powershell
# Find what's using port 8000
netstat -ano | findstr :8000
# Kill it (replace PID with the number from above)
taskkill /PID <PID> /F
```

### Error: "no space left on device" or build fails mid-way
```powershell
# Free up Docker disk space
docker system prune -a --volumes
# Then retry
docker compose up --build
```

### Error: "WSL 2 installation is incomplete"
```powershell
# Run as Administrator:
wsl --update
wsl --set-default-version 2
# Restart Docker Desktop
```

### Error: pip install fails for torch/faiss
The `requirements.txt` now uses the CPU-only PyTorch wheel which is much smaller. If it still fails:
```powershell
# Build only the backend to see full error
docker compose build backend
```

### Docker Desktop crashes or gives 500 errors
1. Right-click Docker Desktop tray icon → **Restart**
2. Wait 30 seconds for it to fully restart
3. Run `docker compose up --build` again

### Slow build / timeout downloading models
The model download step in the Dockerfile can time out on slow connections.
If it does, just re-run — Docker caches completed layers so it resumes from where it stopped:
```powershell
docker compose up --build
```

---

## Useful PowerShell commands

```powershell
# View live logs
docker compose logs -f

# View only backend logs
docker compose logs -f backend

# Stop everything (keeps data)
docker compose down

# Stop everything AND delete all data
docker compose down -v

# Open a shell inside the backend container
docker exec -it rag-assistant-backend-1 bash

# Check how many chunks are indexed
docker exec rag-assistant-backend-1 python -c "
import json, os
path = 'data/vector_store/metadata.json'
if os.path.exists(path):
    data = json.load(open(path))
    print(f'Total chunks indexed: {len(data)}')
else:
    print('No index yet — upload a document first')
"

# Rebuild after code changes (without --build reuses cached layers)
docker compose up --build
```

---

## Running without Docker (for development)

If Docker is giving you trouble, you can run both services natively:

### Backend (Python)
```powershell
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend (Node)
```powershell
cd frontend
npm install
npm start
# Opens at http://localhost:4200
# Automatically proxies /api calls to http://localhost:8000
```
