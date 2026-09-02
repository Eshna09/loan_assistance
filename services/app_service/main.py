"""
Application / Orchestration Service — port 8000

The only service the browser talks to. It owns no model, no index, and no
documents — its job is to sequence calls to the other three services and to
assemble the RAG prompt.

Orchestration of one /ask/debug request:

    1. Retrieval Service   POST /embed      question -> vector preview
    2. Retrieval Service   POST /retrieve   vector  -> top-3 chunks + distances
    3. App Service         (local)          chunks  -> context -> RAG prompt
    4. LLM Service         POST /generate   prompt  -> Code Llama answer

Every hop is timed and returned in a `trace`, so the dashboard can show the
real service-to-service call graph rather than a drawing of one.

The public contract is unchanged from the single-process backend, so the
frontend works against either deployment.
"""

import os
import time
from typing import List

import requests
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from services.common.prompts import CONTEXT_SEPARATOR, build_rag_prompt
from services.app_service.evidence import (
    EVIDENCE_TOP_K,
    build_evidence,
    detect_conflicts,
    resolve_version,
    validate_grounding,
    determine_evidence_status,
)

SERVICE_NAME = "app-service"

DATA_SERVICE_URL = os.environ.get("DATA_SERVICE_URL", "http://127.0.0.1:8003")
RETRIEVAL_SERVICE_URL = os.environ.get("RETRIEVAL_SERVICE_URL", "http://127.0.0.1:8001")
LLM_SERVICE_URL = os.environ.get("LLM_SERVICE_URL", "http://127.0.0.1:8002")

EMBEDDING_DIMENSION = 384
DEFAULT_TOP_K = 3

app = FastAPI(title="Loan Knowledge Assistance API (Orchestrator)", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
    ).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QuestionRequest(BaseModel):
    question: str


class PromptRequest(BaseModel):
    prompt: str


# ── Service-call helper ──────────────────────────────────────────────────────
class Trace:
    """Records each downstream service call so the response can show the flow."""

    def __init__(self):
        self.steps: list[dict] = []

    def record(self, step: str, service: str, endpoint: str, ms: float, status: str):
        self.steps.append({
            "step": step,
            "service": service,
            "endpoint": endpoint,
            "duration_ms": round(ms, 1),
            "status": status,
        })


def call_service(
    method: str,
    url: str,
    *,
    service: str,
    step: str,
    trace: Trace | None = None,
    timeout: int = 30,
    **kwargs,
):
    """
    Make one downstream call, timing it and normalising failures.

    A downstream 4xx/5xx is re-raised with its own detail intact so the browser
    sees the real cause rather than a generic gateway error.
    """
    started = time.perf_counter()
    try:
        res = requests.request(method, url, timeout=timeout, **kwargs)
    except requests.RequestException as exc:
        elapsed = (time.perf_counter() - started) * 1000
        if trace:
            trace.record(step, service, url, elapsed, "unreachable")
        raise HTTPException(status_code=503, detail=f"{service} is unreachable: {exc}")

    elapsed = (time.perf_counter() - started) * 1000
    if trace:
        trace.record(step, service, url, elapsed, "ok" if res.ok else f"http_{res.status_code}")

    if not res.ok:
        detail = res.text
        try:
            body = res.json()
            detail = body.get("detail", detail)
        except ValueError:
            pass
        raise HTTPException(status_code=res.status_code, detail=f"{service}: {detail}")

    return res.json()


# ── Health / discovery ───────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"service": SERVICE_NAME, "message": "Loan Knowledge Assistance API is running."}


@app.get("/health")
def health():
    """Aggregate health of the whole system — one call, four services."""
    services = {
        "app-service": {"status": "ok", "url": "self", "role": "orchestration"},
    }
    targets = [
        ("data-service", f"{DATA_SERVICE_URL}/health", "documents, chunking, uploads"),
        ("retrieval-service", f"{RETRIEVAL_SERVICE_URL}/health", "embeddings + FAISS search"),
        ("llm-service", f"{LLM_SERVICE_URL}/health", "Ollama / Code Llama inference"),
    ]

    for name, url, role in targets:
        started = time.perf_counter()
        try:
            res = requests.get(url, timeout=5)
            res.raise_for_status()
            body = res.json()
            services[name] = {
                **body,
                "url": url,
                "role": role,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        except requests.RequestException as exc:
            services[name] = {
                "service": name,
                "status": "unreachable",
                "url": url,
                "role": role,
                "error": str(exc),
            }

    overall = "ok" if all(s.get("status") == "ok" for s in services.values()) else "degraded"
    return {"status": overall, "services": services}


# ── Core pipeline endpoints ──────────────────────────────────────────────────
@app.post("/retrieve")
def retrieve_service(data: QuestionRequest):
    """Stage 1 only — delegate to the Retrieval Service."""
    result = call_service(
        "POST",
        f"{RETRIEVAL_SERVICE_URL}/retrieve",
        service="Retrieval Service",
        step="retrieve",
        json={"question": data.question, "top_k": DEFAULT_TOP_K},
    )
    return {
        "context_chunks": [c["text"] for c in result["chunks"]],
        "sources": result["sources"],
    }


@app.post("/generate")
def llm_service(data: PromptRequest):
    """Stage 2 only — delegate to the LLM Service."""
    result = call_service(
        "POST",
        f"{LLM_SERVICE_URL}/generate",
        service="LLM Service",
        step="generate",
        json={"prompt": data.prompt},
        timeout=310,
    )
    return {"answer": result["answer"]}


@app.post("/ask")
def application_service(data: QuestionRequest):
    """Orchestrate retrieval + generation and return the final answer."""
    trace = Trace()

    retrieval = call_service(
        "POST",
        f"{RETRIEVAL_SERVICE_URL}/retrieve",
        service="Retrieval Service",
        step="retrieve",
        trace=trace,
        json={"question": data.question, "top_k": DEFAULT_TOP_K},
    )

    context = "\n".join(c["text"] for c in retrieval["chunks"])
    prompt = build_rag_prompt(context, data.question)

    answer = None
    llm_error = None
    try:
        generation = call_service(
            "POST",
            f"{LLM_SERVICE_URL}/generate",
            service="LLM Service",
            step="generate",
            trace=trace,
            json={"prompt": prompt},
            timeout=310,
        )
        answer = generation["answer"]
    except HTTPException as exc:
        llm_error = exc.detail

    # Basic evidence status
    grounding = validate_grounding(answer or "", context)
    conflict = detect_conflicts(retrieval["chunks"])
    evidence_status = determine_evidence_status(grounding, conflict)

    return {
        "question": data.question,
        "answer": answer,
        "sources": retrieval["sources"],
        "ollama_error": llm_error,
        "evidence_status": evidence_status,
        "grounding": grounding,
        "trace": trace.steps,
    }


@app.post("/ask/debug")
def debug_service(data: QuestionRequest):
    """
    Full pipeline with every intermediate value plus the orchestration trace.

    Retrieval runs at EVIDENCE_TOP_K (default 6) so conflict detection can
    compare chunks from multiple document versions.  The LLM only receives
    the top DEFAULT_TOP_K chunks as context to keep the prompt concise.

    If the LLM Service is down the endpoint still returns steps 1-5 with
    answer=null, so the dashboard can render the whole RAG pipeline except
    the final answer.
    """
    question = data.question
    trace = Trace()

    # Step 1 — query embedding
    embedding = call_service(
        "POST",
        f"{RETRIEVAL_SERVICE_URL}/embed",
        service="Retrieval Service",
        step="embed",
        trace=trace,
        json={"text": question},
    )

    # Step 2 — retrieve more chunks for evidence analysis
    retrieval_wide = call_service(
        "POST",
        f"{RETRIEVAL_SERVICE_URL}/retrieve",
        service="Retrieval Service",
        step="retrieve",
        trace=trace,
        json={"question": question, "top_k": EVIDENCE_TOP_K},
    )

    # The LLM context uses only the top DEFAULT_TOP_K chunks (best matches)
    llm_chunks = retrieval_wide["chunks"][:DEFAULT_TOP_K]
    llm_distances = retrieval_wide["distances"][:DEFAULT_TOP_K]
    llm_sources = list(dict.fromkeys(c["source"] for c in llm_chunks))

    # Step 3 — context assembly + prompt
    started = time.perf_counter()
    context_string = CONTEXT_SEPARATOR.join(c["text"] for c in llm_chunks)
    prompt = build_rag_prompt(context_string, question)
    trace.record("build_prompt", "app-service", "local",
                 (time.perf_counter() - started) * 1000, "ok")

    # Step 4 — generation
    answer = None
    llm_error = None
    model = None
    try:
        generation = call_service(
            "POST",
            f"{LLM_SERVICE_URL}/generate",
            service="LLM Service",
            step="generate",
            trace=trace,
            json={"prompt": prompt},
            timeout=310,
        )
        answer = generation["answer"]
        model = generation.get("model")
    except HTTPException as exc:
        llm_error = exc.detail

    # Evidence analysis operates on ALL retrieved chunks (wide retrieval)
    all_chunks  = retrieval_wide["chunks"]
    all_dists   = retrieval_wide["distances"]
    conflict    = detect_conflicts(all_chunks)
    ver_res     = resolve_version(all_chunks, conflict.get("conflicts", []))
    grounding   = validate_grounding(answer or "", context_string)
    ev_status   = determine_evidence_status(grounding, conflict)

    return {
        "question": question,
        "query_embedding_preview": embedding["preview"],
        "query_embedding_dimension": embedding["dimension"],
        # UI shows the wide set so users can see all retrieved chunks
        "retrieved_chunks": all_chunks,
        "distances": all_dists,
        # LLM only saw the top-k subset
        "llm_chunks": llm_chunks,
        "llm_distances": llm_distances,
        "context": context_string,
        "prompt": prompt,
        "answer": answer,
        "sources": llm_sources,
        "model": model,
        "ollama_error": llm_error,
        "trace": trace.steps,
        # Evidence block (all additive)
        "evidence": build_evidence(all_chunks, all_dists),
        "conflict": conflict,
        "version_resolution": ver_res,
        "grounding": grounding,
        "evidence_status": ev_status,
    }


@app.post("/ask/evidence")
def evidence_service(data: QuestionRequest):
    """
    Full evidence-aware RAG pipeline with wide retrieval for conflict detection.
    """
    question = data.question
    trace = Trace()

    embedding = call_service(
        "POST",
        f"{RETRIEVAL_SERVICE_URL}/embed",
        service="Retrieval Service",
        step="embed",
        trace=trace,
        json={"text": question},
    )

    retrieval_wide = call_service(
        "POST",
        f"{RETRIEVAL_SERVICE_URL}/retrieve",
        service="Retrieval Service",
        step="retrieve",
        trace=trace,
        json={"question": question, "top_k": EVIDENCE_TOP_K},
    )

    llm_chunks = retrieval_wide["chunks"][:DEFAULT_TOP_K]
    started = time.perf_counter()
    context_string = CONTEXT_SEPARATOR.join(c["text"] for c in llm_chunks)
    prompt = build_rag_prompt(context_string, question)
    trace.record("build_prompt", "app-service", "local",
                 (time.perf_counter() - started) * 1000, "ok")

    answer = None
    llm_error = None
    model = None
    try:
        generation = call_service(
            "POST",
            f"{LLM_SERVICE_URL}/generate",
            service="LLM Service",
            step="generate",
            trace=trace,
            json={"prompt": prompt},
            timeout=310,
        )
        answer = generation["answer"]
        model = generation.get("model")
    except HTTPException as exc:
        llm_error = exc.detail

    all_chunks = retrieval_wide["chunks"]
    all_dists  = retrieval_wide["distances"]
    conflict   = detect_conflicts(all_chunks)
    version_res = resolve_version(all_chunks, conflict.get("conflicts", []))
    grounding  = validate_grounding(answer or "", context_string)
    ev_status  = determine_evidence_status(grounding, conflict)

    return {
        "question": question,
        "query_embedding_preview": embedding["preview"],
        "query_embedding_dimension": embedding["dimension"],
        "retrieved_chunks": all_chunks,
        "distances": all_dists,
        "context": context_string,
        "prompt": prompt,
        "answer": answer,
        "sources": list(dict.fromkeys(c["source"] for c in llm_chunks)),
        "model": model,
        "ollama_error": llm_error,
        "trace": trace.steps,
        "evidence": build_evidence(all_chunks, all_dists),
        "conflict": conflict,
        "version_resolution": version_res,
        "grounding": grounding,
        "evidence_status": ev_status,
        "evidence_summary": {
            "total_sources": len(set(c["source"] for c in all_chunks)),
            "chunks_retrieved": len(all_chunks),
            "conflict_detected": conflict["conflict_detected"],
            "resolution_performed": version_res.get("resolution_performed", False),
            "groundedness": grounding.get("groundedness"),
            "status": ev_status,
        },
    }


# ── Knowledge-base endpoints (Data Service + reindex fan-out) ────────────────
def _kb_info() -> dict:
    """Compose the dashboard's KB view from the Data and Retrieval services."""
    docs = call_service(
        "GET",
        f"{DATA_SERVICE_URL}/documents",
        service="Data Service",
        step="documents",
    )

    # Vector count is authoritative from the index, not the document store.
    try:
        index = call_service(
            "GET",
            f"{RETRIEVAL_SERVICE_URL}/index/info",
            service="Retrieval Service",
            step="index_info",
            timeout=10,
        )
        vectors = index["vectors"]
        dimension = index["dimension"]
        index_type = index["index_type"]
    except HTTPException:
        vectors = docs["total_chunks"]
        dimension = EMBEDDING_DIMENSION
        index_type = "IndexFlatL2"

    return {
        "documents": docs["documents"],
        "total_chunks": vectors,
        "embedding_dimension": dimension,
        "faiss_index_type": index_type,
        "uploaded_count": docs["uploaded_count"],
        "supported_upload_types": docs["supported_upload_types"],
        "max_upload_mb": docs["max_upload_mb"],
    }


@app.get("/kb/info")
def kb_info():
    """Knowledge-base metadata for the dashboard."""
    return _kb_info()


def _trigger_reindex() -> None:
    """Ask Retrieval to rebuild after the document set changed."""
    try:
        requests.post(f"{RETRIEVAL_SERVICE_URL}/reindex", timeout=120)
    except requests.RequestException:
        # Not fatal: Retrieval also re-indexes lazily on the next query when it
        # notices the Data Service version has moved.
        pass


@app.post("/kb/upload")
async def upload_documents(files: List[UploadFile] = File(...)):
    """Forward the upload to the Data Service, then rebuild the vector index."""
    if not files:
        raise HTTPException(status_code=400, detail="No files were uploaded.")

    forward = []
    for upload in files:
        raw = await upload.read()
        await upload.close()
        forward.append(
            ("files", (upload.filename, raw, upload.content_type or "application/octet-stream"))
        )

    result = call_service(
        "POST",
        f"{DATA_SERVICE_URL}/documents",
        service="Data Service",
        step="upload",
        files=forward,
        timeout=180,
    )

    _trigger_reindex()
    return {"uploaded": result["uploaded"], "failed": result["failed"], "kb": _kb_info()}


@app.post("/kb/upload/with-metadata")
async def upload_documents_with_metadata(
    files: List[UploadFile] = File(...),
    document_type: str = Form(None),
    loan_type: str = Form(None),
    version: str = Form(None),
    effective_date: str = Form(None),
):
    """
    Upload documents WITH optional metadata fields forwarded to the Data Service.
    All metadata fields are optional — same as /kb/upload when omitted.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files were uploaded.")

    forward_files = []
    for upload in files:
        raw = await upload.read()
        await upload.close()
        forward_files.append(
            ("files", (upload.filename, raw, upload.content_type or "application/octet-stream"))
        )

    # Build optional metadata form data to forward
    forward_data = {}
    if document_type:
        forward_data["document_type"] = document_type
    if loan_type:
        forward_data["loan_type"] = loan_type
    if version:
        forward_data["version"] = version
    if effective_date:
        forward_data["effective_date"] = effective_date

    result = call_service(
        "POST",
        f"{DATA_SERVICE_URL}/documents",
        service="Data Service",
        step="upload",
        files=forward_files,
        data=forward_data if forward_data else None,
        timeout=180,
    )

    _trigger_reindex()
    return {"uploaded": result["uploaded"], "failed": result["failed"], "kb": _kb_info()}


# ── Model Playground endpoint ────────────────────────────────────────────────
class PlaygroundRequest(BaseModel):
    question: str
    model: str  # e.g. "codellama:latest", "llama3.2:latest", "gemma:2b"


@app.get("/playground/models")
def playground_models():
    """
    List Ollama models available for the playground, deduplicated by digest.

    Ollama can have the same model under multiple tags (e.g. codellama:7b and
    codellama:latest point to the same weights). We keep one tag per unique
    digest, preferring the more specific tag (e.g. '7b' over 'latest').
    """
    try:
        res = requests.get(f"{LLM_SERVICE_URL}/models", timeout=10)
        res.raise_for_status()
        raw_models = res.json().get("models", [])
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail=f"LLM Service unreachable: {exc}")

    # raw_models may be a list of strings (names) or dicts with digest info.
    # Ask Ollama directly for the full tag list with digests.
    ollama_url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    try:
        tags_res = requests.get(f"{ollama_url}/api/tags", timeout=10)
        tags_res.raise_for_status()
        tag_list = tags_res.json().get("models", [])
    except requests.RequestException:
        # Fallback: no digest info available, just return what the LLM service reported
        return {"models": raw_models}

    # Deduplicate: for each unique digest keep the most specific tag.
    # "Most specific" = prefer a versioned/numbered tag over 'latest'.
    seen_digests: dict[str, str] = {}
    for entry in tag_list:
        name = entry.get("name", "")
        digest = entry.get("digest", name)  # fall back to name if no digest
        existing = seen_digests.get(digest)
        if existing is None:
            seen_digests[digest] = name
        else:
            # Prefer a tag that is NOT just '<model>:latest'
            if existing.endswith(":latest") and not name.endswith(":latest"):
                seen_digests[digest] = name

    unique_models = list(seen_digests.values())
    return {"models": unique_models}


@app.post("/playground/ask")
def playground_ask(data: PlaygroundRequest):
    """
    Full debug pipeline with a caller-specified model.

    Retrieval (MiniLM + FAISS) is always the same; only the LLM changes.
    """
    question = data.question
    trace = Trace()

    embedding = call_service(
        "POST",
        f"{RETRIEVAL_SERVICE_URL}/embed",
        service="Retrieval Service",
        step="embed",
        trace=trace,
        json={"text": question},
    )

    retrieval = call_service(
        "POST",
        f"{RETRIEVAL_SERVICE_URL}/retrieve",
        service="Retrieval Service",
        step="retrieve",
        trace=trace,
        json={"question": question, "top_k": DEFAULT_TOP_K},
    )

    started = time.perf_counter()
    context_string = CONTEXT_SEPARATOR.join(c["text"] for c in retrieval["chunks"])
    prompt = build_rag_prompt(context_string, question)
    trace.record("build_prompt", "app-service", "local",
                 (time.perf_counter() - started) * 1000, "ok")

    # Call Ollama directly with the requested model (bypassing the LLM service's
    # single-model default by going through the LLM service's generate endpoint
    # which we temporarily override via a direct Ollama call).
    ollama_url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    answer = None
    llm_error = None
    model_used = data.model
    gen_started = time.perf_counter()
    try:
        res = requests.post(
            f"{ollama_url}/api/generate",
            json={"model": data.model, "prompt": prompt, "stream": False,
                  "options": {"temperature": 0}},
            timeout=310,
        )
        gen_elapsed = (time.perf_counter() - gen_started) * 1000
        trace.record("generate", f"ollama ({data.model})", f"{ollama_url}/api/generate",
                     gen_elapsed, "ok" if res.ok else f"http_{res.status_code}")
        if res.ok:
            body = res.json()
            answer = body.get("response", "")
            model_used = body.get("model", data.model)
        else:
            llm_error = f"Ollama returned HTTP {res.status_code}"
    except requests.exceptions.ConnectionError:
        llm_error = f"Ollama unreachable at {ollama_url}"
        trace.record("generate", f"ollama ({data.model})", f"{ollama_url}/api/generate",
                     (time.perf_counter() - gen_started) * 1000, "unreachable")
    except requests.RequestException as exc:
        llm_error = str(exc)
        trace.record("generate", f"ollama ({data.model})", f"{ollama_url}/api/generate",
                     (time.perf_counter() - gen_started) * 1000, "error")

    return {
        "question": question,
        "model": model_used,
        "query_embedding_preview": embedding["preview"],
        "query_embedding_dimension": embedding["dimension"],
        "retrieved_chunks": retrieval["chunks"],
        "distances": retrieval["distances"],
        "context": context_string,
        "prompt": prompt,
        "answer": answer,
        "sources": retrieval["sources"],
        "ollama_error": llm_error,
        "trace": trace.steps,
    }


@app.delete("/kb/documents/{filename}")
def delete_document(filename: str):
    """Forward the delete to the Data Service, then rebuild the vector index."""
    result = call_service(
        "DELETE",
        f"{DATA_SERVICE_URL}/documents/{filename}",
        service="Data Service",
        step="delete",
        timeout=30,
    )

    _trigger_reindex()
    return {"deleted": result["deleted"], "kb": _kb_info()}
