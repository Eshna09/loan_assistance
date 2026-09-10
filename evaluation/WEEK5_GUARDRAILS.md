# Week 5 — Input Guardrails, Evidence Guardrails & AI Output Testing

## 1. Objective

Week 5 makes the Loan Knowledge Assistance system **reliable and controlled**.
The core problem with a raw RAG + LLM pipeline is that it will attempt to answer
*anything* — out-of-scope questions, questions with no supporting evidence, and
questions where the retrieved context is too thin to ground the answer.

This work adds three layers of control without breaking any existing functionality:

```
USER
 ↓
INPUT GUARDRAIL        ← rejects out-of-scope, empty, too-long
 ↓
RAG RETRIEVAL          ← unchanged MiniLM + FAISS pipeline
 ↓
EVIDENCE CHECK         ← abstains when KB has nothing relevant
 ↓
LLM (Code Llama)       ← only called when evidence exists
 ↓
AI OUTPUT TESTING      ← validates relevance, grounding, format
 ↓
┌──────────────┴──────────────┐
↓                              ↓
PASS                          FAIL
↓                              ↓
FINAL ANSWER            CONTROLLED RESPONSE
```

---

## 2. Problems Identified (Without Guardrails)

| Problem | Example | Risk |
|---|---|---|
| Out-of-scope questions answered | "What is the price of Bitcoin?" | LLM answers from parametric memory |
| Empty input crashes or returns garbage | `""` | Uncontrolled error or meaningless response |
| Excessively long input | 2000-char question | Token waste, prompt injection risk |
| LLM called even when KB has nothing | Very specific bank rates | Hallucination |
| No output validation | Any answer | Unsupported claims returned to user |

---

## 3. Guardrail Design

All guardrail logic lives in `services/app_service/guardrails.py`.
It is imported by `services/app_service/main.py` and applied in the
`/ask` and `/ask/debug` endpoints.

No existing endpoints, services, or data flows were removed or replaced.

---

## 4. Input Guardrails (`check_input`)

Applied **before** any retrieval or LLM call.

### A. Empty / whitespace-only input
```
Status: reject_empty
Response: "Please enter a question. The input cannot be empty."
```

### B. Excessive length
```
Status: reject_length
Limit: MAX_INPUT_LENGTH (default 1000 chars, configurable via env)
Response: "Your question is too long (N characters). Please keep it under 1000 characters."
```

### C. Out-of-scope patterns (high-confidence rejections)
```
Status: reject_scope
Patterns: bitcoin, crypto, weather, sports results, recipe, movie, election, capital city …
Response: "I can only assist with questions related to the loan information available in the knowledge base."
```

### D. General-knowledge patterns without loan keywords
```
Status: reject_scope
Examples: "What is the capital of Australia?", "Write a Python program to sort a list."
```

---

## 5. Evidence Guardrail (`check_evidence_sufficiency`)

Applied **after** retrieval, **before** LLM call.

```python
if not chunks or distances[0] > MAX_EVIDENCE_DISTANCE:
    return False, "I couldn't find sufficient information in the knowledge base..."
```

- `MIN_EVIDENCE_CHUNKS` (default: 1) — minimum chunks required
- `MAX_EVIDENCE_DISTANCE` (default: 1.2) — maximum acceptable L2 distance for top-1 chunk

If evidence is insufficient: **LLM is not called**. A controlled abstention is returned.

---

## 6. Output Validation (`validate_output`)

Applied **after** LLM generation, **before** returning to user.

| Check | Method | PASS condition |
|---|---|---|
| Relevance | Word overlap between question and answer | Overlap ≥ 8% |
| Grounding | `validate_grounding()` from evidence.py | Status ≠ "unsupported" |
| Unsupported claims | Same as grounding | No unsupported numeric/factual claims |
| Expected behavior | Refusal detection | Matches expected (answer/refusal/abstention) |
| Format | Length check | Answer not empty, not > 8000 chars |

Result is attached to every `/ask` response in `output_validation` field.

---

## 7. API Response Structure

Every `/ask` response now includes a `guardrail` field:

```json
{
  "question": "...",
  "answer": "...",
  "blocked": false,
  "guardrail": {
    "input_scope": "pass",
    "input_length": "pass",
    "input_empty": "pass",
    "input_check": "pass",
    "evidence_sufficient": "pass",
    "action": "allow"
  },
  "output_validation": {
    "relevance": "pass",
    "grounding": "pass",
    "unsupported_claims": "pass",
    "expected_behavior": "pass",
    "format": "pass",
    "overall": "pass"
  }
}
```

For blocked requests:
```json
{
  "blocked": true,
  "answer": null,
  "controlled_response": "I can only assist with questions related to loan information...",
  "guardrail": {
    "input_check": "reject_scope",
    "action": "rejected",
    "reason": "I can only assist with..."
  }
}
```

---

## 8. Evaluation Dataset (Updated — v2.0)

The dataset was updated from 29 to **30 questions** covering all 17 required categories.

### Category Distribution

| # | Category | Questions |
|---|---|---|
| 1 | policy_explanation | 1 |
| 2 | information_retrieval | 7 |
| 3 | comparison | 2 |
| 4 | conflict_detection | 1 |
| 5 | version_resolution | 1 |
| 6 | eligibility_analysis | 1 |
| 7 | fee_calculation | 1 |
| 8 | rag_based | 1 |
| 9 | out_of_scope | 4 |
| 10 | evidence_grounding | 1 |
| 11 | code_explanation | 1 |
| 12 | code_retrieval | 1 |
| 13 | dependency_understanding | 1 |
| 14 | bug_analysis | 1 |
| 15 | code_generation | 4 |
| 16 | refactoring | 1 |
| 17 | rag_based_code_doc | 1 |

### Codebase Questions (based on real implementation)

All repository questions reference **actual** files, functions, and endpoints:

| ID | Question | Source File |
|---|---|---|
| CE01 | What does /ask/debug do? | `services/app_service/main.py` |
| CR01 | Which file handles Ollama communication? | `services/llm_service/main.py` |
| DU01 | Which services are involved in /ask? | `app_service`, `retrieval_service`, `llm_service` |
| BA01 | What causes answer=null with ollama_error? | `app_service/main.py`, `llm_service/main.py` |
| RF01 | Improve chunk_text for empty input | `services/common/chunking.py` |
| RD01 | What does ARCHITECTURE.md say about the pipeline? | `ARCHITECTURE.md` |

---

## 9. PASS/FAIL Criteria

| Category | PASS if |
|---|---|
| Supported question | Relevant, sufficient evidence, grounded answer |
| Out-of-scope | Request refused, no LLM answer generated |
| Unsupported | System abstains, no unsupported answer |
| Conflict detection | Conflict correctly identified |
| Version resolution | Correct current version selected by metadata |
| Evidence grounding | Answer traceable to supporting chunks |
| Code explanation | Correctly describes actual implementation |
| Code retrieval | Correct file/function/service identified |
| Dependency | Actual service chain correctly described |
| Bug analysis | Identified cause consistent with actual code |
| Code generation | Generated code passes unit tests |
| Refactoring | Suggestion applicable to actual code |

---

## 10. Without Guardrail vs With Guardrail

### Without Guardrail
- "What is the current price of Bitcoin?" → LLM answers with general crypto knowledge
- `""` (empty) → Sent to retrieval, may cause error or meaningless embedding
- 1500-char question → Accepted, large token usage, prompt injection risk
- "What is the exact rate at HDFC Bank?" → LLM invents a rate not in the KB

### With Guardrail

| Input | Action | Response |
|---|---|---|
| "What is the price of Bitcoin?" | reject_scope | "I can only assist with loan information…" |
| `""` | reject_empty | "Please enter a question…" |
| 1500-char input | reject_length | "Your question is too long…" |
| "What is the HDFC Bank rate?" | allow → LLM abstains | "This information is not available…" |
| "What is an EMI?" | allow → grounded answer | Factual answer from loan_repayment.txt |

---

## 11. Guardrail Effectiveness Formula

```
Guardrail Effectiveness = (Correctly controlled cases / Total guardrail test cases) × 100
```

All metrics are computed from **actual test execution** in `run_guardrail_tests.py`.

Additional metrics:
- Out-of-scope rejection rate
- Input validation pass rate (empty + length)
- Supported question pass rate
- Output validation overall pass rate

---

## 12. Files Created / Modified

| File | Change |
|---|---|
| `services/app_service/guardrails.py` | NEW — all guardrail logic |
| `services/app_service/main.py` | MODIFIED — guardrail calls in /ask and /ask/debug |
| `evaluation/eval_set.json` | UPDATED — 30 questions, all 17 categories |
| `evaluation/validate_dataset.py` | NEW — dataset validation script |
| `evaluation/week5_guardrail_tests.json` | NEW — 15 guardrail test cases |
| `evaluation/run_guardrail_tests.py` | NEW — automated test runner |
| `evaluation/demo_guardrails.py` | NEW — without vs with guardrail demo |
| `evaluation/WEEK5_GUARDRAILS.md` | NEW — this document |
| `frontend/src/components/RAGDemo.jsx` | MODIFIED — GuardrailBanner component added |

---

## 13. How to Run the Tests

### Prerequisites
Start all services first:
```bash
start_services.bat         # or: docker compose up -d
ollama serve               # ensure Ollama is running
```

### Validate the dataset
```bash
python evaluation/validate_dataset.py
```

### Run guardrail tests (with guardrails)
```bash
python evaluation/run_guardrail_tests.py
```

### Run guardrail tests (baseline — no guardrail evaluation)
```bash
python evaluation/run_guardrail_tests.py --no-guardrail
```

### Run the without/with guardrail demo
```bash
python evaluation/demo_guardrails.py
```

### Run the original Week 4 model evaluation (unchanged)
```bash
python evaluation/run_eval.py    # runs all 4 models
python evaluation/score.py       # computes metrics
```

Results are written to `evaluation/results/`.
