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
from services.app_service.guardrails import (
    check_input,
    check_evidence_sufficiency,
    validate_output,
    build_guardrail_block,
    check_injection,
    check_context_injection,
    check_numeric_fidelity,
    classify_intent,
    MAX_INPUT_LENGTH,
    MAX_EVIDENCE_DISTANCE,
)
from services.app_service.evidence import (
    EVIDENCE_TOP_K,
    build_evidence,
    detect_conflicts,
    resolve_version,
    validate_grounding,
    determine_evidence_status,
)
from services.common.injection import BLOCKING_SEVERITY
from services.app_service.source_graph import build_source_graph
from services.app_service.repo_analysis import get_repo_context, build_repo_prompt

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



def _sanitise_retrieval(retrieval: dict, trace: Trace | None = None) -> dict:
    """
    Drop retrieved chunks that carry instruction-like text, in place.

    The prompt is one flat string, so a chunk saying "ignore previous
    instructions" arrives with the same authority as the system instructions
    above it. check_input() cannot catch this -- the user's question is
    ordinary; the payload rides in through the documents.

    Chunks are removed rather than the request being refused: one poisoned
    document should not deny service for a legitimate question. `chunks`,
    `distances` and `sources` are filtered together so every downstream
    consumer -- evidence, conflict detection, the source graph -- stays
    aligned.
    """
    chunks = list(retrieval.get("chunks") or [])
    distances = list(retrieval.get("distances") or [])
    report = check_context_injection(chunks)

    if report["flagged_count"]:
        dropped = {f["rank"] for f in report["flagged_chunks"]}  # 1-based
        retrieval["chunks"] = [c for i, c in enumerate(chunks, 1) if i not in dropped]
        retrieval["distances"] = [d for i, d in enumerate(distances, 1) if i not in dropped]
        retrieval["sources"] = list(
            dict.fromkeys(c.get("source") for c in retrieval["chunks"])
        )
        if trace:
            trace.record(
                "injection_guard", "app-service", "local", 0.0,
                f"removed_{report['flagged_count']}",
            )
    return report


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
    """
    Orchestrate retrieval + generation with intent-based routing.

    DOMAIN A (LOAN):    question -> Loan FAISS -> evidence check -> LLM
    DOMAIN B (CODEBASE): question -> repo file analysis -> LLM
    OUT_OF_SCOPE:       refuse immediately, no retrieval or LLM called
    """

    # ── INPUT VALIDATION ─────────────────────────────────────────────────
    guard_status, guard_reason = check_input(data.question)
    if guard_status != "pass":
        return {
            "question": data.question,
            "answer": None,
            "sources": [],
            "guardrail": {
                "input_check": guard_status,
                "input_scope": "fail" if guard_status == "reject_scope" else "pass",
                "input_injection": (
                    "fail" if guard_status == "reject_injection" else "pass"
                ),
                "evidence_sufficient": "n/a",
                "action": "rejected",
                "reason": guard_reason,
                "scope_status": "FAIL",
                "domain": "OUT_OF_SCOPE",
                "category": "OUT_OF_SCOPE",
                "route": "NONE",
                "retrieval_source": "NONE",
                "llm_called": False,
            },
            "controlled_response": guard_reason,
            "blocked": True,
            "ollama_error": None,
            "evidence_status": "blocked",
            "grounding": {},
            "trace": [],
        }

    # ── INTENT CLASSIFICATION & ROUTING ─────────────────────────────────
    domain, category = classify_intent(data.question)
    trace = Trace()

    # ── DOMAIN B: CODEBASE → Repository analysis ──────────────────────────
    if domain == "CODEBASE":
        repo = get_repo_context(data.question)
        context = repo["context"]
        sources = repo["sources"]

        if not repo["sufficient"]:
            return {
                "question": data.question,
                "answer": None,
                "sources": sources,
                "guardrail": {
                    "input_check": "pass",
                    "input_scope": "pass",
                    "evidence_sufficient": "fail",
                    "action": "abstained",
                    "scope_status": "PASS",
                    "domain": "CODEBASE",
                    "category": category,
                    "route": "REPOSITORY_ANALYSIS",
                    "retrieval_source": "REPOSITORY",
                    "llm_called": False,
                },
                "controlled_response": "I couldn't find sufficient repository information to answer this question.",
                "blocked": True,
                "evidence_status": "insufficient_evidence",
                "grounding": {},
                "trace": [],
            }

        prompt = build_repo_prompt(context, data.question)
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

        output_validation = validate_output(answer or "", data.question, context)

        return {
            "question": data.question,
            "answer": answer,
            "sources": sources,
            "ollama_error": llm_error,
            "evidence_status": "supported",
            "grounding": {"status": "supported", "groundedness": None},
            "trace": trace.steps,
            "guardrail": {
                "input_check": "pass",
                "input_scope": "pass",
                "evidence_sufficient": "pass",
                "action": "allow",
                "scope_status": "PASS",
                "domain": "CODEBASE",
                "category": category,
                "route": "REPOSITORY_ANALYSIS",
                "retrieval_source": "REPOSITORY",
                "llm_called": True,
            },
            "output_validation": output_validation,
            "blocked": False,
        }

    # ── DOMAIN A: LOAN → Loan RAG pipeline ───────────────────────────────
    retrieval = call_service(
        "POST",
        f"{RETRIEVAL_SERVICE_URL}/retrieve",
        service="Retrieval Service",
        step="retrieve",
        trace=trace,
        json={"question": data.question, "top_k": DEFAULT_TOP_K},
    )

    injection_report = _sanitise_retrieval(retrieval, trace)

    ev_sufficient, ev_reason = check_evidence_sufficiency(
        data.question, retrieval["chunks"], retrieval.get("distances", [])
    )
    if not ev_sufficient:
        return {
            "question": data.question,
            "answer": None,
            "sources": retrieval["sources"],
            "guardrail": {
                "input_check": "pass",
                "input_scope": "pass",
                "evidence_sufficient": "fail",
                "action": "abstained",
                "scope_status": "PASS",
                "domain": "LOAN",
                "category": "LOAN",
                "route": "LOAN_RAG",
                "retrieval_source": "LOAN_KB",
                "embedding_called": True,
                "retrieval_called": True,
                "llm_called": False,
            },
            "controlled_response": ev_reason,
            "blocked": True,
            "ollama_error": None,
            "evidence_status": "insufficient_evidence",
            "grounding": {"status": "insufficient_evidence", "groundedness": 0.0},
            "trace": trace.steps,
        }

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

    grounding = validate_grounding(answer or "", context)
    conflict = detect_conflicts(retrieval["chunks"])
    evidence_status = determine_evidence_status(grounding, conflict)
    output_validation = validate_output(answer or "", data.question, context)
    # Grounding discards digits, so it cannot tell 2.5% from 25%. This can.
    numeric = check_numeric_fidelity(answer or "", context)

    return {
        "question": data.question,
        "answer": answer,
        "sources": retrieval["sources"],
        "ollama_error": llm_error,
        "evidence_status": evidence_status,
        "grounding": grounding,
        "trace": trace.steps,
        "guardrail": {
            "input_check": "pass",
            "input_scope": "pass",
            "evidence_sufficient": "pass",
            "action": "allow",
            "scope_status": "PASS",
            "domain": "LOAN",
            "category": "LOAN",
            "route": "LOAN_RAG",
            "retrieval_source": "LOAN_KB",
            "embedding_called": True,
            "retrieval_called": True,
            "llm_called": True,
            "context_injection": "pass" if injection_report["passed"] else "sanitised",
            "context_chunks_removed": injection_report["flagged_count"],
            "numeric_fidelity": numeric["status"],
        },
        "output_validation": output_validation,
        "context_injection": injection_report,
        "numeric_fidelity": numeric,
        "blocked": False,
    }


@app.post("/ask/debug")
def debug_service(data: QuestionRequest):
    """
    Full pipeline with intent-based routing and every intermediate value.

    CODEBASE questions -> repository file analysis -> LLM (no FAISS)
    LOAN questions     -> Loan FAISS -> evidence check -> LLM
    OUT_OF_SCOPE       -> refuse immediately
    """
    question = data.question

    # ── INPUT VALIDATION ─────────────────────────────────────────────────
    guard_status, guard_reason = check_input(question)
    if guard_status != "pass":
        return {
            "question": question,
            "answer": None,
            "sources": [],
            "guardrail": {
                "input_check": guard_status,
                "input_injection": (
                    "fail" if guard_status == "reject_injection" else "pass"
                ),
                "scope_status": "FAIL",
                "domain": "OUT_OF_SCOPE",
                "category": "OUT_OF_SCOPE",
                "route": "NONE",
                "action": "rejected",
                "reason": guard_reason,
                "llm_called": False,
            },
            "controlled_response": guard_reason,
            "blocked": True,
            "ollama_error": None,
            "trace": [],
        }

    # ── INTENT CLASSIFICATION ─────────────────────────────────────────────
    domain, category = classify_intent(question)
    trace = Trace()

    # ── DOMAIN B: CODEBASE → Repository analysis (NO FAISS) ──────────────
    if domain == "CODEBASE":
        repo = get_repo_context(question)
        context = repo["context"]
        sources = repo["sources"]
        repo_chunks = repo["chunks"]

        guardrail_base = {
            "input_check": "pass",
            "scope_status": "PASS",
            "domain": "CODEBASE",
            "category": category,
            "route": "REPOSITORY_ANALYSIS",
            "retrieval_source": "REPOSITORY",
        }

        if not repo["sufficient"]:
            return {
                "question": question,
                "answer": None,
                "sources": sources,
                "retrieved_chunks": [],
                "distances": [],
                "context": "",
                "prompt": "",
                "trace": trace.steps,
                "guardrail": {
                    **guardrail_base,
                    "evidence_sufficient": "fail",
                    "action": "abstained",
                    "llm_called": False,
                },
                "controlled_response": "I couldn't find sufficient repository information to answer this question.",
                "blocked": True,
                "evidence_status": "insufficient_evidence",
                "grounding": {},
            }

        prompt = build_repo_prompt(context, question)

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

        output_validation = validate_output(answer or "", question, context)

        return {
            "question": question,
            "answer": answer,
            "sources": sources,
            "retrieved_chunks": repo_chunks,
            "distances": [],
            "context": context,
            "prompt": prompt,
            "model": model,
            "ollama_error": llm_error,
            "trace": trace.steps,
            "evidence": [],
            "conflict": {"conflict_detected": False, "conflicts": []},
            "version_resolution": {"resolution_performed": False},
            "grounding": {"status": "supported", "groundedness": None},
            "evidence_status": "supported",
            "source_graph": None,
            "output_validation": output_validation,
            "guardrail": {
                **guardrail_base,
                "evidence_sufficient": "pass",
                "action": "allow",
                "llm_called": True,
            },
            "blocked": False,
        }

    # ── DOMAIN A: LOAN → Loan FAISS RAG pipeline ─────────────────────────
    # Step 1 — query embedding
    embedding = call_service(
        "POST",
        f"{RETRIEVAL_SERVICE_URL}/embed",
        service="Retrieval Service",
        step="embed",
        trace=trace,
        json={"text": question},
    )

    # Step 2 — retrieve chunks
    retrieval_wide = call_service(
        "POST",
        f"{RETRIEVAL_SERVICE_URL}/retrieve",
        service="Retrieval Service",
        step="retrieve",
        trace=trace,
        json={"question": question, "top_k": EVIDENCE_TOP_K},
    )

    injection_report = _sanitise_retrieval(retrieval_wide, trace)

    llm_chunks = retrieval_wide["chunks"][:DEFAULT_TOP_K]
    llm_distances = retrieval_wide["distances"][:DEFAULT_TOP_K]
    llm_sources = list(dict.fromkeys(c["source"] for c in llm_chunks))

    # Step 3 — context + prompt
    started = time.perf_counter()
    context_string = CONTEXT_SEPARATOR.join(c["text"] for c in llm_chunks)
    prompt = build_rag_prompt(context_string, question)
    trace.record("build_prompt", "app-service", "local",
                 (time.perf_counter() - started) * 1000, "ok")

    all_chunks = retrieval_wide["chunks"]
    all_dists  = retrieval_wide["distances"]
    conflict   = detect_conflicts(all_chunks)
    ver_res    = resolve_version(all_chunks, conflict.get("conflicts", []))

    # Evidence sufficiency check
    ev_sufficient, ev_reason = check_evidence_sufficiency(
        question, llm_chunks, llm_distances
    )

    if not ev_sufficient:
        grounding = {"status": "insufficient_evidence", "groundedness": 0.0,
                     "explanation": "Evidence guardrail: context does not sufficiently cover the question."}
        return {
            "question": question,
            "query_embedding_preview": embedding["preview"],
            "query_embedding_dimension": embedding["dimension"],
            "retrieved_chunks": all_chunks,
            "distances": all_dists,
            "llm_chunks": llm_chunks,
            "llm_distances": llm_distances,
            "context": context_string,
            "prompt": prompt,
            "answer": None,
            "sources": llm_sources,
            "model": None,
            "ollama_error": None,
            "trace": trace.steps,
            "evidence": build_evidence(all_chunks, all_dists),
            "conflict": conflict,
            "version_resolution": ver_res,
            "grounding": grounding,
            "evidence_status": "insufficient_evidence",
            "source_graph": None,
            "guardrail": {
                "input_check": "pass",
                "scope_status": "PASS",
                "domain": "LOAN",
                "category": "LOAN",
                "route": "LOAN_RAG",
                "retrieval_source": "LOAN_KB",
                "evidence_sufficient": "fail",
                "action": "abstained",
                "llm_called": False,
            },
            "controlled_response": ev_reason,
            "blocked": True,
        }

    # Step 4 — LLM generation
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

    grounding = validate_grounding(answer or "", context_string)
    ev_status = determine_evidence_status(grounding, conflict)
    numeric = check_numeric_fidelity(answer or "", context_string)

    return {
        "question": question,
        "query_embedding_preview": embedding["preview"],
        "query_embedding_dimension": embedding["dimension"],
        "retrieved_chunks": all_chunks,
        "distances": all_dists,
        "llm_chunks": llm_chunks,
        "llm_distances": llm_distances,
        "context": context_string,
        "prompt": prompt,
        "answer": answer,
        "sources": llm_sources,
        "model": model,
        "ollama_error": llm_error,
        "trace": trace.steps,
        "evidence": build_evidence(all_chunks, all_dists),
        "conflict": conflict,
        "version_resolution": ver_res,
        "grounding": grounding,
        "evidence_status": ev_status,
        "context_injection": injection_report,
        "numeric_fidelity": numeric,
        "source_graph": build_source_graph(
            question=question,
            chunks=all_chunks,
            distances=all_dists,
            llm_chunk_count=len(llm_chunks),
            answer=answer,
            conflict=conflict,
            version_resolution=ver_res,
        ),
        "guardrail": {
            "input_check": "pass",
            "scope_status": "PASS",
            "domain": "LOAN",
            "category": "LOAN",
            "route": "LOAN_RAG",
            "retrieval_source": "LOAN_KB",
            "evidence_sufficient": "pass",
            "action": "allow",
            "llm_called": True,
            "context_injection": "pass" if injection_report["passed"] else "sanitised",
            "context_chunks_removed": injection_report["flagged_count"],
            "numeric_fidelity": numeric["status"],
        },
        "blocked": False,
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

    injection_report = _sanitise_retrieval(retrieval_wide, trace)

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
    numeric    = check_numeric_fidelity(answer or "", context_string)

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
        "context_injection": injection_report,
        "numeric_fidelity": numeric,
        "source_graph": build_source_graph(
            question=question,
            chunks=all_chunks,
            distances=all_dists,
            llm_chunk_count=len(llm_chunks),
            answer=answer,
            conflict=conflict,
            version_resolution=version_res,
        ),
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


# ── Guardrail inspection endpoints ──────────────────────────────────────────

class GuardrailInputRequest(BaseModel):
    question: str


class InjectionCheckRequest(BaseModel):
    text: str


@app.post("/guardrails/check-injection")
def guardrail_check_injection(data: InjectionCheckRequest):
    """
    Run ONLY the prompt-injection scanner over a piece of document text.

    This is the guardrail that inspects DOCUMENTS rather than the question.
    The same scanner runs at upload time in the Data Service and again over
    retrieved chunks here, just before prompt assembly.
    """
    verdict = check_injection(data.text)
    return {
        "input": data.text[:500],
        "input_length": len(data.text or ""),
        "status": verdict["status"],
        "passed": verdict["passed"],
        "severity": verdict["severity"],
        "blocking": verdict["blocking"],
        "action": verdict["action"],
        "reason": verdict["reason"],
        "match_count": verdict["match_count"],
        "matches": verdict["matches"],
        "blocking_severity": BLOCKING_SEVERITY,
    }


@app.post("/guardrails/check-numeric")
def guardrail_check_numeric(data: GuardrailInputRequest):
    """
    Run the numeric-fidelity guardrail over a real pipeline result.

    Retrieves context for the question, generates an answer, then verifies
    every figure the answer asserts actually appears in that context.  The
    grounding score is returned alongside so the gap is visible: grounding
    tokenises with [a-z]{3,} and therefore cannot distinguish 2.5% from 25%.
    """
    question = data.question

    input_status, input_reason = check_input(question)
    if input_status != "pass":
        return {
            "input": question,
            "status": "n/a",
            "passed": None,
            "reason": input_reason,
            "action": "rejected",
            "llm_called": False,
        }

    retrieval = call_service(
        "POST",
        f"{RETRIEVAL_SERVICE_URL}/retrieve",
        service="Retrieval Service",
        step="retrieve",
        json={"question": question, "top_k": DEFAULT_TOP_K},
    )
    injection_report = _sanitise_retrieval(retrieval)
    context = CONTEXT_SEPARATOR.join(c["text"] for c in retrieval["chunks"])

    answer = None
    llm_error = None
    try:
        generation = call_service(
            "POST",
            f"{LLM_SERVICE_URL}/generate",
            service="LLM Service",
            step="generate",
            json={"prompt": build_rag_prompt(context, question)},
            timeout=310,
        )
        answer = generation["answer"]
    except HTTPException as exc:
        llm_error = exc.detail

    numeric = check_numeric_fidelity(answer or "", context)
    grounding = validate_grounding(answer or "", context)

    return {
        "input": question,
        "answer": answer,
        "ollama_error": llm_error,
        "status": numeric["status"],
        "passed": numeric["passed"],
        "action": "flagged" if numeric["status"] == "fail" else "allow",
        "reason": numeric["reason"],
        "numbers_checked": numeric["numbers_checked"],
        "verified": numeric["verified"],
        "unverified": numeric["unverified"],
        "advisory": numeric["advisory"],
        "strict_mode": numeric["strict_mode"],
        "sources": retrieval["sources"],
        "context_injection": injection_report,
        # Shown side by side so the blind spot is self-evident.
        "grounding_comparison": {
            "grounding_status": grounding["status"],
            "groundedness": grounding.get("groundedness"),
            "note": (
                "Grounding counts word overlap and discards digits, so it "
                "cannot detect an altered figure. Numeric fidelity can."
            ),
        },
        "llm_called": True,
    }


@app.post("/guardrails/check-input")
def guardrail_check_input(data: GuardrailInputRequest):
    """
    Run ONLY the input validation guardrail (check_input).
    Returns the raw status, reason, length, and whether it passed.
    No retrieval or LLM is called.
    """
    question = data.question
    status, reason = check_input(question)
    return {
        "input": question,
        "input_length": len(question.strip()) if question else 0,
        "status": status,
        "passed": status == "pass",
        "reason": reason,
        "action": "allow" if status == "pass" else "rejected",
        "checks": {
            "empty": "fail" if status == "reject_empty" else "pass",
            "length": "fail" if status == "reject_length" else "pass",
            "injection": "fail" if status == "reject_injection" else "pass",
            "scope": "fail" if status == "reject_scope" else "pass",
        },
        "limits": {
            "max_input_length": MAX_INPUT_LENGTH,
        },
    }


@app.post("/guardrails/check-scope")
def guardrail_check_scope(data: GuardrailInputRequest):
    """
    Run input validation + intent classification.
    Returns the domain, category, and scope decision.
    No retrieval or LLM is called.
    """
    question = data.question
    input_status, input_reason = check_input(question)

    if input_status in ("reject_empty", "reject_length"):
        return {
            "input": question,
            "status": input_status,
            "passed": False,
            "domain": None,
            "category": None,
            "reason": input_reason,
            "action": "rejected",
            "llm_called": False,
        }

    domain, category = classify_intent(question)
    passed = domain != "OUT_OF_SCOPE"

    return {
        "input": question,
        "status": "pass" if passed else "reject_scope",
        "passed": passed,
        "domain": domain,
        "category": category,
        "reason": None if passed else input_reason,
        "action": "allow" if passed else "rejected",
        "llm_called": False,
        "scope_status": "PASS" if passed else "FAIL",
    }


@app.post("/guardrails/check-evidence")
def guardrail_check_evidence(data: GuardrailInputRequest):
    """
    Run input validation + retrieval + evidence sufficiency check.
    Does NOT call the LLM. Returns retrieval results and evidence decision.
    """
    question = data.question
    trace = Trace()

    # Input check first
    input_status, input_reason = check_input(question)
    if input_status != "pass":
        return {
            "input": question,
            "status": input_status,
            "passed": False,
            "reason": input_reason,
            "action": "rejected",
            "llm_called": False,
            "retrieved_chunks": 0,
            "best_distance": None,
            "evidence_status": "blocked_by_input",
            "threshold": MAX_EVIDENCE_DISTANCE,
        }

    domain, category = classify_intent(question)
    if domain == "OUT_OF_SCOPE":
        return {
            "input": question,
            "status": "reject_scope",
            "passed": False,
            "domain": domain,
            "reason": "Question is out of scope.",
            "action": "rejected",
            "llm_called": False,
            "retrieved_chunks": 0,
            "best_distance": None,
            "evidence_status": "blocked_by_scope",
            "threshold": MAX_EVIDENCE_DISTANCE,
        }

    if domain == "CODEBASE":
        return {
            "input": question,
            "status": "pass",
            "passed": True,
            "domain": domain,
            "category": category,
            "reason": "Codebase questions use repository analysis — no FAISS retrieval.",
            "action": "allow",
            "llm_called": False,
            "retrieved_chunks": 0,
            "best_distance": None,
            "evidence_status": "codebase_route",
            "threshold": MAX_EVIDENCE_DISTANCE,
        }

    # LOAN domain — run retrieval
    try:
        retrieval = call_service(
            "POST",
            f"{RETRIEVAL_SERVICE_URL}/retrieve",
            service="Retrieval Service",
            step="retrieve",
            trace=trace,
            json={"question": question, "top_k": DEFAULT_TOP_K},
        )
    except HTTPException as exc:
        return {
            "input": question,
            "status": "error",
            "passed": False,
            "reason": str(exc.detail),
            "action": "error",
            "llm_called": False,
            "retrieved_chunks": 0,
            "best_distance": None,
            "evidence_status": "retrieval_error",
            "threshold": MAX_EVIDENCE_DISTANCE,
        }

    chunks = retrieval["chunks"]
    distances = retrieval.get("distances", [])
    best_distance = distances[0] if distances else None

    ev_sufficient, ev_reason = check_evidence_sufficiency(question, chunks, distances)

    return {
        "input": question,
        "status": "pass" if ev_sufficient else "insufficient_evidence",
        "passed": ev_sufficient,
        "domain": domain,
        "category": category,
        "retrieved_chunks": len(chunks),
        "best_distance": round(best_distance, 4) if best_distance is not None else None,
        "threshold": MAX_EVIDENCE_DISTANCE,
        "evidence_status": "sufficient" if ev_sufficient else "insufficient",
        "reason": ev_reason if not ev_sufficient else None,
        "action": "allow" if ev_sufficient else "abstained",
        "llm_called": False,
        "chunks_preview": [
            {"source": c.get("source", ""), "text": c.get("text", "")[:120]}
            for c in chunks[:3]
        ],
        "trace": trace.steps,
    }


@app.post("/guardrails/check-output")
def guardrail_check_output(data: GuardrailInputRequest):
    """
    Run the full pipeline including LLM, then validate the output.
    Returns the output_validation result from validate_output().
    """
    question = data.question
    trace = Trace()

    input_status, input_reason = check_input(question)
    if input_status != "pass":
        return {
            "input": question,
            "status": input_status,
            "passed": False,
            "reason": input_reason,
            "action": "rejected",
            "answer": None,
            "output_validation": None,
        }

    domain, category = classify_intent(question)
    if domain == "OUT_OF_SCOPE":
        return {
            "input": question,
            "status": "reject_scope",
            "passed": False,
            "domain": domain,
            "reason": "Out of scope — no answer generated.",
            "action": "rejected",
            "answer": None,
            "output_validation": None,
        }

    # CODEBASE route
    if domain == "CODEBASE":
        from services.app_service.repo_analysis import get_repo_context, build_repo_prompt
        repo = get_repo_context(question)
        context = repo["context"]
        if not repo["sufficient"]:
            return {
                "input": question,
                "status": "insufficient_evidence",
                "passed": False,
                "domain": domain,
                "reason": "Insufficient repository context.",
                "action": "abstained",
                "answer": None,
                "output_validation": None,
            }
        prompt = build_repo_prompt(context, question)
    else:
        retrieval = call_service(
            "POST",
            f"{RETRIEVAL_SERVICE_URL}/retrieve",
            service="Retrieval Service",
            step="retrieve",
            trace=trace,
            json={"question": question, "top_k": DEFAULT_TOP_K},
        )
        chunks = retrieval["chunks"]
        distances = retrieval.get("distances", [])
        ev_sufficient, ev_reason = check_evidence_sufficiency(question, chunks, distances)
        if not ev_sufficient:
            return {
                "input": question,
                "status": "insufficient_evidence",
                "passed": False,
                "domain": domain,
                "reason": ev_reason,
                "action": "abstained",
                "answer": None,
                "output_validation": None,
            }
        context = "\n".join(c["text"] for c in chunks)
        from services.common.prompts import build_rag_prompt as _build_rag_prompt
        prompt = _build_rag_prompt(context, question)

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

    if not answer:
        return {
            "input": question,
            "status": "llm_error",
            "passed": False,
            "domain": domain,
            "reason": llm_error or "LLM returned no answer.",
            "action": "error",
            "answer": None,
            "output_validation": None,
        }

    output_validation = validate_output(answer, question, context)

    return {
        "input": question,
        "status": "pass" if output_validation["overall"] == "pass" else "fail",
        "passed": output_validation["overall"] == "pass",
        "domain": domain,
        "answer": answer,
        "action": "accepted" if output_validation["overall"] == "pass" else "flagged",
        "output_validation": output_validation,
        "trace": trace.steps,
    }
