"""
LLM Service — port 8002

The only component that knows Ollama exists. It wraps the Code Llama runtime
behind a stable HTTP contract, so the orchestrator never has to care which
runtime or model is behind it — swapping Ollama for another backend means
changing this file only.

Endpoints
    GET  /health      liveness + whether Ollama is reachable
    GET  /models      models available in the Ollama runtime
    POST /generate    prompt -> answer
"""

import os
import time

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

SERVICE_NAME = "llm-service"

OLLAMA_BASE_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "codellama:7b")
GENERATE_TIMEOUT = int(os.environ.get("GENERATE_TIMEOUT", "300"))

app = FastAPI(title="LLM Service", version="1.0.0")


class PromptRequest(BaseModel):
    prompt: str


@app.get("/")
def root():
    return {"service": SERVICE_NAME, "message": "LLM Service is running."}


@app.get("/health")
def health():
    """Report reachability of the Ollama runtime without failing the request."""
    try:
        res = requests.get(OLLAMA_TAGS_URL, timeout=5)
        res.raise_for_status()
        models = [m["name"] for m in res.json().get("models", [])]
        return {
            "service": SERVICE_NAME,
            "status": "ok",
            "runtime": "Ollama",
            "runtime_url": OLLAMA_BASE_URL,
            "model": OLLAMA_MODEL,
            "ollama_reachable": True,
            "model_available": OLLAMA_MODEL in models,
            "models": models,
        }
    except requests.RequestException as exc:
        return {
            "service": SERVICE_NAME,
            "status": "degraded",
            "runtime": "Ollama",
            "runtime_url": OLLAMA_BASE_URL,
            "model": OLLAMA_MODEL,
            "ollama_reachable": False,
            "model_available": False,
            "error": str(exc),
        }


@app.get("/models")
def models():
    try:
        res = requests.get(OLLAMA_TAGS_URL, timeout=10)
        res.raise_for_status()
        return {"models": [m["name"] for m in res.json().get("models", [])]}
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Ollama unreachable: {exc}")


@app.post("/generate")
def generate(data: PromptRequest):
    """Forward a fully-built prompt to Code Llama and return the completion."""
    started = time.perf_counter()
    try:
        res = requests.post(
            OLLAMA_GENERATE_URL,
            json={"model": OLLAMA_MODEL, "prompt": data.prompt, "stream": False},
            timeout=GENERATE_TIMEOUT,
        )
        res.raise_for_status()
        answer = res.json().get("response", "")
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Ollama is unreachable at {OLLAMA_BASE_URL}. Ensure the runtime is "
                f"running and '{OLLAMA_MODEL}' has been pulled."
            ),
        )
    except requests.exceptions.Timeout:
        raise HTTPException(
            status_code=504, detail=f"Ollama request timed out after {GENERATE_TIMEOUT}s."
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Ollama error: {exc}")

    return {
        "answer": answer,
        "model": OLLAMA_MODEL,
        "runtime": "Ollama",
        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
    }
