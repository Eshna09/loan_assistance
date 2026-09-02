"""
code_rag_probe.py — Exercise 6: can this LLM + RAG system understand a codebase?

Indexes THIS repository with the application's own pipeline (chunk_text at
300/50, all-MiniLM-L6-v2, FAISS IndexFlatL2) into a separate in-process index,
then asks ten questions that require relating multiple files, modules or
components to each other.

Each question carries a hand-verified ground-truth file set, so two things are
measured separately:

  retrieval file recall  did the retriever surface the right FILES at all?
  answer file recall     did the model NAME the right files in its response?

Separating them distinguishes "the retriever never found it" from "the model had
it and could not reason about it" - the same split used in the Exercise 5
analysis.

Every question is run at top_k=3 (the application's real setting) and again at
top_k=8, to test whether simply supplying more context repairs the failures.

Writes CODEBASE_UNDERSTANDING.md. Requires host Ollama on :11434.
"""

import json
import os
import re
import sys
import time

import numpy as np
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.environ.get("PROBE_MODEL", "llama3.2:latest")
GEN_OPTIONS = {"temperature": 0, "seed": 42, "num_predict": 400, "top_p": 1.0}

CHUNK_SIZE, OVERLAP = 300, 50  # the application's own parameters

INDEX_GLOBS = [
    ("services", (".py",)),
    ("backend", (".py",)),
    (os.path.join("frontend", "src"), (".jsx", ".js")),
    ("evaluation", (".py",)),
]
ROOT_FILES = ["docker-compose.yml", "frontend/nginx.conf", "frontend/vite.config.js"]

SKIP_DIRS = {"__pycache__", "node_modules", "dist", ".git", "results"}

# This script and the Exercise 5 write-up both contain ground-truth file lists and
# commentary about the repository's structure. Indexing them leaks the answer key:
# an early run had the model reply "these components are listed as part of the R04
# scenario in evaluation/code_rag_probe.py". Excluded so the probe measures code
# understanding rather than answer retrieval.
SKIP_FILES = {"evaluation/code_rag_probe.py", "evaluation/rag_analysis.py"}


# ── the application's chunker, unchanged ─────────────────────────────────────
def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=OVERLAP):
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + chunk_size])
        start += (chunk_size - overlap)
    return chunks


def collect_files():
    files = []
    for sub, exts in INDEX_GLOBS:
        base = os.path.join(REPO, sub)
        if not os.path.isdir(base):
            continue
        for root, dirs, names in os.walk(base):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for n in sorted(names):
                if n.endswith(exts):
                    full = os.path.join(root, n)
                    files.append(os.path.relpath(full, REPO).replace("\\", "/"))
    for rel in ROOT_FILES:
        full = os.path.join(REPO, rel.replace("/", os.sep))
        if os.path.isfile(full):
            files.append(rel)
    return sorted(set(files) - SKIP_FILES)


# ── questions with hand-verified ground truth ────────────────────────────────
QUESTIONS = [
    {
        "id": "R01",
        "kind": "multi-file feature",
        "q": "Which files are involved in handling a document upload?",
        "expect": [
            "frontend/src/components/KnowledgeBase.jsx",
            "frontend/src/services/api.js",
            "services/app_service/main.py",
            "services/data_service/main.py",
            "services/retrieval_service/main.py",
        ],
    },
    {
        "id": "R02",
        "kind": "call relationship",
        "q": "Which service calls the LLM service, and from which file?",
        "expect": ["services/app_service/main.py", "services/llm_service/main.py"],
    },
    {
        "id": "R03",
        "kind": "cross-component flow",
        "q": "What happens, step by step and across which files, after a user submits a question in the dashboard?",
        "expect": [
            "frontend/src/components/RAGDemo.jsx",
            "frontend/src/services/api.js",
            "services/app_service/main.py",
            "services/retrieval_service/main.py",
            "services/llm_service/main.py",
        ],
    },
    {
        "id": "R04",
        "kind": "impact analysis",
        "q": "Which components would be affected if the build_rag_prompt function were modified?",
        "expect": [
            "services/common/prompts.py",
            "services/app_service/main.py",
            "evaluation/run_eval.py",
        ],
    },
    {
        "id": "R05",
        "kind": "single-file lookup (control)",
        "q": "In which file is the FAISS index created?",
        "expect": ["services/retrieval_service/main.py", "backend/knowledge_base.py"],
    },
    {
        "id": "R06",
        "kind": "single-file lookup (control)",
        "q": "Where is CORS middleware configured?",
        "expect": ["services/app_service/main.py", "backend/main.py"],
    },
    {
        "id": "R07",
        "kind": "test coverage",
        "q": "Which test cases cover the retrieval logic?",
        "expect": [],
        "expect_none": True,
    },
    {
        "id": "R08",
        "kind": "reverse call lookup",
        "q": "Which functions call rebuild_index, and in which files?",
        "expect": ["services/retrieval_service/main.py", "backend/knowledge_base.py"],
    },
    {
        "id": "R09",
        "kind": "impact analysis",
        "q": "Which files would have to change to switch from Ollama to a different LLM runtime?",
        "expect": ["services/llm_service/main.py", "docker-compose.yml"],
    },
    {
        "id": "R10",
        "kind": "deployment wiring",
        "q": "How does the frontend reach the backend when running under Docker, and which files define that?",
        "expect": ["frontend/nginx.conf", "docker-compose.yml"],
    },
]


CODE_PROMPT = (
    "You are a code assistant answering questions about a software repository.\n"
    "Answer the question ONLY using the provided code context.\n"
    "Always name the specific file paths involved.\n"
    "If the answer cannot be found in the context, say:\n"
    "'This information is not available in my knowledge base.'\n"
    "\n"
    "Context:\n{context}\n"
    "\n"
    "Question:\n{question}\n"
    "\n"
    "Answer:"
)


def generate(prompt):
    started = time.perf_counter()
    res = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": MODEL, "prompt": prompt, "stream": False, "options": GEN_OPTIONS},
        timeout=300,
    )
    res.raise_for_status()
    body = res.json()
    return body.get("response", ""), (time.perf_counter() - started) * 1000


def files_named(answer, known_files):
    """Which indexed files the answer actually names (path or unambiguous basename)."""
    a = answer.lower()
    found = set()
    basename_owners = {}
    for f in known_files:
        basename_owners.setdefault(os.path.basename(f).lower(), []).append(f)

    for f in known_files:
        if f.lower() in a:
            found.add(f)

    for base, owners in basename_owners.items():
        # main.py is ambiguous across four services; only count unique basenames.
        if len(owners) == 1 and re.search(r"\b" + re.escape(base) + r"\b", a):
            found.add(owners[0])

    # "app_service/main.py" style partial paths
    for f in known_files:
        tail = "/".join(f.split("/")[-2:]).lower()
        if tail in a:
            found.add(f)
    return sorted(found)


def prf(expected, got):
    if not expected:
        return None, None
    e, g = set(expected), set(got)
    hit = e & g
    recall = len(hit) / len(e)
    precision = len(hit) / len(g) if g else 0.0
    return recall, precision


def main():
    print("Loading embedding model...")
    from sentence_transformers import SentenceTransformer
    import faiss

    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    files = collect_files()
    print(f"Indexing {len(files)} source files with chunk_size={CHUNK_SIZE}, overlap={OVERLAP}...")

    chunks, meta = [], []
    for rel in files:
        with open(os.path.join(REPO, rel.replace("/", os.sep)), encoding="utf-8", errors="replace") as f:
            text = f.read()
        for c in chunk_text(text):
            chunks.append(c)
            meta.append({"source": rel, "text": c})

    emb = model.encode(chunks, show_progress_bar=False)
    index = faiss.IndexFlatL2(384)
    index.add(np.array(emb, dtype=np.float32))
    print(f"Indexed {index.ntotal} chunks from {len(files)} files.\n")

    def retrieve(question, k):
        qv = model.encode([question])
        d, i = index.search(np.array(qv, dtype=np.float32), k)
        out = []
        for rank, idx in enumerate(i[0]):
            if idx < 0:
                continue
            out.append({**meta[idx], "distance": float(d[0][rank])})
        return out

    results = []
    for q in QUESTIONS:
        row = {**q, "runs": {}}
        for k in (3, 8):
            hits = retrieve(q["q"], k)
            ctx = "\n---\n".join(f"# {h['source']}\n{h['text']}" for h in hits)
            answer, ms = generate(CODE_PROMPT.format(context=ctx, question=q["q"]))

            retrieved_files = sorted({h["source"] for h in hits})
            named = files_named(answer, files)
            r_rec, _ = prf(q["expect"], retrieved_files)
            a_rec, a_prec = prf(q["expect"], named)

            row["runs"][k] = {
                "retrieved_files": retrieved_files,
                "distances": [round(h["distance"], 3) for h in hits],
                "answer": answer.strip(),
                "named_files": named,
                "retrieval_recall": r_rec,
                "answer_recall": a_rec,
                "answer_precision": a_prec,
                "latency_ms": round(ms, 1),
            }
            rr = "n/a" if r_rec is None else f"{r_rec * 100:3.0f}%"
            ar = "n/a" if a_rec is None else f"{a_rec * 100:3.0f}%"
            print(f"  {q['id']} k={k}  retrieval {rr}  answer {ar}  ({ms / 1000:.1f}s)")
        results.append(row)

    payload = {
        "model": MODEL,
        "chunk_size": CHUNK_SIZE,
        "overlap": OVERLAP,
        "files_indexed": len(files),
        "chunks_indexed": index.ntotal,
        "files": files,
        "gen_options": GEN_OPTIONS,
        "results": results,
    }
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    out = os.path.join(HERE, "results", "code_probe.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    sys.exit(main())
