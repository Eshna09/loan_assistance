"""
score.py — compute every Exercise 3 metric from raw_results.json.

Each metric is defined here in code, so the number in the report is traceable
to the exact rule that produced it.

QUALITY
  1. Correctness / Accuracy
       Each knowledge question carries `key_facts` (a fact may list alternative
       phrasings separated by '|') and a `min_facts` threshold.
         fact_coverage = matched_facts / total_facts
         correct       = matched_facts >= min_facts
         Accuracy      = correct answers / knowledge questions
       Matching is case-insensitive substring on whitespace-normalised text.

  2. Relevance
       Cosine similarity between the MiniLM embedding of the answer and of the
       question — the same all-MiniLM-L6-v2 model the application uses for
       retrieval. Answers that drift off-topic score lower. Reported as the
       mean over knowledge questions.

  3. Retrieval Quality
       A property of the RAG layer, identical for every model because the same
       cached retrieval is replayed to all of them.
         Recall@3 = questions where >=1 expected source is in the top-3 / total
         MRR      = mean of 1/rank of the first expected source
       Reported once, not per model.

  4. Hallucination Rate — two independently measurable components.
       a. Refusal-failure rate (out-of-KB questions):
            the model did NOT refuse a question with no supporting context.
            Refusal = the fallback phrase, or any of REFUSAL_PATTERNS.
       b. Unsupported-number rate (knowledge questions):
            numeric tokens present in the answer but absent from the retrieved
            context, per answer. Invented figures are the highest-risk
            hallucination for a lending assistant. Markdown list enumeration
            ("1." / "2)") is stripped first - it is formatting, not a claim.
       Also reported: groundedness = share of the answer's content words that
       appear in the retrieved context.

  5. Test-Pass Rate (code generation)
       The fenced code block is extracted, executed in a subprocess with a
       timeout, and each recorded assertion is run.
         test_pass_rate = assertions passed / assertions run
         task_pass_rate = tasks where every assertion passed / tasks

PERFORMANCE
  6. Response Latency — wall-clock ms per request, measured client-side around
     the HTTP call, excluding model load (each model is warmed up first).
     Reported as mean, median and p95.

  7. Token Usage — Ollama's own counters: prompt_eval_count (input tokens) and
     eval_count (output tokens). Throughput = eval_count / eval_duration.

  8. CPU / GPU / Memory — RSS and CPU% sampled at 4 Hz across ollama.exe and
     llama-server.exe during each generation; plus Ollama's reported resident
     size and the VRAM share (GPU vs CPU placement).
"""

import json
import os
import re
import statistics
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(HERE, "results")

# A refusal counts if the answer contains the fallback phrase or one of these.
REFUSAL_PATTERNS = [
    "not available in my knowledge base",
    "cannot be found in the context",
    "can not be found in the context",
    "is not in the context",
    "not found in the context",
    "not provided in the context",
    "does not contain",
    "no information about",
    "does not provide information",
    "context does not",
    "i don't have information",
    "i do not have information",
    "unable to answer",
]

# Declines that stop short of citing the knowledge base. These still answer from
# parametric memory rather than context, but they do not assert invented facts.
DECLINE_PATTERNS = [
    "cannot provide",
    "can not provide",
    "can't provide",
    "unable to provide",
    "i cannot give",
    "i can't give",
    "not able to provide",
    "cannot recommend",
    "can't recommend",
    "consult a financial advisor",
    "consult a professional",
]

STOPWORDS = set("""a an the and or but if then than that this these those of to in on for with without
by from as at is are was were be been being it its it's do does did not no nor so such can could may
might will would shall should must have has had you your i we they he she them their our us me my
what which who whom when where why how about into over under more most less least other some any each
both few many own same very just also only their there here""".split())


# ── helpers ──────────────────────────────────────────────────────────────────
def norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())


def fact_matched(fact: str, answer_norm: str) -> bool:
    """A fact is satisfied if any of its '|'-separated alternatives appears."""
    return any(alt.strip() in answer_norm for alt in fact.split("|") if alt.strip())


def is_refusal(answer: str) -> bool:
    """A proper refusal — the model cites the absence of supporting context."""
    a = norm(answer)
    return any(p in a for p in REFUSAL_PATTERNS)


def is_soft_decline(answer: str) -> bool:
    a = norm(answer)
    return any(p in a for p in DECLINE_PATTERNS)


def classify_out_of_kb(answer: str) -> str:
    """
    proper_refusal — declines and cites the knowledge base (the desired behaviour)
    soft_decline   — declines to advise but still answers from outside the context
    fabricated     — answers the question outright from parametric memory
    """
    if is_refusal(answer):
        return "proper_refusal"
    if is_soft_decline(answer):
        return "soft_decline"
    return "fabricated"


NUM_RE = re.compile(r"\d+(?:\.\d+)?")

# Markdown enumeration ("1." / "2)" at the start of a line) is formatting, not a
# factual claim. Counting it as an invented figure penalises models that answer
# in lists, which is what an early version of this metric did.
LIST_MARKER_RE = re.compile(r"^[\s>*-]*\d+[.)]\s", re.MULTILINE)


def strip_list_markers(text: str) -> str:
    return LIST_MARKER_RE.sub("", text or "")


def numbers_in(text: str, ignore_list_markers: bool = False) -> set:
    """
    Numeric tokens, normalised so '10' and '10.0' compare equal.

    With ignore_list_markers, leading enumeration is removed first so only
    numbers that form part of a claim are counted.
    """
    source = strip_list_markers(text) if ignore_list_markers else (text or "")
    out = set()
    for m in NUM_RE.findall(source):
        try:
            out.add(float(m))
        except ValueError:
            continue
    return out


def content_words(text: str) -> list:
    words = re.findall(r"[a-z]{3,}", norm(text))
    return [w for w in words if w not in STOPWORDS]


def groundedness(answer: str, context: str) -> float:
    """Share of the answer's content words that also occur in the context."""
    aw = content_words(answer)
    if not aw:
        return 0.0
    cw = set(content_words(context))
    return sum(1 for w in aw if w in cw) / len(aw)


CODE_FENCE = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_code(answer: str) -> str:
    """Prefer a fenced block; fall back to the text from the first 'def'."""
    blocks = CODE_FENCE.findall(answer or "")
    if blocks:
        return max(blocks, key=len).strip()
    idx = (answer or "").find("def ")
    return answer[idx:].strip() if idx != -1 else ""


def run_code_tests(code: str, tests: list) -> dict:
    """
    Execute generated code in a separate interpreter and check each assertion.

    Runs in a subprocess with a timeout so a model that emits an infinite loop
    cannot stall the scoring run.
    """
    if not code.strip():
        return {"passed": 0, "total": len(tests), "detail": ["no code emitted"] * len(tests)}

    harness = [
        "import json, math",
        code,
        "results = []",
    ]
    for t in tests:
        harness.append(
            "try:\n"
            f"    _v = {t['call']}\n"
            f"    results.append(abs(float(_v) - {t['expected']!r}) <= {t['tolerance']!r})\n"
            "except Exception as _e:\n"
            "    results.append(False)"
        )
    harness.append("print(json.dumps(results))")

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write("\n".join(harness))
        path = f.name

    try:
        proc = subprocess.run(
            [sys.executable, path], capture_output=True, text=True, timeout=20
        )
        line = (proc.stdout or "").strip().splitlines()
        flags = json.loads(line[-1]) if line else []
    except (subprocess.TimeoutExpired, json.JSONDecodeError, IndexError):
        flags = []
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    if len(flags) != len(tests):
        flags = [False] * len(tests)

    return {
        "passed": sum(1 for x in flags if x),
        "total": len(tests),
        "detail": [
            f"{t['call']} -> {'PASS' if ok else 'FAIL'}" for t, ok in zip(tests, flags)
        ],
    }


def percentile(values, p):
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


# ── retrieval quality (model-independent) ────────────────────────────────────
def score_retrieval(questions, retrieval):
    hits, rr, rows = 0, [], []
    considered = 0
    for q in questions:
        expected = q.get("expected_sources") or []
        if not expected or q["id"] not in retrieval:
            continue
        considered += 1
        got = retrieval[q["id"]]["sources"]
        rank = next((i + 1 for i, s in enumerate(got) if s in expected), None)
        if rank:
            hits += 1
            rr.append(1 / rank)
        else:
            rr.append(0.0)
        rows.append({
            "id": q["id"],
            "expected": expected,
            "retrieved": got,
            "hit_rank": rank,
        })
    return {
        "questions_considered": considered,
        "recall_at_3": round(hits / considered, 4) if considered else None,
        "mrr": round(statistics.mean(rr), 4) if rr else None,
        "per_question": rows,
    }


# ── per-model scoring ────────────────────────────────────────────────────────
def score_model(model, run, questions_by_id, embed):
    rows = []
    for r in run["results"]:
        q = questions_by_id[r["id"]]
        answer = r.get("answer") or ""
        row = {
            "id": r["id"],
            "category": r["category"],
            "latency_ms": r["latency_ms"],
            "prompt_tokens": r.get("prompt_eval_count") or 0,
            "output_tokens": r.get("eval_count") or 0,
            "eval_duration_ms": r.get("eval_duration_ms") or 0,
            "resources": r.get("resources") or {},
            "answer_chars": len(answer),
            "error": r.get("error"),
        }

        if r["category"] == "code_generation":
            code = extract_code(answer)
            row["code_extracted"] = bool(code)
            row.update(run_code_tests(code, q["tests"]))
            row["code"] = code
        elif r["category"] == "out_of_kb":
            row["outcome"] = classify_out_of_kb(answer)
            row["refused"] = row["outcome"] == "proper_refusal"
            # Anything that is not a proper refusal answered from outside the KB.
            row["hallucinated"] = not row["refused"]
            row["fabricated"] = row["outcome"] == "fabricated"
        else:
            facts = q["key_facts"]
            a = norm(answer)
            matched = [f for f in facts if fact_matched(f, a)]
            row["facts_total"] = len(facts)
            row["facts_matched"] = len(matched)
            row["fact_coverage"] = round(len(matched) / len(facts), 4)
            row["correct"] = len(matched) >= q["min_facts"]
            row["missed_facts"] = [f for f in facts if f not in matched]

            ctx = r.get("context") or ""
            row["groundedness"] = round(groundedness(answer, ctx), 4)
            unsupported = numbers_in(answer, ignore_list_markers=True) - numbers_in(ctx)
            row["unsupported_numbers"] = sorted(unsupported)
            row["has_unsupported_number"] = bool(unsupported)
            row["relevance"] = round(embed(answer, q["question"]), 4)
            # A model that refuses an answerable question is not hallucinating,
            # but it is failing the task — tracked separately from correctness.
            row["refused_answerable"] = is_refusal(answer)

        rows.append(row)

    knowledge = [r for r in rows if r["category"] not in ("code_generation", "out_of_kb")]
    oob = [r for r in rows if r["category"] == "out_of_kb"]
    code = [r for r in rows if r["category"] == "code_generation"]
    latencies = [r["latency_ms"] for r in rows]

    tests_passed = sum(r["passed"] for r in code)
    tests_total = sum(r["total"] for r in code)
    tasks_passed = sum(1 for r in code if r["total"] and r["passed"] == r["total"])

    residency = run.get("residency") or []
    resident = next((m for m in residency if m.get("name") == model), None) or {}

    out_tokens = sum(r["output_tokens"] for r in rows)
    eval_ms = sum(r["eval_duration_ms"] for r in rows)
    peaks = [r["resources"].get("peak_rss_mb") for r in rows if r["resources"].get("peak_rss_mb")]
    cpus = [r["resources"].get("mean_cpu_percent") for r in rows if r["resources"].get("mean_cpu_percent") is not None]

    return {
        "model": model,
        "residency": run.get("residency"),
        "quality": {
            "accuracy": round(sum(1 for r in knowledge if r["correct"]) / len(knowledge), 4),
            "correct_count": sum(1 for r in knowledge if r["correct"]),
            "knowledge_questions": len(knowledge),
            "mean_fact_coverage": round(statistics.mean(r["fact_coverage"] for r in knowledge), 4),
            "mean_relevance": round(statistics.mean(r["relevance"] for r in knowledge), 4),
            "mean_groundedness": round(statistics.mean(r["groundedness"] for r in knowledge), 4),
            "refused_answerable_count": sum(1 for r in knowledge if r["refused_answerable"]),
        },
        "hallucination": {
            "out_of_kb_questions": len(oob),
            "refusals": sum(1 for r in oob if r["refused"]),
            "soft_declines": sum(1 for r in oob if r.get("outcome") == "soft_decline"),
            "fabrications": sum(1 for r in oob if r.get("fabricated")),
            "refusal_failure_rate": round(sum(1 for r in oob if r["hallucinated"]) / len(oob), 4) if oob else None,
            "fabrication_rate": round(sum(1 for r in oob if r.get("fabricated")) / len(oob), 4) if oob else None,
            "unsupported_number_rate": round(
                sum(1 for r in knowledge if r["has_unsupported_number"]) / len(knowledge), 4
            ),
        },
        "code": {
            "tasks": len(code),
            "code_blocks_extracted": sum(1 for r in code if r.get("code_extracted")),
            "tests_passed": tests_passed,
            "tests_total": tests_total,
            "test_pass_rate": round(tests_passed / tests_total, 4) if tests_total else None,
            "tasks_fully_passed": tasks_passed,
            "task_pass_rate": round(tasks_passed / len(code), 4) if code else None,
        },
        "performance": {
            "mean_latency_ms": round(statistics.mean(latencies), 1),
            "median_latency_ms": round(statistics.median(latencies), 1),
            "p95_latency_ms": round(percentile(latencies, 0.95), 1),
            "min_latency_ms": round(min(latencies), 1),
            "max_latency_ms": round(max(latencies), 1),
            "total_prompt_tokens": sum(r["prompt_tokens"] for r in rows),
            "total_output_tokens": out_tokens,
            "mean_output_tokens": round(out_tokens / len(rows), 1),
            "output_tokens_per_sec": round(out_tokens / (eval_ms / 1000), 2) if eval_ms else None,
        },
        "resources": {
            "peak_rss_mb": max(peaks) if peaks else None,
            "mean_peak_rss_mb": round(statistics.mean(peaks), 1) if peaks else None,
            "mean_cpu_percent": round(statistics.mean(cpus), 1) if cpus else None,
            "resident_mb": resident.get("resident_mb"),
            "vram_mb": resident.get("vram_mb"),
            "gpu_percent": resident.get("gpu_percent"),
        },
        "per_question": rows,
    }


def main():
    with open(os.path.join(HERE, "eval_set.json"), encoding="utf-8") as f:
        eval_set = json.load(f)
    with open(os.path.join(RESULTS_DIR, "raw_results.json"), encoding="utf-8") as f:
        raw = json.load(f)

    questions = eval_set["questions"]
    by_id = {q["id"]: q for q in questions}

    # Relevance uses the application's own embedding model.
    print("Loading MiniLM for relevance scoring...")
    from sentence_transformers import SentenceTransformer
    import numpy as np

    st = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    def embed(a: str, b: str) -> float:
        if not a.strip() or not b.strip():
            return 0.0
        v = st.encode([a, b])
        na, nb = np.linalg.norm(v[0]), np.linalg.norm(v[1])
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(v[0], v[1]) / (na * nb))

    summary = {
        "generated_at": raw.get("finished_at"),
        "knowledge_base": raw["knowledge_base"],
        "gen_options": raw["gen_options"],
        "eval_set": {
            "total_questions": len(questions),
            "by_category": {
                c: sum(1 for q in questions if q["category"] == c)
                for c in eval_set["categories"]
            },
        },
        "retrieval_quality": score_retrieval(questions, raw["retrieval"]),
        "models": {},
    }

    for model in raw["models"]:
        print(f"Scoring {model}...")
        summary["models"][model] = score_model(model, raw["runs"][model], by_id, embed)

    out = os.path.join(RESULTS_DIR, "summary.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Wrote {out}")


if __name__ == "__main__":
    sys.exit(main())
