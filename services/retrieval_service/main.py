"""
Retrieval / RAG Service — port 8001

Owns the embedding model (MiniLM) and the FAISS index, and nothing else. It
never reads the filesystem for documents: it pulls chunks from the Data Service
over HTTP and embeds them.

Because it holds torch + sentence-transformers + faiss, this is the heavy
service — separating it means the other three containers stay small and can be
restarted or scaled without reloading a model.

Endpoints
    GET  /health        liveness + index state
    GET  /index/info    vectors, dimension, index type, indexed data version
    POST /reindex       pull /chunks from Data Service and rebuild FAISS
    POST /embed         embed a single text, return the preview + dimension
    POST /retrieve      question -> top-k chunks, sources, L2 distances
"""

import os
import threading

import numpy as np
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

SERVICE_NAME = "retrieval-service"

DATA_SERVICE_URL = os.environ.get("DATA_SERVICE_URL", "http://127.0.0.1:8003")
EMBEDDING_MODEL_NAME = os.environ.get(
    "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
EMBEDDING_DIMENSION = 384
FAISS_INDEX_TYPE = "IndexFlatL2"
DEFAULT_TOP_K = 3

app = FastAPI(title="Retrieval Service", version="1.0.0")

_lock = threading.RLock()

print(f"[{SERVICE_NAME}] Loading embedding model (MiniLM)...")
from sentence_transformers import SentenceTransformer  # noqa: E402
import faiss  # noqa: E402

embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
print(f"[{SERVICE_NAME}] Model ready.")

faiss_index = faiss.IndexFlatL2(EMBEDDING_DIMENSION)
chunk_metadata: list[dict] = []
indexed_version: int | None = None  # data version currently reflected in FAISS


class QuestionRequest(BaseModel):
    question: str
    top_k: int = DEFAULT_TOP_K


class EmbedRequest(BaseModel):
    text: str


def _fetch_chunks() -> tuple[list[dict], int]:
    res = requests.get(f"{DATA_SERVICE_URL}/chunks", timeout=30)
    res.raise_for_status()
    payload = res.json()
    return payload["chunks"], payload["version"]


def _fetch_version() -> int:
    res = requests.get(f"{DATA_SERVICE_URL}/version", timeout=5)
    res.raise_for_status()
    return res.json()["version"]


def rebuild_index() -> dict:
    """Pull every chunk from the Data Service and rebuild FAISS from scratch."""
    global faiss_index, chunk_metadata, indexed_version

    chunks, version = _fetch_chunks()

    with _lock:
        index = faiss.IndexFlatL2(EMBEDDING_DIMENSION)
        if chunks:
            embeddings = embedding_model.encode([c["text"] for c in chunks])
            index.add(np.array(embeddings, dtype=np.float32))

        faiss_index = index
        chunk_metadata = chunks
        indexed_version = version

        print(
            f"[{SERVICE_NAME}] Indexed {faiss_index.ntotal} vectors "
            f"({EMBEDDING_DIMENSION}-dim, {FAISS_INDEX_TYPE}) at data version {version}."
        )
        return {
            "vectors": faiss_index.ntotal,
            "dimension": EMBEDDING_DIMENSION,
            "index_type": FAISS_INDEX_TYPE,
            "data_version": version,
        }


def ensure_fresh_index() -> None:
    """
    Re-index if the Data Service has changed since we last built.

    This is what keeps an upload visible to retrieval without any shared state
    between the two services — one cheap HTTP call per query.
    """
    try:
        current = _fetch_version()
    except requests.RequestException as exc:
        with _lock:
            if indexed_version is None:
                raise HTTPException(
                    status_code=503,
                    detail=f"Data Service unreachable and no index has been built yet: {exc}",
                )
        return  # keep serving the existing index if Data is briefly down

    if current != indexed_version:
        try:
            rebuild_index()
        except requests.RequestException as exc:
            raise HTTPException(
                status_code=503, detail=f"Could not rebuild index from Data Service: {exc}"
            )


@app.on_event("startup")
def startup():
    """Build the index at boot; tolerate the Data Service not being up yet."""
    try:
        rebuild_index()
    except Exception as exc:
        print(f"[{SERVICE_NAME}] Deferred initial index build: {exc}")


@app.get("/")
def root():
    return {"service": SERVICE_NAME, "message": "Retrieval Service is running."}


@app.get("/health")
def health():
    with _lock:
        return {
            "service": SERVICE_NAME,
            "status": "ok",
            "vectors": faiss_index.ntotal,
            "dimension": EMBEDDING_DIMENSION,
            "index_type": FAISS_INDEX_TYPE,
            "embedding_model": EMBEDDING_MODEL_NAME,
            "indexed_version": indexed_version,
        }


@app.get("/index/info")
def index_info():
    with _lock:
        return {
            "vectors": faiss_index.ntotal,
            "dimension": EMBEDDING_DIMENSION,
            "index_type": FAISS_INDEX_TYPE,
            "indexed_version": indexed_version,
            "chunks": len(chunk_metadata),
        }


@app.post("/reindex")
def reindex():
    """Force a rebuild — called by the App Service after an upload or delete."""
    try:
        return rebuild_index()
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail=f"Data Service unreachable: {exc}")


@app.post("/embed")
def embed(data: EmbedRequest):
    """Embed one text and return the first 8 + last 2 dimensions as a preview."""
    vec = embedding_model.encode([data.text])[0]
    preview = list(vec[:8]) + list(vec[-2:])
    return {
        "preview": [round(float(v), 4) for v in preview],
        "dimension": EMBEDDING_DIMENSION,
        "model": EMBEDDING_MODEL_NAME,
    }


@app.post("/retrieve")
def retrieve(data: QuestionRequest):
    """Question -> query embedding -> FAISS L2 search -> top-k chunks."""
    ensure_fresh_index()

    with _lock:
        if faiss_index.ntotal == 0:
            return {
                "chunks": [],
                "sources": [],
                "distances": [],
                "indexed_version": indexed_version,
            }

        question_embedding = embedding_model.encode([data.question])
        k = min(max(data.top_k, 1), faiss_index.ntotal)
        distances, indices = faiss_index.search(
            np.array(question_embedding, dtype=np.float32), k
        )

        chunks = []
        sources = []
        raw_distances = []
        for i, idx in enumerate(indices[0]):
            if idx < 0:
                continue
            meta = chunk_metadata[idx]
            chunk_out = {
                "text": meta["text"],
                "source": meta["source"],
                "chunk_id": meta.get("id", int(idx)),
                # pass through metadata fields if present
                "document_type": meta.get("document_type", "general"),
                "loan_type": meta.get("loan_type", "general"),
                "version": meta.get("version", "1.0"),
                "effective_date": meta.get("effective_date"),
            }
            chunks.append(chunk_out)
            sources.append(meta["source"])
            raw_distances.append(float(distances[0][i]))

        return {
            "chunks": chunks,
            "sources": list(dict.fromkeys(sources)),
            "distances": raw_distances,
            "indexed_version": indexed_version,
        }
