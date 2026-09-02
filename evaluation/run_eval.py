"""
run_eval.py — execute the evaluation set against every model under test.

Design constraints (Exercise 1: "keep these the same while comparing"):

  * Application      — the same RAG pipeline; retrieval runs through the
                       Retrieval Service, exactly as the app does.
  * Prompts          — one fixed RAG template for knowledge questions, one
                       fixed code template for code tasks. Byte-identical
                       across models.
  * Questions        — the same eval_set.json for every model.
  * Knowledge base   — the same 6 loan documents / 25 vectors, verified before
                       the run starts.
  * Conditions       — temperature 0, fixed seed, same num_predict cap, same
                       machine, models run sequentially so none competes for
                       memory. Retrieval is executed ONCE per question and the
                       resulting context is replayed to every model, so any
                       difference in output is attributable to the model alone.

Outputs evaluation/results/raw_results.json for score.py to consume.
"""

import json
import os
import re
import statistics
import sys
import threading
import time
from datetime import datetime, timezone

import psutil
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(HERE, "results")

RETRIEVAL_URL = os.environ.get("RETRIEVAL_URL", "http://127.0.0.1:8000/retrieve")
KB_INFO_URL = os.environ.get("KB_INFO_URL", "http://127.0.0.1:8000/kb/info")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")

MODELS = [
    "codellama:7b",
    "wizardlm2:7b",
    "llama3.2:latest",
    "gemma:2b",
]

# Identical decoding settings for every model — part of "same conditions".
GEN_OPTIONS = {"temperature": 0, "seed": 42, "num_predict": 512, "top_p": 1.0}
REQUEST_TIMEOUT = 600


# ── Prompt templates (fixed across models) ───────────────────────────────────
def build_rag_prompt(context_string: str, question: str) -> str:
    """The application's own RAG template, unchanged from services/common/prompts.py."""
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


def build_code_prompt(task: str) -> str:
    """
    Fixed template for the code-generation tasks.

    These bypass RAG deliberately: the app's RAG template forbids answering
    outside the retrieved context, which would make every model refuse every
    coding task and produce a meaningless 0% test-pass rate for all four.
    """
    return (
        "You are a Python assistant for a loan application.\n"
        "Write a single, self-contained Python function that solves the task.\n"
        "Use only the Python standard library.\n"
        "Return only the code inside one ```python code block, with no explanation.\n"
        "\n"
        f"Task:\n{task}\n"
    )


# ── Resource sampling ────────────────────────────────────────────────────────
class ResourceSampler(threading.Thread):
    """
    Sample RSS and CPU of every Ollama process while a generation is running.

    Ollama spawns a separate llama server process per loaded model, so the
    sampler sums across all matching processes rather than tracking one PID.
    """

    def __init__(self, interval=0.25):
        super().__init__(daemon=True)
        self.interval = interval
        self._stop_evt = threading.Event()
        self.rss_samples = []
        self.cpu_samples = []

    @staticmethod
    def _ollama_procs():
        """
        Ollama's memory lives in llama-server.exe, not ollama.exe — the CLI
        process holds only ~45 MB. Match on the executable path so both the
        supervisor and the model server are captured.
        """
        procs = []
        for p in psutil.process_iter(["name", "exe"]):
            try:
                name = (p.info["name"] or "").lower()
                exe = (p.info["exe"] or "").lower()
                if "ollama" in name or "llama-server" in name or "ollama" in exe:
                    procs.append(p)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return procs

    def run(self):
        procs = self._ollama_procs()
        for p in procs:
            try:
                p.cpu_percent(None)  # prime the CPU counter
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        while not self._stop_evt.is_set():
            rss = 0
            cpu = 0.0
            for p in procs:
                try:
                    rss += p.memory_info().rss
                    cpu += p.cpu_percent(None)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            if rss:
                self.rss_samples.append(rss)
                self.cpu_samples.append(cpu)
            self._stop_evt.wait(self.interval)

    def stop(self):
        self._stop_evt.set()
        self.join(timeout=3)
        return {
            "peak_rss_mb": round(max(self.rss_samples) / 1_048_576, 1) if self.rss_samples else None,
            "mean_rss_mb": round(statistics.mean(self.rss_samples) / 1_048_576, 1) if self.rss_samples else None,
            "mean_cpu_percent": round(statistics.mean(self.cpu_samples), 1) if self.cpu_samples else None,
            "peak_cpu_percent": round(max(self.cpu_samples), 1) if self.cpu_samples else None,
            "samples": len(self.rss_samples),
        }


def ollama_ps():
    """Model residency as Ollama reports it — size in memory and GPU/CPU split."""
    try:
        res = requests.get(f"{OLLAMA_URL}/api/ps", timeout=10)
        res.raise_for_status()
        out = []
        for m in res.json().get("models", []):
            total = m.get("size", 0)
            vram = m.get("size_vram", 0)
            out.append({
                "name": m.get("name"),
                "resident_mb": round(total / 1_048_576, 1),
                "vram_mb": round(vram / 1_048_576, 1),
                "gpu_percent": round(100 * vram / total, 1) if total else None,
            })
        return out
    except requests.RequestException:
        return []


# ── Generation ───────────────────────────────────────────────────────────────
def generate(model: str, prompt: str) -> dict:
    """One timed generation, with resource sampling and Ollama's own counters."""
    sampler = ResourceSampler()
    sampler.start()
    started = time.perf_counter()
    error = None
    body = {}

    try:
        res = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False, "options": GEN_OPTIONS},
            timeout=REQUEST_TIMEOUT,
        )
        res.raise_for_status()
        body = res.json()
    except requests.RequestException as exc:
        error = str(exc)

    wall_ms = (time.perf_counter() - started) * 1000
    resources = sampler.stop()

    ns = 1_000_000  # nanoseconds -> milliseconds
    return {
        "answer": body.get("response", ""),
        "error": error,
        "latency_ms": round(wall_ms, 1),
        "total_duration_ms": round(body.get("total_duration", 0) / ns, 1),
        "load_duration_ms": round(body.get("load_duration", 0) / ns, 1),
        "prompt_eval_count": body.get("prompt_eval_count"),
        "prompt_eval_duration_ms": round(body.get("prompt_eval_duration", 0) / ns, 1),
        "eval_count": body.get("eval_count"),
        "eval_duration_ms": round(body.get("eval_duration", 0) / ns, 1),
        "resources": resources,
    }


# ── Retrieval (executed once, replayed to every model) ───────────────────────
def retrieve_all(questions):
    """
    Run retrieval once per knowledge question.

    The retriever is identical for all models, so retrieval quality is a
    property of the RAG layer, not of any model. Caching it here also
    guarantees every model sees byte-identical context.
    """
    cache = {}
    for q in questions:
        if q["category"] == "code_generation":
            continue
        res = requests.post(RETRIEVAL_URL, json={"question": q["question"]}, timeout=60)
        res.raise_for_status()
        body = res.json()
        chunks = body.get("context_chunks", [])
        cache[q["id"]] = {
            "context_chunks": chunks,
            "sources": body.get("sources", []),
            "context": "\n---\n".join(chunks),
        }
        print(f"  retrieved {q['id']}: {body.get('sources')}")
    return cache


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)

    with open(os.path.join(HERE, "eval_set.json"), encoding="utf-8") as f:
        eval_set = json.load(f)
    questions = eval_set["questions"]

    # Record the KB state so the run is reproducible and auditable.
    kb = requests.get(KB_INFO_URL, timeout=30).json()
    print(f"Knowledge base: {len(kb['documents'])} documents, {kb['total_chunks']} vectors")
    print(f"Questions: {len(questions)}   Models: {', '.join(MODELS)}\n")

    print("Retrieving context once per question (shared by all models)...")
    retrieval = retrieve_all(questions)
    print()

    results = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "models": MODELS,
        "gen_options": GEN_OPTIONS,
        "knowledge_base": {
            "documents": [d["filename"] for d in kb["documents"]],
            "vectors": kb["total_chunks"],
            "embedding_dimension": kb["embedding_dimension"],
            "index_type": kb["faiss_index_type"],
        },
        "retrieval": retrieval,
        "runs": {},
    }

    for model in MODELS:
        print(f"===== {model} =====")

        # Warm-up: load the model so its load time is not charged to Q1.
        warm = generate(model, "Reply with the single word: ready")
        residency = ollama_ps()
        print(f"  warm-up {warm['latency_ms']} ms; resident: {residency}")

        runs = []
        for i, q in enumerate(questions, 1):
            if q["category"] == "code_generation":
                prompt = build_code_prompt(q["question"])
                context = None
                sources = []
            else:
                r = retrieval[q["id"]]
                prompt = build_rag_prompt(r["context"], q["question"])
                context = r["context"]
                sources = r["sources"]

            out = generate(model, prompt)
            out.update({
                "id": q["id"],
                "category": q["category"],
                "question": q["question"],
                "prompt_chars": len(prompt),
                "retrieved_sources": sources,
                "context": context,
            })
            runs.append(out)

            status = "ERR" if out["error"] else "ok "
            print(
                f"  [{i:>2}/{len(questions)}] {q['id']:<4} {status} "
                f"{out['latency_ms']:>8.0f} ms  "
                f"in={out['prompt_eval_count']} out={out['eval_count']}"
            )

        results["runs"][model] = {
            "residency": residency,
            "warmup_ms": warm["latency_ms"],
            "results": runs,
        }
        print()

    results["finished_at"] = datetime.now(timezone.utc).isoformat()

    out_path = os.path.join(RESULTS_DIR, "raw_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    sys.exit(main())
