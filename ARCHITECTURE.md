# Architecture — Loan Knowledge Assistance

This document covers **Exercise 4 (services, APIs, orchestration)** and
**Exercise 5 (Docker)**. Exercises 1–3 are the single-process backend in
[`backend/`](backend/), which is kept intact as the earlier stage of the same
application.

---

## 1. Why these four services

The monolith in `backend/main.py` already had the four *responsibilities*
separated as functions. Exercise 4 asks which of them are genuinely separable —
the test being whether each one owns distinct state and has a distinct reason to
change.

| Service | Port | Owns | Changes when… |
|---|---|---|---|
| **Application / Orchestration** | 8000 | Nothing but request sequencing | the pipeline order or prompt changes |
| **Retrieval / RAG** | 8001 | Embedding model + FAISS index | the model, dimension, or search strategy changes |
| **LLM** | 8002 | The Ollama client | the runtime or model changes |
| **Data** | 8003 | Documents on disk, chunking, uploads | the document formats or chunk parameters change |

Three consequences make the split real rather than cosmetic:

1. **Only the Data Service touches the filesystem.** The Retrieval Service has
   no volume mount — it obtains chunks over HTTP.
2. **Only the Retrieval Service loads a model.** Its image carries torch and the
   baked-in MiniLM weights; the other three are ~271–293 MB slim Python images.
   Restarting the orchestrator does not reload a model.
3. **Only the LLM Service knows Ollama exists.** Swapping Code Llama for another
   runtime means editing one file.

The Application Service deliberately holds *no* state. That is what makes it the
only service the browser needs to reach.

---

## 2. The APIs

### Data Service — `:8003`

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness, document count |
| GET | `/version` | monotonic counter, bumped on every mutation |
| GET | `/documents` | metadata + full text for the dashboard |
| GET | `/chunks` | every chunk in stable order, for indexing |
| POST | `/documents` | multipart upload (`.txt`, `.md`, `.pdf`, `.docx`) |
| DELETE | `/documents/{filename}` | remove an uploaded document |

`/chunks` returns chunks in a fixed order, so index *i* in that list is FAISS row
*i* in the Retrieval Service. That positional contract is the only coupling
between the two services.

### Retrieval Service — `:8001`

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness, vector count, indexed data version |
| GET | `/index/info` | vectors, dimension, index type |
| POST | `/reindex` | pull `/chunks` from Data and rebuild FAISS |
| POST | `/embed` | text → 384-dim vector preview |
| POST | `/retrieve` | question → top-k chunks, sources, L2 distances |

### LLM Service — `:8002`

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | whether Ollama is reachable and the model is pulled |
| GET | `/models` | models available in the runtime |
| POST | `/generate` | prompt → answer, model, duration |

### Application Service — `:8000` (public)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | aggregate status of all four services |
| POST | `/retrieve` | stage 1 only |
| POST | `/generate` | stage 2 only |
| POST | `/ask` | orchestrated question → answer |
| POST | `/ask/debug` | full pipeline internals + orchestration trace |
| GET | `/kb/info` | knowledge-base metadata |
| POST | `/kb/upload` | upload → Data Service → trigger reindex |
| DELETE | `/kb/documents/{filename}` | delete → Data Service → trigger reindex |

This public contract is **identical to the single-process backend**, so the
React dashboard runs against either deployment without modification.

---

## 3. Orchestrating one request

`POST /ask/debug` with `{"question": "..."}`:

```
Browser
   │
   ▼
Application Service :8000
   │
   ├─ 1. POST retrieval-service:8001/embed      question → 384-dim vector preview
   ├─ 2. POST retrieval-service:8001/retrieve   vector → top-3 chunks + L2 distances
   │        └─ retrieval checks data-service:8003/version, re-indexes if stale
   ├─ 3. (local) join chunks with "---", build the RAG prompt
   └─ 4. POST llm-service:8002/generate         prompt → Code Llama answer
              └─ ollama:11434/api/generate
   │
   ▼
Response: embedding preview, chunks, distances, context, prompt, answer, trace
```

Every hop is timed and returned in a `trace` array. Measured on this machine:

| # | step | service | duration |
|---|---|---|---|
| 1 | `embed` | Retrieval Service | 28.2 ms |
| 2 | `retrieve` | Retrieval Service | 41.9 ms |
| 3 | `build_prompt` | app-service (local) | 0.0 ms |
| 4 | `generate` | LLM Service | 9,521.8 ms |

The same question through the **containerised** stack, entering via nginx on
port 3000:

| # | step | endpoint | duration |
|---|---|---|---|
| 1 | `embed` | `http://retrieval-service:8001/embed` | 39.2 ms |
| 2 | `retrieve` | `http://retrieval-service:8001/retrieve` | 12.1 ms |
| 3 | `build_prompt` | local | 0.0 ms |
| 4 | `generate` | `http://llm-service:8002/generate` | 37,856.6 ms |

Retrieval returned identical L2 distances in both deployments
(`0.576, 0.777, 0.822`), which is the payoff from baking fixed model weights
into the image. Generation is slower in the container because Ollama runs
CPU-only there, against a GPU-assisted host runtime.

The dashboard renders this table live under **Service Architecture**, so the
orchestration shown is measured rather than drawn.

### Keeping the index fresh without shared state

The Data and Retrieval services share no disk. When a document is uploaded:

1. App Service forwards the file to Data Service, which increments its `version`.
2. App Service calls Retrieval `POST /reindex` — the fast path.
3. Independently, Retrieval checks `GET /version` before every query. If the
   version moved, it rebuilds before answering.

Step 3 means the system self-heals even when a document is uploaded *directly*
to the Data Service, bypassing the orchestrator entirely — verified in testing.

### Failure isolation

With the LLM Service stopped, `/ask/debug` still returns the query embedding,
retrieved chunks, context, and prompt, with `answer: null` and the trace marking
`generate` as `unreachable`. `/health` reports `degraded` and names the one
failed service. The RAG pipeline is not coupled to generation being available.

---

## 4. Docker

Six containers on one bridge network (`rag-net`), defined in
[`docker-compose.yml`](docker-compose.yml).

```
browser :3000
   │
   ▼
frontend (nginx) ──/api/*──► app-service:8000
                                 ├──► retrieval-service:8001 ──► data-service:8003
                                 └──► llm-service:8002 ──► ollama:11434
```

Services address each other by **compose service name**, not by IP or
`localhost` — `http://data-service:8003` resolves on the bridge network. Those
URLs are injected as environment variables, so the same image runs unchanged
locally (pointing at `127.0.0.1`) or in compose.

### Notable build decisions

- **CPU-only torch** in the Retrieval image, via the PyTorch CPU wheel index —
  the CUDA build would add several GB for no benefit on this machine.
- **The MiniLM model is baked into the image** at build time. Container start
  needs no network, and every run embeds with identical weights.
- **Two named volumes**: `kb-uploads` so uploaded documents outlive the
  container, and `ollama-models` so the 3.8 GB Code Llama pull happens once.
- **Healthchecks with `depends_on: condition: service_healthy`**, because the
  Retrieval Service needs ~90 s to load its model and the App Service must not
  accept traffic before its dependencies are ready.
- **Ollama publishes on host port 11435**, not 11434, so the container does not
  clash with an Ollama already running on the host.

Resulting image sizes show the separation paying off — only one service carries
the ML stack:

| Image | Size |
|---|---|
| `retrieval-service` | 2.29 GB |
| `data-service` | 293 MB |
| `app-service` | 271 MB |
| `llm-service` | 271 MB |
| `frontend` | 73.9 MB |

Note that the containerised stack has its own `kb-uploads` volume, so documents
uploaded to the local (non-Docker) deployment do not appear in the container
deployment. That is correct isolation, not a bug.

### Running it

```bash
docker compose up --build -d
docker compose exec ollama ollama pull codellama:7b    # once, ~3.8 GB

docker compose ps
curl http://localhost:8000/health
```

Then open **http://localhost:3000**.

To use a host Ollama instead of the container, set
`OLLAMA_URL=http://host.docker.internal:11434` on `llm-service` and start with
`--scale ollama=0`.

### Running without Docker

`start_services.bat` launches all four services in separate windows against a
host Ollama; `start_frontend.bat` runs the Vite dev server on :5173.

---

## 5. The complete journey

```
User → Frontend → App Service → Retrieval Service → FAISS → relevant chunks
     → context + question → RAG prompt → LLM Service → Ollama → Code Llama → Response
```

Every arrow above is an HTTP call across a process boundary, observable in the
`trace` of any `/ask/debug` response.
