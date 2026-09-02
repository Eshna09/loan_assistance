# Loan Knowledge Assistance

A Retrieval-Augmented Generation (RAG) system for answering loan-related questions. Built with a microservices architecture, a React dashboard, and powered by Code Llama via Ollama.

---

## What it does

Users ask questions about loans — eligibility, interest rates, repayment options, risks — and get answers grounded in a curated knowledge base. The system retrieves the most relevant document chunks using semantic search (MiniLM + FAISS), builds a prompt, and passes it to Code Llama for generation. All pipeline steps are observable in the dashboard.

---

## Architecture

```
Browser
   │
   ▼
Frontend (React/Vite) :5173  ──── or ────  nginx :3000 (Docker)
   │
   ▼
App Service :8000          ← orchestration + public API
   ├──► Retrieval Service :8001   MiniLM embeddings + FAISS index
   │         └──► Data Service :8003   documents, chunking, uploads
   └──► LLM Service :8002         Ollama client
             └──► Ollama :11434   Code Llama 7B
```

| Service | Port | Responsibility |
|---|---|---|
| App Service | 8000 | Orchestration, public API |
| Retrieval Service | 8001 | Sentence embeddings + FAISS search |
| LLM Service | 8002 | Ollama / Code Llama inference |
| Data Service | 8003 | Document storage, chunking, uploads |
| Frontend | 5173 / 3000 | React dashboard |

---

## Tech Stack

**Backend**
- Python 3.12, FastAPI, Uvicorn
- `sentence-transformers` (all-MiniLM-L6-v2)
- `faiss-cpu` for vector search
- Ollama + `codellama:7b` for generation
- `pypdf`, `python-docx` for document ingestion

**Frontend**
- React 18, Vite 5, Tailwind CSS 3

**Infrastructure**
- Docker + Docker Compose (6-container stack)
- nginx reverse proxy
- Named volumes for uploaded docs and Ollama models

---

## Project Structure

```
.
├── backend/                  # Single-process monolith (Exercises 1–3)
│   ├── main.py
│   ├── knowledge_base.py
│   ├── finance_kb/           # Built-in loan knowledge documents
│   └── requirements.txt
│
├── services/                 # Microservices (Exercise 4)
│   ├── app_service/
│   ├── retrieval_service/
│   ├── llm_service/
│   ├── data_service/
│   └── common/
│
├── frontend/                 # React dashboard
│   └── src/
│       └── components/
│
├── evaluation/               # RAG evaluation suite
│   ├── eval_set.json
│   ├── run_eval.py
│   ├── score.py
│   └── results/
│
├── docker-compose.yml
├── start_backend.bat         # Run monolith locally
├── start_services.bat        # Run all 4 services locally
├── start_frontend.bat        # Run Vite dev server
└── ARCHITECTURE.md           # Detailed architecture notes
```

---

## Running Locally (without Docker)

### Prerequisites
- Python 3.10+
- Node.js 18+
- [Ollama](https://ollama.com) installed and running

### 1. Start Ollama and pull the model
```bash
ollama serve
ollama pull codellama:7b
```

### 2. Install backend dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 3. Start all four services
Run from the project root:
```bash
start_services.bat
```
This opens 4 terminal windows:
- `data-service` on :8003
- `retrieval-service` on :8001 (takes ~20s to load MiniLM)
- `llm-service` on :8002
- `app-service` on :8000

### 4. Start the frontend
```bash
start_frontend.bat
```

Open **http://localhost:5173** in your browser.

- API docs: http://localhost:8000/docs
- Aggregate health: http://localhost:8000/health

---

## Running with Docker

### Prerequisites
- Docker Desktop running
- ~8 GB free disk space (model weights + images)

```bash
# Build and start all containers
docker compose up --build -d

# Pull Code Llama (once, ~3.8 GB)
docker compose exec ollama ollama pull codellama:7b

# Check everything is healthy
docker compose ps
curl http://localhost:8000/health
```

Open **http://localhost:3000**.

> To use a host Ollama instead of the container:
> ```bash
> docker compose up -d --scale ollama=0
> # Set OLLAMA_URL=http://host.docker.internal:11434 in llm-service environment
> ```

---

## API Reference

### App Service — :8000 (public)

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Aggregate health of all services |
| POST | `/ask` | Question → answer (full RAG pipeline) |
| POST | `/ask/debug` | Full pipeline with trace, embeddings, chunks |
| POST | `/retrieve` | Retrieval only |
| POST | `/generate` | LLM generation only |
| GET | `/kb/info` | Knowledge base metadata |
| POST | `/kb/upload` | Upload documents (.txt, .md, .pdf, .docx) |
| DELETE | `/kb/documents/{filename}` | Remove an uploaded document |

### Example

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the eligibility criteria for a home loan?"}'
```

---

## Evaluation

The `evaluation/` directory contains a test suite to measure RAG quality.

```bash
cd evaluation
python run_eval.py      # runs retrieval + generation over eval_set.json
python score.py         # computes precision, recall, F1 on results
```

Results are written to `evaluation/results/`.

---

## Knowledge Base

Six built-in documents cover:
- Loan types
- Eligibility criteria
- Interest rates
- Repayment options
- Loan risks
- General loans overview

You can upload additional `.txt`, `.md`, `.pdf`, or `.docx` files through the dashboard or via `POST /kb/upload`. The index rebuilds automatically.

---

## Notes

- The LLM step is non-fatal: if Ollama is unreachable, `/ask/debug` still returns embeddings, retrieved chunks, and the prompt — with `answer: null`.
- The Retrieval Service self-heals: it checks the Data Service version before every query and reindexes if documents changed.
- Docker uses host port `11435` for Ollama (not 11434) to avoid clashing with a local Ollama install.
