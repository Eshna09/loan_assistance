"""
repo_analysis.py - Repository/codebase evidence retrieval.

When a question is classified as CODEBASE intent, this module
provides context by reading actual project files instead of
querying the loan FAISS index.

It uses simple keyword-based file selection to find the most
relevant files for the question, then returns their content
as context for the LLM.
"""

import os
import re

# Root of the project (two levels up from this file)
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))

# Key project files indexed by their role/keywords
_REPO_FILES = {
    "services/app_service/main.py": [
        "ask", "endpoint", "orchestrat", "app service", "appservice",
        "api", "route", "handler", "application service", "playground",
        "kb/upload", "kb/info", "health",
    ],
    "services/app_service/guardrails.py": [
        "guardrail", "scope", "input check", "evidence check",
        "validate", "block", "reject", "intent",
    ],
    "services/app_service/evidence.py": [
        "evidence", "conflict", "grounding", "version resolution",
        "detect_conflicts", "resolve_version", "validate_grounding",
        "field_synonyms",
    ],
    "services/retrieval_service/main.py": [
        "faiss", "retrieval", "embedding", "minilm", "retrieve",
        "index", "rebuild", "ensure_fresh", "vector",
    ],
    "services/data_service/main.py": [
        "data service", "document", "upload", "chunk", "chunking",
        "version", "kb_dir", "upload_dir", "extract_text",
    ],
    "services/llm_service/main.py": [
        "llm service", "ollama", "generate", "codellama",
        "llm", "language model",
    ],
    "services/common/chunking.py": [
        "chunking", "chunk_text", "chunk size", "overlap", "chunk",
    ],
    "services/common/prompts.py": [
        "prompt", "rag prompt", "build_rag_prompt", "fallback phrase",
        "context separator",
    ],
    "services/app_service/source_graph.py": [
        "source graph", "provenance", "source_graph",
    ],
    "ARCHITECTURE.md": [
        "architecture", "documentation", "doc", "readme", "pipeline",
        "service communication", "docker", "image", "volume",
        "request flow", "rag pipeline",
    ],
    "docker-compose.yml": [
        "docker", "compose", "container", "image", "volume",
        "network", "port",
    ],
}

# Maximum chars to read from each file (to keep context manageable)
_MAX_CHARS_PER_FILE = 3000
# Maximum total context chars
_MAX_TOTAL_CHARS = 8000


def _score_file(q_lower: str, keywords: list) -> int:
    """Count how many keywords appear in the question."""
    return sum(1 for kw in keywords if kw in q_lower)


def _read_file_excerpt(rel_path: str, max_chars: int = _MAX_CHARS_PER_FILE) -> str:
    """Read up to max_chars from a project file."""
    full_path = os.path.join(_ROOT, rel_path.replace("/", os.sep))
    if not os.path.isfile(full_path):
        return ""
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_chars * 2)  # read a bit more then trim
        # If it's a Python file, try to keep complete function/class definitions
        if rel_path.endswith(".py") and len(content) > max_chars:
            content = content[:max_chars]
            # Trim to last complete line
            last_newline = content.rfind("\n")
            if last_newline > max_chars // 2:
                content = content[:last_newline]
        return content[:max_chars]
    except Exception:
        return ""


def get_repo_context(question: str, top_k: int = 3) -> dict:
    """
    Select the most relevant project files for the question and
    return their content as context for the LLM.

    Returns:
      {
        "context": str,          # combined file contents
        "sources": list[str],    # file paths used
        "chunks": list[dict],    # chunk-like records for evidence display
        "sufficient": bool,      # whether any relevant files were found
      }
    """
    q_lower = question.lower()

    # Score each file
    scored = []
    for rel_path, keywords in _REPO_FILES.items():
        score = _score_file(q_lower, keywords)
        if score > 0:
            scored.append((score, rel_path))

    # Sort by score descending, take top_k
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = [path for _, path in scored[:top_k]]

    # Always include ARCHITECTURE.md for documentation questions
    q_doc = any(w in q_lower for w in ["architecture", "documentation", "doc", "readme"])
    if q_doc and "ARCHITECTURE.md" not in selected:
        selected.insert(0, "ARCHITECTURE.md")
        selected = selected[:top_k]

    if not selected:
        # Fallback: include the two most-used files
        selected = ["services/app_service/main.py", "ARCHITECTURE.md"]

    # Read file contents
    parts = []
    sources = []
    chunks = []
    total_chars = 0

    for rel_path in selected:
        content = _read_file_excerpt(rel_path)
        if not content:
            continue
        remaining = _MAX_TOTAL_CHARS - total_chars
        if remaining <= 0:
            break
        excerpt = content[:remaining]
        parts.append(f"### File: {rel_path}\n\n{excerpt}")
        sources.append(rel_path)
        chunks.append({
            "text": excerpt[:300],
            "source": rel_path,
            "chunk_id": len(chunks),
            "document_type": "codebase",
            "version": "current",
        })
        total_chars += len(excerpt)

    context = "\n\n---\n\n".join(parts)

    return {
        "context": context,
        "sources": sources,
        "chunks": chunks,
        "sufficient": bool(parts),
    }


def build_repo_prompt(context: str, question: str) -> str:
    """Build a prompt for codebase questions."""
    return (
        "You are an expert software engineer assistant for the Loan Knowledge Assistance project.\n"
        "Answer the user's question using ONLY the provided repository files and code.\n"
        "Be specific and reference actual file names, function names, class names, and line logic.\n"
        "If the answer cannot be determined from the provided files, say:\n"
        "'I could not find sufficient information in the repository to answer this question.'\n"
        "\n"
        f"Repository Context:\n{context}\n"
        "\n"
        f"Question:\n{question}\n"
        "\n"
        "Answer:"
    )
