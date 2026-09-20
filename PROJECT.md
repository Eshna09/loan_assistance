# Loan Knowledge Assistance — Complete Project Documentation

> One document covering the full project: architecture, all services, file map, APIs, evaluation, guardrails, and how to run everything.

---

## Table of Contents

1. [What It Does](#1-what-it-does)
2. [Architecture Overview](#2-architecture-overview)
3. [Complete File Map — What Every File Contains](#3-complete-file-map)
4. [Services — Detailed Reference](#4-services-detailed-reference)
   - [Data Service :8003](#41-data-service-8003)
   - [Retrieval Service :8001](#42-retrieval-service-8001)
   - [LLM Service :8002](#43-llm-service-8002)
   - [App Service :8000](#44-app-service-8000)
5. [Guardrails (Week 5)](#5-guardrails)
6. [Model Evaluation (Week 4)](#6-model-evaluation)
7. [RAG Pipeline Analysis](#7-rag-pipeline-analysis)
8. [Running the Project](#8-running-the-project)
9. [API Reference](#9-api-reference)
10. [Knowledge Base](#10-knowledge-base)

---

## 1. What It Does

Users ask questions about loans — eligibility, interest rates, repayment, risks — and get answers grounded in a curated knowledge base. The pipeline:

1. Embeds the question using MiniLM (`all-MiniLM-L6-v2`)
2. Searches a FAISS vector index for the top-3 most relevant document chunks
3. Passes those chunks + the question into a RAG prompt
4. Sends the prompt to Code Llama 7B via Ollama for generation
5. Returns the answer with full trace, evidence, and guardrail metadata

All pipeline steps are observable in the React dashboard. Input guardrails block out-of-scope and malformed questions before any retrieval or LLM call is made.

---

## 2. Architecture Overview

```
Browser
   │
   ▼
Frontend (React/Vite) :5173  ──── or ────  nginx :3000 (Docker)
   │
   ▼ /api/*
App Service :8000              orchestration + public API
   ├──► Retrieval Service :8001     MiniLM embeddings + FAISS index
   │         └──► Data Service :8003    documents, chunking, uploads
   └──► LLM Service :8002            Ollama client
             └──► Ollama :11434       Code Llama 7B
```

### Service Responsibilities

| Service | Port | Owns | Changes when… |
|---|---|---|---|
| App Service | 8000 | Nothing but request sequencing | pipeline order or prompt changes |
| Retrieval Service | 8001 | Embedding model + FAISS index | model, dimension, or search strategy changes |
| LLM Service | 8002 | The Ollama client | runtime or model changes |
| Data Service | 8003 | Documents on disk, chunking, uploads | document formats or chunk parameters change |
| Frontend | 5173 / 3000 | React dashboard | UI changes |

### Why four services

1. **Only the Data Service touches the filesystem.** Retrieval has no volume mount.
2. **Only the Retrieval Service loads a model.** Its image carries torch + MiniLM; the other three are ~271–293 MB slim Python images.
3. **Only the LLM Service knows Ollama exists.** Swapping runtimes means changing one file.
4. **The App Service holds no state.** That is what makes it the only service the browser needs to reach.

### Docker image sizes

| Image | Size |
|---|---|
| `retrieval-service` | 2.29 GB |
| `data-service` | 293 MB |
| `app-service` | 271 MB |
| `llm-service` | 271 MB |
| `frontend` | 73.9 MB |

---

## 3. Complete File Map

Every file in the project and what it contains.

### Root

| File | Contains |
|---|---|
| `docker-compose.yml` | Full 6-container stack definition (data, retrieval, llm, app, ollama, frontend). Named volumes for uploads and Ollama models. |
| `start_services.bat` | Launches all 4 backend services in separate terminal windows for local (non-Docker) development. |
| `start_backend.bat` | Launches only the legacy single-process backend (`backend/main.py`) on :8000. |
| `start_frontend.bat` | Runs `npm install` + `npm run dev` for the Vite frontend on :5173. |
| `PROJECT.md` | This file — complete project documentation. |

### `backend/` — Single-process monolith (Weeks 1–3)

| File | Contains |
|---|---|
| `backend/main.py` | Original FastAPI app. All 4 responsibilities in one process: `/retrieve`, `/generate`, `/ask`, `/ask/debug`, `/kb/info`, `/kb/upload`, `/kb/documents/{name}`. Talks directly to Ollama at localhost:11434. |
| `backend/knowledge_base.py` | MiniLM model loading, FAISS index build, `retrieve_context()`, `get_kb_info()`, `add_document()`, `remove_document()`. Manages both built-in and uploaded document indexes in-process. |
| `backend/requirements.txt` | `fastapi`, `uvicorn`, `sentence-transformers`, `faiss-cpu`, `numpy`, `requests`, `python-multipart`, `pypdf`, `python-docx` |
| `backend/finance_kb/loans.txt` | General loan overview — what a loan is, key terms (principal, interest, collateral, default). |
| `backend/finance_kb/loan_types.txt` | Loan types: personal, home, car, student, business, secured, unsecured. Selection factors: purpose, repayment capacity, cost, term, collateral, risk. |
| `backend/finance_kb/loan_interest.txt` | Interest rate types (fixed, variable, compound, simple), APR, how rates are set, comparison factors. |
| `backend/finance_kb/loan_repayment.txt` | EMI, repayment schedules, prepayment, part-payment, moratorium, consequences of missed payments. |
| `backend/finance_kb/loan_eligibility.txt` | Credit score, income requirements, debt-to-income ratio, required documents (identity, address, income proof, bank statement, tax docs). |
| `backend/finance_kb/loan_risks.txt` | Borrower risks (over-borrowing, interest rate risk, default), secured vs unsecured default consequences, lender rights. |
| `backend/uploaded_kb/` | Runtime-uploaded documents. Contains test files: `Loan_Knowledge_Base_Testing.txt`, `Loan_Knowledge_Base_Testing_1.txt`, `Loan_Policy_V2_Updated.txt` and their `.meta.json` sidecars. |

### `services/` — Microservices (Week 4+)

#### `services/common/`

| File | Contains |
|---|---|
| `services/common/__init__.py` | Empty package marker. |
| `services/common/chunking.py` | `chunk_text(text, chunk_size=300, overlap=50)` — splits text into overlapping character windows. Constants: `CHUNK_SIZE=300`, `OVERLAP=50`. Used by both backend monolith and Data Service. |
| `services/common/prompts.py` | `build_rag_prompt(context, question)` — the standard RAG prompt template instructing the model to answer only from retrieved context. `CONTEXT_SEPARATOR` constant (`\n---\n`). |

#### `services/data_service/`

| File | Contains |
|---|---|
| `services/data_service/main.py` | FastAPI app on :8003. Endpoints: `GET /health`, `GET /version`, `GET /documents`, `GET /chunks`, `POST /documents`, `DELETE /documents/{name}`. Loads 6 built-in KB files + uploaded files. Thread-safe `_version` counter incremented on every mutation. Text extraction for `.txt`, `.md`, `.pdf`, `.docx`. |
| `services/data_service/metadata_store.py` | `load_metadata()`, `save_metadata()`, `delete_metadata()`, `make_upload_metadata()` — reads/writes `.meta.json` sidecar files alongside uploaded documents. Stores: `document_type`, `loan_type`, `version`, `effective_date`, `upload_date`. |
| `services/data_service/requirements.txt` | `fastapi`, `uvicorn`, `python-multipart`, `pypdf`, `python-docx` |
| `services/data_service/Dockerfile` | Slim Python image for the data service. |
| `services/data_service/__init__.py` | Empty package marker. |

#### `services/retrieval_service/`

| File | Contains |
|---|---|
| `services/retrieval_service/main.py` | FastAPI app on :8001. Loads `all-MiniLM-L6-v2` at startup. `rebuild_index()` — fetches all chunks from Data Service, embeds with MiniLM, builds `faiss.IndexFlatL2(384)`. `ensure_fresh_index()` — checks Data Service `/version` before every query, rebuilds if stale. Endpoints: `GET /health`, `GET /index/info`, `POST /reindex`, `POST /embed`, `POST /retrieve`. |
| `services/retrieval_service/requirements.txt` | `fastapi`, `uvicorn`, `sentence-transformers`, `faiss-cpu`, `numpy`, `requests` |
| `services/retrieval_service/Dockerfile` | Heavy image — bakes in MiniLM weights at build time so container start needs no network. CPU-only torch via PyTorch CPU wheel index. |

#### `services/llm_service/`

| File | Contains |
|---|---|
| `services/llm_service/main.py` | FastAPI app on :8002. Wraps Ollama behind a stable HTTP contract. `POST /generate` — forwards prompt to `ollama:11434/api/generate`, returns `{answer, model, runtime, duration_ms}`. `GET /health` — checks Ollama reachability and whether `codellama:7b` is pulled. `GET /models` — lists available Ollama models. |
| `services/llm_service/requirements.txt` | `fastapi`, `uvicorn`, `requests` |
| `services/llm_service/Dockerfile` | Slim image. OLLAMA_URL, OLLAMA_MODEL, GENERATE_TIMEOUT injected via env. |

#### `services/app_service/`

| File | Contains |
|---|---|
| `services/app_service/main.py` | FastAPI orchestrator on :8000. Full intent-based routing: `classify_intent()` → LOAN (→ FAISS RAG) / CODEBASE (→ repo analysis) / OUT_OF_SCOPE (→ immediate reject). `Trace` class records every downstream HTTP call with timing. All public endpoints: `/health`, `/ask`, `/ask/debug`, `/ask/evidence`, `/retrieve`, `/generate`, `/kb/info`, `/kb/upload`, `/kb/upload/with-metadata`, `/kb/documents/{name}`, `/playground/models`, `/playground/ask`. |
| `services/app_service/guardrails.py` | All guardrail logic. `check_input(question)` — validates empty, length > 1000, out-of-scope patterns. `check_evidence_sufficiency(question, chunks, distances)` — rejects if top-1 L2 > 1.2. `validate_output(answer, question, context)` — checks relevance (word overlap ≥ 8%), grounding, format. `classify_intent(question)` — routes to LOAN / CODEBASE / OUT_OF_SCOPE domain. |
| `services/app_service/evidence.py` | `build_evidence(chunks, distances)` — attaches confidence tier (HIGH/MEDIUM/LOW) to each chunk. `detect_conflicts(chunks)` — finds version/date conflicts across chunks from the same source. `resolve_version(chunks, conflicts)` — picks newest version when conflict detected. `validate_grounding(answer, context)` — computes word-overlap groundedness score. `determine_evidence_status()` — returns `supported` / `partially_supported` / `unsupported` / `insufficient_evidence`. |
| `services/app_service/source_graph.py` | `build_source_graph(question, chunks, distances, ...)` — builds a node/edge graph for the SourceGraph dashboard component. Nodes: question, documents, chunks, answer. Edges: retrieval with L2 distance labels. |
| `services/app_service/repo_analysis.py` | `get_repo_context(question)` — reads actual source files from the repo to answer codebase questions without FAISS. `build_repo_prompt(context, question)` — prompt template for repository questions. Maps codebase question keywords to specific source files. |
| `services/app_service/requirements.txt` | `fastapi`, `uvicorn`, `requests`, `python-multipart` |
| `services/app_service/Dockerfile` | Slim image. DATA_SERVICE_URL, RETRIEVAL_SERVICE_URL, LLM_SERVICE_URL, CORS_ORIGINS injected via env. |

### `frontend/`

| File | Contains |
|---|---|
| `frontend/src/App.jsx` | Root component. Top-level page navigation between all dashboard sections. |
| `frontend/src/index.css` | Global Tailwind CSS base styles. |
| `frontend/src/main.jsx` | React 18 root mount. |
| `frontend/src/components/RAGDemo.jsx` | Main RAG demo interface. Question input, answer display, `GuardrailBanner` component showing guardrail status, evidence panel toggle. |
| `frontend/src/components/EvidencePanel.jsx` | Renders evidence chunks with confidence tiers, conflict detection results, version resolution, groundedness score. |
| `frontend/src/components/ModelPlayground.jsx` | Lets user pick any installed Ollama model and run a question through the full RAG pipeline. Calls `GET /playground/models` and `POST /playground/ask`. |
| `frontend/src/components/EvaluationDashboard.jsx` | Displays Week 4 quantitative evaluation results. Accuracy, hallucination, latency, resource metrics per model. |
| `frontend/src/components/RAGAnalysis.jsx` | Visualises the 6 RAG analysis cases (A–F) from Week 4 pipeline analysis. |
| `frontend/src/components/RepositoryAnalysis.jsx` | Shows codebase RAG probe results — retrieval vs answer file recall at k=3 and k=8. |
| `frontend/src/components/KnowledgeBase.jsx` | Document list, chunk counts, upload interface (`POST /kb/upload`), document deletion. |
| `frontend/src/components/ChunkingViewer.jsx` | Shows how a sample text is chunked with 300-char windows and 50-char overlap. |
| `frontend/src/components/EmbeddingViewer.jsx` | Visualises the 384-dim MiniLM embedding preview for a query. |
| `frontend/src/components/VectorDatabase.jsx` | FAISS index stats: vector count, dimension, index type, indexed version. |
| `frontend/src/components/PipelineOverview.jsx` | Step-by-step animated view of the full RAG pipeline. |
| `frontend/src/components/PipelineSummary.jsx` | Compact pipeline summary card. |
| `frontend/src/components/ServiceArchitecture.jsx` | Live service-to-service call trace from `/ask/debug`, rendered as a table with measured durations. |
| `frontend/src/components/ApiArchitecture.jsx` | Static diagram of all service API endpoints. |
| `frontend/src/components/DockerArchitecture.jsx` | Docker Compose container topology diagram. |
| `frontend/src/components/QueryHistory.jsx` | Stores and replays previous queries with their answers. |
| `frontend/src/components/SourceGraph.jsx` | Renders the node/edge source graph from `/ask/debug` response. |
| `frontend/src/components/Header.jsx` | Dashboard top header with service health indicators. |
| `frontend/src/components/SectionNav.jsx` | In-page section navigation component. |
| `frontend/src/components/ui/Section.jsx` | Reusable card/section wrapper. |
| `frontend/src/data/staticData.js` | Static lookup data for the evaluation dashboard (model comparison tables, chart data). |
| `frontend/src/hooks/useBackendStatus.js` | Custom React hook that polls `GET /health` and returns per-service status for the header indicators. |
| `frontend/package.json` | `react@18`, `vite@5`, `tailwindcss@3`. Scripts: `dev`, `build`, `preview`. |
| `frontend/index.html` | Vite HTML entry point. |
| `frontend/nginx.conf` | nginx config for Docker deployment. Proxies `/api/*` to `app-service:8000`. Serves the built React app on port 80. |
| `frontend/Dockerfile` | Two-stage build: Node for `npm run build`, then nginx:alpine to serve dist/. |
| `frontend/postcss.config.js` | PostCSS config for Tailwind. |

### `evaluation/`

| File | Contains |
|---|---|
| `evaluation/eval_set.json` | 30-question evaluation dataset (v2.0). Categories: `policy_explanation`, `information_retrieval`, `comparison`, `conflict_detection`, `version_resolution`, `eligibility_analysis`, `fee_calculation`, `rag_based`, `out_of_scope`, `evidence_grounding`, `code_explanation`, `code_retrieval`, `dependency_understanding`, `bug_analysis`, `code_generation`, `refactoring`, `rag_based_code_doc`. Each entry has: `id`, `category`, `question`, `expected_sources`, `key_facts`, `min_facts`. |
| `evaluation/questions.json` | 25-question formal dataset. 9 categories: `factual`, `eligibility`, `policy`, `document_retrieval`, `numerical`, `comparison`, `multi_doc`, `contextual`, `unanswerable`. |
| `evaluation/week5_guardrail_tests.json` | 15 guardrail test cases covering: `out_of_scope` (Bitcoin, weather, country capitals), `empty_input`, `length_exceeded`, `supported_questions`, `evidence_grounding`. Each has `input`, `expected_blocked`, `expected_guardrail_status`. |
| `evaluation/evidence_eval_set.json` | Evidence-specific test cases for conflict detection, version resolution, and grounding validation. |
| `evaluation/run_eval.py` | Runs all questions in `eval_set.json` against all 4 Ollama models. Saves raw results to `results/raw_results.json`. Executes 116 total generations (29 questions × 4 models). Warms up each model before timing. |
| `evaluation/score.py` | Reads `results/raw_results.json`. Computes: accuracy (keyword matching), fact coverage, relevance (cosine similarity), groundedness (word overlap), hallucination/fabrication rates, code test-pass rate, latency percentiles (mean, median, P95), throughput, resident memory. Saves to `results/summary.json`. |
| `evaluation/rag_analysis.py` | Traces retrieval→generation for 5 case types (relevant retrieval, irrelevant retrieval, missed info, synthesis required, hallucination despite context). Generates report on Recall@3, MRR, retrieval failures. |
| `evaluation/code_rag_probe.py` | Indexes the repo's 37 source files (817 chunks) and runs 10 codebase questions through `llama3.2:latest` at `top_k=3` and `top_k=8`. Computes retrieval file recall, answer file recall, answer file precision. |
| `evaluation/run_guardrail_tests.py` | Automated test runner for `week5_guardrail_tests.json`. Hits `/ask` endpoint and validates `blocked`, `guardrail.input_check`, `guardrail.evidence_sufficient` fields. Reports pass/fail per case. |
| `evaluation/demo_guardrails.py` | Side-by-side demo: same questions sent with and without guardrail evaluation. Shows the difference in responses for out-of-scope, empty, and supported queries. |
| `evaluation/validate_dataset.py` | Schema validation for `eval_set.json` — checks required fields, category membership, `min_facts` ≤ `len(key_facts)`. |
| `evaluation/results/raw_results.json` | Output of `run_eval.py`. Per-question, per-model: answer text, matched facts, latency, token counts, Ollama metadata. |
| `evaluation/results/summary.json` | Output of `score.py`. Per-model aggregated metrics ready for the EvaluationDashboard component. |
| `evaluation/results/code_probe.json` | Output of `code_rag_probe.py`. Per-question correctness at k=3 and k=8. |
| `evaluation/results/guardrail_results.json` | Output of `run_guardrail_tests.py`. Per-test-case pass/fail with actual vs expected guardrail status. |

---

## 4. Services — Detailed Reference

### 4.1 Data Service :8003

Owns all documents. The only service that touches disk.

**Built-in documents** (from `backend/finance_kb/`):
- `loans.txt` — general loan concepts
- `loan_types.txt` — personal, home, car, student, business
- `loan_interest.txt` — fixed/variable rates, APR
- `loan_repayment.txt` — EMI, schedules, prepayment
- `loan_eligibility.txt` — credit score, income, documents
- `loan_risks.txt` — default consequences, lender rights

**API**

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Service liveness, document count, current version |
| GET | `/version` | Version counter (increments on every upload or delete) |
| GET | `/documents` | Full metadata + text preview for all documents |
| GET | `/chunks` | All chunks in stable positional order for FAISS indexing |
| POST | `/documents` | Upload `.txt`, `.md`, `.pdf`, `.docx` (max 5 MB each) |
| DELETE | `/documents/{name}` | Remove an uploaded document (built-ins are protected) |

**Version contract:** Every mutation increments `_version`. The Retrieval Service polls `GET /version` before every query and rebuilds its FAISS index if the version moved. This is the only coupling between the two services — no shared disk, no shared state.

---

### 4.2 Retrieval Service :8001

Owns the embedding model and FAISS index. Never reads disk directly.

**Embedding:** `sentence-transformers/all-MiniLM-L6-v2` — 384-dim vectors, baked into the Docker image at build time.

**Index:** `faiss.IndexFlatL2(384)` — exact L2 nearest-neighbour search.

**Index freshness:** `ensure_fresh_index()` runs before every `/retrieve` call. Fetches `GET /version` from Data Service. If version differs from `indexed_version`, calls `rebuild_index()` which pulls `/chunks`, re-embeds all text, and replaces the FAISS index atomically.

**API**

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness, vector count, indexed version |
| GET | `/index/info` | Vectors, dimension, index type |
| POST | `/reindex` | Force rebuild (called by App Service after upload) |
| POST | `/embed` | Text → 384-dim preview (first 8 + last 2 dims) |
| POST | `/retrieve` | Question → top-k chunks with L2 distances |

---

### 4.3 LLM Service :8002

The only service that knows Ollama exists.

**Default model:** `codellama:7b` (configurable via `OLLAMA_MODEL` env var)

**API**

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Checks Ollama reachability + model availability |
| GET | `/models` | Lists all pulled Ollama models |
| POST | `/generate` | Forwards prompt → Ollama, returns `{answer, model, runtime, duration_ms}` |

**Failure isolation:** If Ollama is unreachable, `/health` returns `degraded` (not 5xx). `/generate` raises a 502 with a clear message. The App Service catches this and returns `answer: null` with `ollama_error` set — the frontend still renders embedding, retrieval, and prompt steps.

---

### 4.4 App Service :8000

Orchestration layer. Holds no state and no model.

**Request flow for `POST /ask/debug`:**

```
1. check_input(question)              → reject_empty / reject_length / reject_scope / pass
2. classify_intent(question)          → LOAN / CODEBASE / OUT_OF_SCOPE
3a. [CODEBASE] get_repo_context()     → reads actual source files
3b. [LOAN] POST /embed                → 384-dim query embedding
4.  [LOAN] POST /retrieve             → top-k chunks + L2 distances
5.  check_evidence_sufficiency()      → abstain if top-1 L2 > 1.2
6.  build_rag_prompt(context, q)      → full prompt string
7.  POST /generate                    → Code Llama answer
8.  validate_grounding()              → groundedness score
9.  detect_conflicts()                → version conflicts across chunks
10. validate_output()                 → relevance, grounding, format checks
```

Every step is timed and returned in the `trace` array.

**API**

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Aggregate health of all 4 services |
| POST | `/ask` | Full RAG pipeline with intent routing + guardrails |
| POST | `/ask/debug` | Same as `/ask` plus full trace, embeddings, evidence |
| POST | `/ask/evidence` | Wide retrieval (top-10) for conflict/version analysis |
| POST | `/retrieve` | Retrieval only (delegates to Retrieval Service) |
| POST | `/generate` | Generation only (delegates to LLM Service) |
| GET | `/kb/info` | Knowledge base metadata |
| POST | `/kb/upload` | Upload → Data Service → trigger reindex |
| POST | `/kb/upload/with-metadata` | Upload with document_type, loan_type, version, effective_date |
| DELETE | `/kb/documents/{name}` | Delete → Data Service → trigger reindex |
| GET | `/playground/models` | Available Ollama models |
| POST | `/playground/ask` | Full debug pipeline with caller-specified model |

---

## 5. Guardrails

All logic in `services/app_service/guardrails.py`. Applied in `/ask` and `/ask/debug` before any retrieval or LLM call.

### Pipeline with guardrails

```
USER INPUT
    ↓
INPUT GUARDRAIL       ← rejects empty, too-long, out-of-scope
    ↓
INTENT CLASSIFICATION ← LOAN / CODEBASE / OUT_OF_SCOPE
    ↓
RAG RETRIEVAL         ← unchanged MiniLM + FAISS
    ↓
EVIDENCE CHECK        ← abstains when KB has nothing relevant (L2 > 1.2)
    ↓
LLM (Code Llama)      ← only called when evidence is sufficient
    ↓
OUTPUT VALIDATION     ← relevance, grounding, format
    ↓
RESPONSE
```

### Input guardrail (`check_input`)

| Check | Trigger | Status |
|---|---|---|
| Empty / whitespace | `question.strip() == ""` | `reject_empty` |
| Too long | Length > 1000 chars (env: `MAX_INPUT_LENGTH`) | `reject_length` |
| Out-of-scope keywords | bitcoin, crypto, weather, sports, recipe, capital city, … | `reject_scope` |
| General knowledge without loan context | "Write a Python sort", "Who won the election?" | `reject_scope` |

### Evidence guardrail (`check_evidence_sufficiency`)

```python
if not chunks or distances[0] > MAX_EVIDENCE_DISTANCE:
    # LLM is NOT called — return controlled abstention
```

- `MAX_EVIDENCE_DISTANCE = 1.2` (L2, configurable)
- `MIN_EVIDENCE_CHUNKS = 1`

### Output validation (`validate_output`)

| Check | Method | Pass condition |
|---|---|---|
| Relevance | Word overlap: question ∩ answer | ≥ 8% overlap |
| Grounding | `validate_grounding()` from evidence.py | Status ≠ "unsupported" |
| Unsupported claims | Numeric/factual claim detection | No fabricated numbers |
| Format | Length check | Not empty, not > 8000 chars |

### Response structure

Every `/ask` response includes `guardrail` and `output_validation` fields:

```json
{
  "question": "...",
  "answer": "...",
  "blocked": false,
  "guardrail": {
    "input_check": "pass",
    "evidence_sufficient": "pass",
    "action": "allow",
    "domain": "LOAN",
    "route": "LOAN_RAG",
    "llm_called": true
  },
  "output_validation": {
    "relevance": "pass",
    "grounding": "pass",
    "unsupported_claims": "pass",
    "format": "pass",
    "overall": "pass"
  }
}
```

Blocked response:
```json
{
  "blocked": true,
  "answer": null,
  "controlled_response": "I can only assist with questions related to loan information.",
  "guardrail": {
    "input_check": "reject_scope",
    "action": "rejected"
  }
}
```

### Without vs With guardrails

| Input | Without | With |
|---|---|---|
| "What is the price of Bitcoin?" | LLM answers from training data | `reject_scope` — no retrieval or LLM call |
| `""` | Empty embedding sent to FAISS | `reject_empty` — immediate rejection |
| 1500-char question | Accepted, large token usage | `reject_length` — rejected at input |
| "What is the HDFC Bank rate?" | LLM invents a rate | Evidence check fails (L2 > 1.2) — abstention |
| "What is an EMI?" | Grounded answer | Allow → grounded answer from `loan_repayment.txt` |

---

## 6. Model Evaluation

Four models evaluated over 29 questions under identical conditions (temperature=0, seed=42, max_tokens=512, retrieval replayed byte-identically).

### Models

| Model | Tag | Parameters | Resident RAM |
|---|---|---|---|
| Code Llama | `codellama:7b` | 7B | 5,797 MB |
| WizardLM 2 | `wizardlm2:7b` | 7B | 4,550 MB |
| Llama 3.2 | `llama3.2:latest` | 3B | 2,443 MB |
| Gemma | `gemma:2b` | 2B | 1,784 MB |

### Retrieval quality (identical for all models)

| Metric | Value |
|---|---|
| Recall@3 | 89.5% (17 / 19 questions with expected source) |
| MRR | 0.895 |
| Misses | S02 (two-intent car loan query), C04 (loan type factors) |

### Quality metrics

| Metric | codellama:7b | wizardlm2:7b | llama3.2 | gemma:2b |
|---|---|---|---|---|
| Accuracy | 94.7% | 94.7% | 89.5% | 73.7% |
| Fact coverage | 94.6% | 87.7% | 86.8% | 74.3% |
| Relevance (cosine) | 0.759 | 0.742 | **0.780** | 0.744 |
| Groundedness | 81.1% | 50.6% | **81.8%** | 75.9% |

### Hallucination

| Metric | codellama:7b | wizardlm2:7b | llama3.2 | gemma:2b |
|---|---|---|---|---|
| Fabrication rate ↓ | 60.0% | 80.0% | **0.0%** | **0.0%** |
| Proper refusals (out-of-KB) | 0 / 5 | 1 / 5 | **5 / 5** | **5 / 5** |

### Code generation (14 assertions per model)

| Model | Test-pass rate |
|---|---|
| llama3.2 | **71.4%** (10/14) |
| codellama | 50.0% (7/14) |
| wizardlm2 | 42.9% (6/14) |
| gemma | 35.7% (5/14) |

### Latency (CPU-only, no GPU)

| Model | Mean | Median | P95 | Throughput |
|---|---|---|---|---|
| gemma:2b | **4.3 s** | 3.6 s | 8.5 s | 16.0 tok/s |
| llama3.2 | 6.1 s | 6.3 s | 9.8 s | 12.7 tok/s |
| codellama | 20.5 s | 18.4 s | 39.1 s | 6.1 tok/s |
| wizardlm2 | 36.9 s | 32.1 s | 80.0 s | 6.3 tok/s |

### Recommendation

**Replace `codellama:7b` with `llama3.2:latest`.**

Moving codellama → llama3.2: −5.3 accuracy points, +3.3× speed, −3.4 GB RAM, 0% fabrication (was 60%), +21 pts code test-pass. Four of five measures improve simultaneously — this is not a trade-off, it is a strictly better operating point.

---

## 7. RAG Pipeline Analysis

Six real cases from the evaluation run.

### Case A — Good retrieval → correct answer
`loan_risks.txt` at rank 1, L2 0.201. All key facts matched. Groundedness 100%.

### Case B — Irrelevant retrieval → model-dependent outcome
"What is the capital city of Australia?" → 3 loan chunks, L2 1.794–1.871.
- codellama: "The capital city of Australia is Canberra." ✗ fabricated
- llama3.2: "This information is not available in my knowledge base." ✓ refused

**Finding:** FAISS always returns k chunks. There is no distance threshold — the retriever cannot abstain. Same bad retrieval, opposite model behaviours.

### Case C — Missed chunk → unrecoverable partial answer
Two-intent query: loan type for car + what to check. `loan_types.txt` not in top-3 because the embedding averages both intents. All models gave partial answers. No model can recover information the retriever never supplied.

### Case D — Synthesis required → correct
Simple vs compound interest. Context stated them separately; llama3.2 synthesised a comparison correctly. Key facts 3/3, groundedness 73%, relevance 0.850.

### Case E — Correct answer + hallucination
`loan_eligibility.txt` at rank 1, L2 0.189. wizardlm2 scored 5/5 key facts but added "W-2 forms", "Social Security Number" from US training data. Groundedness: 49%. **Accuracy metrics would mark this correct; only groundedness reveals the embellishment.**

### Case F — Specific financial figure fabricated
"What is the current RBI repo rate?" → codellama gave a specific percentage not in the KB. gemma refused correctly.

### Retrieval ceiling findings

| Root cause | Fix |
|---|---|
| Retriever cannot abstain | Add L2 distance threshold; pass empty context when nothing qualifies |
| Multi-intent queries miss chunks | Decompose into sub-queries, retrieve per intent, merge |
| Embellishment undetected | Show groundedness score in dashboard next to every answer |

---

## 8. Running the Project

### Option A — Local (no Docker)

**Prerequisites:** Python 3.10+, Node.js 18+, Ollama installed

```bash
# 1. Start Ollama (if not already running)
ollama serve
ollama pull codellama:7b

# 2. Install Python dependencies
cd backend
pip install -r requirements.txt
cd ..

# 3. Start all 4 backend services (opens 4 terminal windows)
start_services.bat

# 4. Start the frontend (separate terminal)
start_frontend.bat
```

Open **http://localhost:5173**

Services start on: `:8003` (data), `:8001` (retrieval — takes ~20s to load MiniLM), `:8002` (llm), `:8000` (app)

Health check: http://localhost:8000/health
API docs: http://localhost:8000/docs

### Option B — Docker Compose

**Prerequisites:** Docker Desktop running, ~8 GB free disk

```bash
# Build and start all 6 containers
docker compose up --build -d

# Pull Code Llama (once, ~3.8 GB)
docker compose exec ollama ollama pull codellama:7b

# Verify everything is healthy
docker compose ps
curl http://localhost:8000/health
```

Open **http://localhost:3000**

> To use a host Ollama instead of the container:
> ```bash
> docker compose up -d --scale ollama=0
> # Set OLLAMA_URL=http://host.docker.internal:11434 in llm-service environment
> ```

### Running Evaluation

```bash
# Week 4 — model evaluation
python evaluation/run_eval.py     # 116 generations across 4 models
python evaluation/score.py        # compute all metrics

# Week 5 — guardrail tests
python evaluation/validate_dataset.py    # validate eval_set.json schema
python evaluation/run_guardrail_tests.py # run 15 guardrail test cases
python evaluation/demo_guardrails.py     # without vs with demo

# RAG analysis
python evaluation/rag_analysis.py        # 5 pipeline analysis cases
python evaluation/code_rag_probe.py      # codebase RAG probe
```

Results written to `evaluation/results/`.

---

## 9. API Reference

### Core

```bash
# Full RAG pipeline
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the eligibility criteria for a home loan?"}'

# Full debug pipeline (all intermediate steps)
curl -X POST http://localhost:8000/ask/debug \
  -H "Content-Type: application/json" \
  -d '{"question": "What happens if I miss an EMI payment?"}'

# Aggregate health
curl http://localhost:8000/health
```

### Knowledge Base

```bash
# Upload a document
curl -X POST http://localhost:8000/kb/upload \
  -F "files=@my_policy.pdf"

# Upload with metadata
curl -X POST http://localhost:8000/kb/upload/with-metadata \
  -F "files=@policy_v2.pdf" \
  -F "document_type=policy" \
  -F "loan_type=home" \
  -F "version=2.0" \
  -F "effective_date=2024-01-01"

# Delete an uploaded document
curl -X DELETE http://localhost:8000/kb/documents/policy_v2.txt

# KB metadata
curl http://localhost:8000/kb/info
```

### Model Playground

```bash
# List available models
curl http://localhost:8000/playground/models

# Ask with a specific model
curl -X POST http://localhost:8000/playground/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is compound interest?", "model": "llama3.2:latest"}'
```

---

## 10. Knowledge Base

### Built-in documents (6 files in `backend/finance_kb/`)

| File | Covers |
|---|---|
| `loans.txt` | Loan definition, principal, interest, collateral, default, borrower/lender basics |
| `loan_types.txt` | Personal, home, car, student, business loans. Secured vs unsecured. Selection factors. |
| `loan_interest.txt` | Fixed vs variable rates. Simple vs compound interest. APR. Rate comparison. |
| `loan_repayment.txt` | EMI calculation, repayment schedules, prepayment, part-payment, moratorium, missed payment consequences |
| `loan_eligibility.txt` | Credit score thresholds, income requirements, debt-to-income ratio, required documents |
| `loan_risks.txt` | Over-borrowing risk, interest rate risk, default consequences, asset repossession, lender rights |

### Chunking

All text is split by `services/common/chunking.py`:
- **Chunk size:** 300 characters
- **Overlap:** 50 characters
- **Index:** `faiss.IndexFlatL2(384)` — currently 87 vectors (6 built-in + 3 uploaded documents)

### Adding documents

Upload `.txt`, `.md`, `.pdf`, or `.docx` through the Knowledge Base tab in the dashboard or via `POST /kb/upload`. The FAISS index rebuilds automatically. Uploaded documents persist in `backend/uploaded_kb/` with `.meta.json` sidecars.


---

## 11. Week 4 Formal Evaluation Report (Exercises 2–4)

*Source: `evaluation/Week4_Model_Evaluation_Ex2-4.docx` — extracted and merged here.*

### Summary

Four locally-hosted language models were evaluated on the same RAG application using 29 tasks, the same prompts, the same knowledge base, and the same decoding settings. 116 generations recorded in total.

**Headline result:** The most accurate model was the least trustworthy. `codellama:7b` scored highest on accuracy (94.7%) yet fabricated answers to 60% of questions its knowledge base could not support — including inventing a Reserve Bank of India repo rate. `llama3.2:3b` scored 5.3 points lower, fabricated nothing, ran 3.3× faster, and used 2.4× less memory.

---

### Evaluation Setup

| Item | Value |
|---|---|
| Application | RAG pipeline: retrieval → prompt assembly → LLM generation |
| Knowledge base | 6 loan documents, FAISS IndexFlatL2, 384-dimensional |
| Models compared | codellama:7b, wizardlm2:7b, llama3.2:3b, gemma:2b |
| Tasks per model | 29 |
| Total generations | 116 |
| Decoding settings | temperature=0, seed=42, num_predict=512, top_p=1.0 |
| Hardware | Single machine, CPU only, models run sequentially |

---

### Exercise 2 — The Evaluation Dataset

**Composition — 29 tasks across 5 categories**

| Category | Tasks | What it tests |
|---|---|---|
| `factual_retrieval` | 10 | Single-document lookup — answer sits in one KB document |
| `multi_doc_synthesis` | 4 | Answer requires combining two or more documents |
| `conceptual` | 5 | Explanation or comparison of a concept in the KB |
| `out_of_kb` | 5 | Deliberately unanswerable — assistant must refuse, not invent |
| `code_generation` | 5 | In-domain loan mathematics, executed against unit tests |

**Example tasks**

| ID | Category | Task |
|---|---|---|
| F01 | factual_retrieval | What are the main parts of a loan? |
| F09 | factual_retrieval | What is a debt-to-income ratio and why do lenders calculate it? |
| S01 | multi_doc_synthesis | Compare secured and unsecured loans, including how default is handled for each. |
| C02 | conceptual | Explain the difference between simple interest and compound interest. |
| H02 | out_of_kb | What is the current repo rate set by the Reserve Bank of India? |
| H05 | out_of_kb | Based on my salary of 50,000 rupees, exactly how much home loan will I be approved for? |
| G01 | code_generation | Write a Python function `emi(principal, annual_rate_percent, months)` that returns the monthly EMI using the standard amortization formula. |

**How each task carries its own answer key**

- `expected_sources` — which KB document should be retrieved (measures retrieval quality)
- `key_facts` + `min_facts` — facts required for a correct answer; alternative phrasings accepted
- `expect_refusal` — marks the 5 out-of-KB traps where the correct behaviour is to decline
- `tests` — for the 5 coding tasks, 14 executable assertions with known-correct values

Source file: `evaluation/eval_set.json`

**Why out-of-KB traps matter:** Tasks H01–H05 ask questions the KB cannot answer (e.g. current RBI repo rate, capital city of Australia). The prompt instructs the model to reply "This information is not available in my knowledge base." These tasks convert hallucination from a verbal description into a counted number — and produced the single most important finding.

---

### Exercise 3 — Quantitative Evaluation

**Metric definitions**

| Metric | Calculation |
|---|---|
| Accuracy | Matched facts ≥ min_facts = correct. Accuracy = correct answers ÷ knowledge questions. Case-insensitive substring on whitespace-normalised text. |
| Relevance | Cosine similarity between MiniLM embedding of answer and question. Mean over knowledge questions. |
| Retrieval Recall@3 | Questions where ≥1 expected source is in top-3 chunks. |
| MRR | Mean of 1 ÷ rank of first expected source. |
| Hallucination | Out-of-KB answers classified as: `proper_refusal` / `soft_decline` / `fabricated`. Fabrication rate = fabricated ÷ total out-of-KB. |
| Groundedness | Share of answer's content words (stopwords removed) that also appear in retrieved context. |
| Test-pass rate | Fenced code block extracted, executed in subprocess. Assertions passed ÷ assertions run (14 total). |
| Response latency | Wall-clock ms around HTTP call, model warmed up before timing. Mean, median, P95. |
| Token usage | Ollama's own counters: `prompt_eval_count` (input), `eval_count` (output). Throughput = output tokens ÷ eval duration. |
| CPU/GPU/memory | RSS and CPU% sampled at 4 Hz across `ollama.exe` + `llama-server.exe`. Model size and VRAM from `GET /api/ps`. |

All metric calculations implemented in `evaluation/score.py`.

**What was held constant:** Retrieval executed once per question, cached results replayed byte-identically to every model. All four received the exact same context chunks.

**Retrieval quality (identical for all models)**

| Metric | Value | Interpretation |
|---|---|---|
| Recall@3 | 89.5% | Expected document in top 3 for 17 of 19 questions |
| MRR | 0.895 | Whenever the right document was found, it was ranked first |

**Quality results**

| Metric | codellama:7b | wizardlm2:7b | llama3.2:3b | gemma:2b |
|---|---|---|---|---|
| Accuracy | 94.7% | 94.7% | 89.5% | 73.7% |
| Correct / total | 18/19 | 18/19 | 17/19 | 14/19 |
| Mean fact coverage | 94.6% | 87.7% | 86.8% | 74.3% |
| Relevance | 0.759 | 0.742 | **0.780** | 0.744 |
| Groundedness | 81.1% | 50.6% | **81.8%** | 75.9% |
| Refused an answerable question | 0 | 0 | 1 | 3 |

**Hallucination results**

| Metric | codellama:7b | wizardlm2:7b | llama3.2:3b | gemma:2b |
|---|---|---|---|---|
| Out-of-KB questions refused | 0/5 | 1/5 | **5/5** | **5/5** |
| Soft declines | 2 | 0 | 0 | 0 |
| Outright fabrications | 3 | 4 | **0** | **0** |
| Fabrication rate ↓ | 60.0% | 80.0% | **0.0%** | **0.0%** |
| Refusal-failure rate ↓ | 100.0% | 80.0% | **0.0%** | **0.0%** |

**Code generation results (14 assertions executed per model)**

| Metric | codellama:7b | wizardlm2:7b | llama3.2:3b | gemma:2b |
|---|---|---|---|---|
| Code block produced | 5/5 | 5/5 | 5/5 | 5/5 |
| Assertions passed | 7/14 | 6/14 | **10/14** | 5/14 |
| Test-pass rate | 50.0% | 42.9% | **71.4%** | 35.7% |
| Tasks fully passing | 2/5 | 2/5 | **3/5** | 1/5 |

**Performance results**

| Metric | codellama:7b | wizardlm2:7b | llama3.2:3b | gemma:2b |
|---|---|---|---|---|
| Mean latency | 20.5 s | 36.9 s | 6.1 s | **4.2 s** |
| Median latency | 18.4 s | 32.1 s | 6.3 s | **3.6 s** |
| 95th percentile latency | 39.1 s | 80.0 s | 9.8 s | **8.5 s** |
| Throughput | 6.05 tok/s | 6.33 tok/s | 12.67 tok/s | **16.01 tok/s** |
| Total input tokens | 8,157 | 8,447 | 6,920 | 7,209 |
| Total output tokens | 2,796 | 5,974 | 1,571 | 1,295 |
| Mean output tokens/answer | 96.4 | 206.0 | 54.2 | **44.7** |

**Resource consumption**

| Metric | codellama:7b | wizardlm2:7b | llama3.2:3b | gemma:2b |
|---|---|---|---|---|
| Resident model size | 5,797 MB | 4,550 MB | 2,443 MB | **1,784 MB** |
| Mean CPU during generation | 959% | 971% | 890% | **851%** |
| VRAM used | 0 MB | 0 MB | 0 MB | 0 MB |
| GPU share | 0% | 0% | 0% | 0% |

> CPU% summed across cores. 959% ≈ 9.6 cores saturated. No GPU offload — Ollama reported 0 MB VRAM for all models.

---

### Exercise 4 — Analysis

**Direct answers to each question**

| Question | Answer | Evidence |
|---|---|---|
| Which model provides better accuracy? | codellama:7b and wizardlm2:7b (tied) | 94.7% each |
| Which model produces fewer hallucinations? | llama3.2:3b and gemma:2b (tied) | 0% fabrication; both refused all 5 out-of-KB |
| Which model gives better retrieval-based responses? | llama3.2:3b | 81.8% groundedness, 0.780 relevance |
| Which model generates code with higher test-pass rate? | llama3.2:3b | 71.4%, 10 of 14 assertions |
| Which model has lower response latency? | gemma:2b | 4.2 s mean |
| Which model requires fewer computational resources? | gemma:2b | 1,784 MB resident |
| Is the most accurate model also the most efficient? | No | codellama is 4.8× slower and 3.2× larger than gemma |

**Quality–latency–resource trade-off**

| Model | Accuracy | Mean latency | Resident | Accuracy/second | Accuracy/GB |
|---|---|---|---|---|---|
| codellama:7b | 94.7% | 20.5 s | 5,797 MB | 4.62 | 16.74 |
| wizardlm2:7b | 94.7% | 36.9 s | 4,550 MB | 2.57 | 21.32 |
| llama3.2:3b | 89.5% | 6.1 s | 2,443 MB | 14.63 | 37.50 |
| gemma:2b | 73.7% | 4.2 s | 1,784 MB | 17.35 | 42.29 |

**Five findings**

1. **Accuracy and safety point to different models.** codellama and wizardlm2 tie at 94.7% but fabricate 60% and 80% of out-of-KB answers. codellama replied "The current repo rate set by the RBI is 6.25%" — a figure not in the KB. llama3.2, with identical context, replied "This information is not available in my knowledge base." For a lending assistant, an invented interest rate is worse than a missing answer.

2. **The RAG prompt does not enforce grounding.** All four models received byte-identical context and the same instruction. Two ignored it. Grounding is a property of the model's instruction-following, not of the prompt. Retrieval gives an honest model something to work with; it cannot make a dishonest model honest.

3. **Parameter count does not predict quality.** The 3B llama3.2 beat both 7B models on relevance, groundedness, code test-pass rate, and every performance metric, using 42% of codellama's memory. The code-specialised codellama passed 7/14 assertions; the general-purpose 3B model passed 10.

4. **Verbosity costs latency without buying grounding.** wizardlm2 produced 206 output tokens per answer vs llama3.2's 54 — 3.8× more — for 5.3 extra accuracy points and the worst groundedness (50.6%). P95 latency of 80 s makes it unusable interactively.

5. **The trade-off is not where expected.** Moving codellama → llama3.2: −5.3 accuracy points, +3.3× speed, −3.4 GB RAM, 0% fabrication (was 60%), +21 pts code test-pass. Four of five measures improve — this is a strictly better operating point. The genuine trade-off is only at the bottom: gemma saves 1.9 s at the cost of 15.8 accuracy points and over-refusal on answerable questions.

**Recommendation:** Deploy `llama3.2:3b`, replace `codellama:7b` as the application default. llama3.2 is the only model that is simultaneously accurate (89.5%), safe (0% fabrication), grounded (81.8%), best at code (71.4% test-pass), and fast enough for interactive use (6.1 s mean, 9.8 s P95) within 2.4 GB of RAM.

**Measurement caveats**

- CPU% is summed across cores — all models sit in a narrow 851–971% band, so it does not discriminate.
- No GPU offload occurred. All latency figures are CPU-bound.
- Accuracy is keyword-based — rewards stating required facts, not fluency.
- Code tasks use a separate fixed template (not the RAG prompt) because the RAG prompt would cause every model to refuse every coding task.

**Reproducing these results**

| Step | Command | Produces |
|---|---|---|
| 1. Execute | `python evaluation/run_eval.py` | `results/raw_results.json` — all 116 generations |
| 2. Score | `python evaluation/score.py` | `results/summary.json` — every metric |
