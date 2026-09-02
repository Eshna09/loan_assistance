"""
main.py
FastAPI application — routes for /retrieve, /generate, /ask, /ask/debug, /kb/info.
All endpoints match the spec derived from the eshnaAIDevOps notebook.
"""

from typing import List

import requests as http_requests
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from knowledge_base import (
    retrieve_context,
    get_kb_info,
    get_query_embedding_preview,
    add_document,
    remove_document,
    DocumentError,
    EMBEDDING_DIMENSION,
)

# ── App setup ────────────────────────────────────────────────────────────────
app = FastAPI(title="Loan Knowledge Assistance API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "codellama:7b"

# ── Request models ────────────────────────────────────────────────────────────
class QuestionRequest(BaseModel):
    question: str

class PromptRequest(BaseModel):
    prompt: str


# ── RAG prompt template (exact from notebook) ────────────────────────────────
def build_rag_prompt(context_string: str, question: str) -> str:
    return (
        "You are an educational loan knowledge assistant.\n"
        "Answer the user's question ONLY using the provided context.\n"
        "Do not invent information.\n"
        "If the answer cannot be found in the context, say:\n"
        "'This information is not available in my knowledge base.'\n"
        "This system provides general educational loan information and is not personalized lending, legal, tax, or financial advice.\n"
        "\n"
        f"Context:\n{context_string}\n"
        "\n"
        f"Question:\n{question}\n"
        "\n"
        "Answer:"
    )


def call_ollama(prompt: str) -> str:
    """Send prompt to Ollama and return the response text."""
    try:
        res = http_requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=120,
        )
        res.raise_for_status()
        return res.json().get("response", "")
    except http_requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=502,
            detail="Ollama service is unreachable. Ensure 'ollama serve' is running and codellama:7b is pulled.",
        )
    except http_requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Ollama request timed out.")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Ollama error: {str(exc)}")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "Loan Knowledge Assistance API is running."}


@app.post("/retrieve")
def retrieve_service(data: QuestionRequest):
    """Return top-3 relevant chunks and their sources for a question."""
    chunks, sources, _ = retrieve_context(data.question)
    return {
        "context_chunks": [c["text"] for c in chunks],
        "sources": sources,
    }


@app.post("/generate")
def llm_service(data: PromptRequest):
    """Forward a prompt to Ollama and return the answer."""
    answer = call_ollama(data.prompt)
    return {"answer": answer}


@app.post("/ask")
def application_service(data: QuestionRequest):
    """Orchestrate retrieval + generation and return the final answer."""
    chunks, sources, _ = retrieve_context(data.question)
    context = "\n".join([c["text"] for c in chunks])
    prompt = build_rag_prompt(context, data.question)
    answer = None
    ollama_error = None
    try:
        answer = call_ollama(prompt)
    except HTTPException as e:
        ollama_error = e.detail
    return {
        "question": data.question,
        "answer": answer,
        "sources": sources,
        "ollama_error": ollama_error,
    }


@app.post("/ask/debug")
def debug_service(data: QuestionRequest):
    """
    Full debug endpoint — returns every pipeline step for the dashboard.
    Fields: question, query_embedding_preview, query_embedding_dimension,
            retrieved_chunks, distances, context, prompt, answer.

    If Ollama is unreachable the endpoint still returns steps 1-5 (embedding,
    retrieval, context, prompt) with answer=null and ollama_error set, so the
    dashboard can render all RAG steps except the final LLM answer.
    """
    question = data.question

    # Step 1: query embedding preview
    embedding_preview = get_query_embedding_preview(question)

    # Step 2: retrieval
    chunks, sources, distances = retrieve_context(question)

    # Step 3: context + prompt
    context_string = "\n---\n".join([c["text"] for c in chunks])
    prompt = build_rag_prompt(context_string, question)

    # Step 4: LLM generation — non-fatal: return partial result if Ollama is down
    answer = None
    ollama_error = None
    try:
        answer = call_ollama(prompt)
    except HTTPException as e:
        ollama_error = e.detail

    return {
        "question": question,
        "query_embedding_preview": embedding_preview,
        "query_embedding_dimension": EMBEDDING_DIMENSION,
        "retrieved_chunks": chunks,
        "distances": distances,
        "context": context_string,
        "prompt": prompt,
        "answer": answer,
        "sources": sources,
        "ollama_error": ollama_error,
    }


@app.get("/kb/info")
def kb_info():
    """Return knowledge-base metadata for the dashboard."""
    return get_kb_info()


@app.post("/kb/upload")
async def upload_documents(files: List[UploadFile] = File(...)):
    """
    Upload one or more documents (.txt, .md, .pdf, .docx) into the knowledge base.

    Each accepted file is text-extracted, chunked with the same
    chunk_text(300, overlap=50) logic, embedded with MiniLM, and added to the
    FAISS index — so answers start using it immediately. Files are processed
    independently: a failure on one is reported without rejecting the others.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files were uploaded.")

    uploaded = []
    failed = []

    for upload in files:
        try:
            raw = await upload.read()
            if not raw:
                raise DocumentError(f"'{upload.filename}' is empty.")
            uploaded.append(add_document(upload.filename, raw))
        except DocumentError as exc:
            failed.append({"filename": upload.filename, "error": str(exc)})
        except Exception as exc:  # extraction failures from pypdf/python-docx
            failed.append({
                "filename": upload.filename,
                "error": f"Could not read the file: {exc}",
            })
        finally:
            await upload.close()

    if not uploaded and failed:
        raise HTTPException(status_code=400, detail=failed[0]["error"])

    return {"uploaded": uploaded, "failed": failed, "kb": get_kb_info()}


@app.delete("/kb/documents/{filename}")
def delete_document(filename: str):
    """Remove an uploaded document and rebuild the index. Built-in docs are protected."""
    try:
        remove_document(filename)
    except DocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"deleted": filename, "kb": get_kb_info()}
