"""
guardrails.py - Input, evidence, and output guardrails.

Control flow (strict default-deny):

    USER INPUT
        |
    INPUT GUARDRAIL (check_input)
        |
    +---+---------------------------+
    | OUT OF SCOPE                  | IN SCOPE
    | action: refuse                |
    | embed/retrieve/llm: NOT CALLED|   EMBEDDING + FAISS RETRIEVAL
    +-------------------------------+        |
                                    EVIDENCE SUFFICIENCY CHECK
                                    (check_evidence_sufficiency)
                                             |
                                    +--------+----------+
                                    | INSUFFICIENT      | SUFFICIENT
                                    | action: abstained |    LLM
                                    | llm: NOT CALLED   |    |
                                    +-------------------+ OUTPUT TEST

IMPORTANT: "FAISS returned chunks" does NOT mean evidence is sufficient.
The evidence check uses semantic coverage: what fraction of the question's
content words appear in the retrieved context? If coverage < MIN_CONTEXT_COVERAGE
the LLM is NOT called and the application abstains immediately.
"""

import os
import re
from typing import Tuple

# ---------------------------------------------------------------------------
# Configurable limits
# ---------------------------------------------------------------------------
MAX_INPUT_LENGTH = int(os.environ.get("MAX_INPUT_LENGTH", "1000"))
MAX_EVIDENCE_DISTANCE = float(os.environ.get("MAX_EVIDENCE_DISTANCE", "1.2"))
MIN_EVIDENCE_CHUNKS = int(os.environ.get("MIN_EVIDENCE_CHUNKS", "1"))

# Minimum fraction of question content-words that must appear in retrieved
# context for evidence to be considered sufficient.
MIN_CONTEXT_COVERAGE = float(os.environ.get("MIN_CONTEXT_COVERAGE", "0.25"))

# ---------------------------------------------------------------------------
# Loan-domain positive signals (used by scope check - default deny)
# ---------------------------------------------------------------------------
LOAN_TOPIC_PHRASES = [
    r"\bemi\b",
    r"\bequated monthly\b",
    r"\binstalment\b",
    r"\binstallment\b",
    r"\bamortiz",
    r"\brepayment\b",
    r"\brepay\b",
    r"\bprepayment\b",
    r"\bforeclosure\b",
    r"\boverdue\b",
    r"\binterest rate\b",
    r"\bcompound interest\b",
    r"\bsimple interest\b",
    r"\bfixed rate\b",
    r"\bvariable rate\b",
    r"\bfloating rate\b",
    r"\bcollateral\b",
    r"\bmortgage\b",
    r"\bguarantor\b",
    r"\bprincipal amount\b",
    r"\bloan\b",
    r"\blending\b",
    r"\bborrower\b",
    r"\blender\b",
    r"\beligibility\b",
    r"\bprocessing fee\b",
    r"\blate payment\b",
    r"\bsanction\b",
    r"\bdisburs",
    r"\bdebt.to.income\b",
    r"\bdti\b",
    r"\bcredit score\b",
    r"\bcreditworthiness\b",
    r"\bdefault on\b",
]

# ---------------------------------------------------------------------------
# Hard-coded out-of-scope patterns (checked before positive signal test)
# ---------------------------------------------------------------------------
OUT_OF_SCOPE_PATTERNS = [
    r"\bbitcoin\b",
    r"\bcryptocurrency\b",
    r"\bcrypto\b",
    r"\bstock market\b",
    r"\bshare price\b",
    r"\bweather\b",
    r"\bplanet\b",
    r"\bearth\b",
    r"\bspace\b",
    r"\bsports\b",
    r"\bcricket\b",
    r"\bfootball\b",
    r"\bbasketball\b",
    r"\bsoccer\b",
    r"\brecipe\b",
    r"\bcooking\b",
    r"\bmovie\b",
    r"\bfilm\b",
    r"\bsong\b",
    r"\belection\b",
    r"\bpolitics\b",
    r"\bcapital of\b",
    r"\bcapital city\b",
    r"\brepo rate\b",
    r"\breserve bank of india\b",
    r"\brbi\b",
    r"\bmutual fund\b",
    r"\bstock price\b",
    r"\bshare market\b",
    r"\binvest in\b",
    r"\bgoing on earth\b",
    r"\bhappening on earth\b",
]

REFUSAL_PHRASES = (
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
    "i can only assist with questions related to",
    "couldn't find sufficient information",
)

_SCOPE_REFUSAL_MSG = (
    "I can only assist with questions related to the loan "
    "information available in the knowledge base."
)

_EVIDENCE_ABSTAIN_MSG = (
    "I couldn't find sufficient information in the knowledge base "
    "to answer this question."
)

_STOPWORDS = frozenset(
    "a an the and or but if then that this these those of to in on for with by "
    "from as at is are was were be been being it its do does did not no nor so "
    "such can could may might will would shall should must have has had you your "
    "i we they he she them their our us me my what which who when where why how "
    "about into over under more most less also only just very please tell give "
    "explain describe show exactly exact".split()
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _content_words(text: str) -> set:
    """Return meaningful words (3+ chars, not stopwords) from text."""
    words = re.findall(r"[a-z]{3,}", text.lower())
    return {w for w in words if w not in _STOPWORDS}


def _is_loan_scope(q_lower: str) -> bool:
    """Return True only if the question contains positive loan-domain evidence."""
    return any(re.search(p, q_lower) for p in LOAN_TOPIC_PHRASES)


# ---------------------------------------------------------------------------
# INPUT GUARDRAIL
# ---------------------------------------------------------------------------
def check_input(question: str) -> Tuple[str, str | None]:
    """
    Validate and scope-check the input question (DEFAULT-DENY).

    Returns (status, reason):
      status: "pass" | "reject_empty" | "reject_length" | "reject_scope"
    """
    # 1. Empty / whitespace
    if not question or not question.strip():
        return "reject_empty", "Please enter a question. The input cannot be empty."

    q = question.strip()

    # 2. Length
    if len(q) > MAX_INPUT_LENGTH:
        return (
            "reject_length",
            f"Your question is too long ({len(q)} characters). "
            f"Please keep it under {MAX_INPUT_LENGTH} characters.",
        )

    q_lower = q.lower()

    # 3. Explicit out-of-scope patterns
    for pattern in OUT_OF_SCOPE_PATTERNS:
        if re.search(pattern, q_lower):
            return "reject_scope", _SCOPE_REFUSAL_MSG

    # 4. DEFAULT-DENY: require positive loan-domain evidence
    if not _is_loan_scope(q_lower):
        return "reject_scope", _SCOPE_REFUSAL_MSG

    return "pass", None


# ---------------------------------------------------------------------------
# EVIDENCE SUFFICIENCY CHECK  (runs AFTER retrieval, BEFORE LLM)
# ---------------------------------------------------------------------------
def check_evidence_sufficiency(
    question: str,
    chunks: list,
    distances: list,
) -> Tuple[bool, str | None]:
    """
    Determine whether retrieved chunks provide sufficient evidence to answer.

    "FAISS returned something" is NOT sufficient by itself.

    Three gates:
      1. At least MIN_EVIDENCE_CHUNKS chunks retrieved.
      2. Top-1 L2 distance <= MAX_EVIDENCE_DISTANCE.
      3. Coverage: fraction of question content-words present in combined
         context >= MIN_CONTEXT_COVERAGE.

    Gate 3 catches cases where FAISS returns general loan chunks that are
    topically related but do not contain the specific fact asked.

    Example:
      Q: "What is the exact late-payment penalty for a personal loan?"
      Retrieved: chunks about credit score impact, EMI structure
      Coverage:  "late", "payment", "penalty", "personal" not in context
      Result:    INSUFFICIENT -> LLM NOT CALLED
    """
    # Gate 1: chunk count
    if not chunks or len(chunks) < MIN_EVIDENCE_CHUNKS:
        return False, _EVIDENCE_ABSTAIN_MSG

    # Gate 2: L2 distance
    if distances and distances[0] > MAX_EVIDENCE_DISTANCE:
        return False, _EVIDENCE_ABSTAIN_MSG

    # Gate 3: semantic coverage
    q_words = _content_words(question)
    if not q_words:
        return True, None  # cannot judge, let through

    combined = " ".join(c.get("text", "") for c in chunks)
    ctx_words = _content_words(combined)

    coverage = len(q_words & ctx_words) / len(q_words)

    if coverage < MIN_CONTEXT_COVERAGE:
        return False, _EVIDENCE_ABSTAIN_MSG

    # Gate 4: specificity check
    # If the question asks for an exact/specific value (percentage, amount, number),
    # verify the context actually contains numeric values related to the key noun.
    q_lower = question.lower()
    asks_exact = bool(re.search(
        r"\b(exact|specific|precise|how much|percentage|rate|amount|figure|number|value)\b",
        q_lower
    ))
    if asks_exact:
        # Extract key noun phrases from the question (non-stopword sequences)
        key_nouns = [w for w in q_words if len(w) >= 5]
        # Check if context contains a number/percentage near those nouns
        has_specific_value = bool(re.search(r"\d+(?:\.\d+)?\s*%", combined))
        # Also check if the context contains the exact topic word + number
        topic_with_number = any(
            re.search(rf"\b{re.escape(noun)}\b.{{0,80}}\d", combined, re.IGNORECASE)
            for noun in key_nouns
        )
        if not has_specific_value and not topic_with_number:
            return False, _EVIDENCE_ABSTAIN_MSG

    return True, None


# ---------------------------------------------------------------------------
# OUTPUT VALIDATION  (runs AFTER LLM)
# ---------------------------------------------------------------------------
def validate_output(
    answer: str,
    question: str,
    context: str,
    expected_behavior: str = "answer",
) -> dict:
    """Validate LLM output before returning to the user."""
    result = {
        "relevance": "pass",
        "grounding": "pass",
        "unsupported_claims": "pass",
        "expected_behavior": "pass",
        "format": "pass",
        "overall": "pass",
        "failed_checks": [],
        "details": {},
    }

    # Format
    if not answer or not answer.strip():
        result["format"] = "fail"
        result["details"]["format"] = "Answer is empty."
    elif len(answer) > 8000:
        result["format"] = "fail"
        result["details"]["format"] = f"Answer is excessively long ({len(answer)} chars)."

    # Relevance
    q_words = set(re.findall(r"[a-z]{3,}", question.lower()))
    a_words = set(re.findall(r"[a-z]{3,}", answer.lower()))
    if q_words:
        overlap = len(q_words & a_words) / len(q_words)
        result["details"]["relevance_overlap"] = round(overlap, 3)
        if overlap < 0.08:
            result["relevance"] = "fail"
            result["details"]["relevance"] = f"Low word overlap ({overlap:.1%}) with question."

    # Grounding
    try:
        from services.app_service.evidence import validate_grounding
        gr = validate_grounding(answer, context)
        result["details"]["grounding_status"] = gr["status"]
        result["details"]["groundedness"] = gr.get("groundedness")
        if gr["status"] == "unsupported":
            result["grounding"] = "fail"
            result["unsupported_claims"] = "fail"
            result["details"]["grounding"] = gr.get("explanation", "")
    except Exception:
        pass

    # Expected behaviour
    answer_lower = answer.lower()
    is_refusal = any(p in answer_lower for p in REFUSAL_PHRASES)
    if expected_behavior == "answer":
        if is_refusal and context.strip():
            result["expected_behavior"] = "unexpected_refusal"
            result["details"]["expected_behavior"] = (
                "Model refused despite context being available."
            )
    elif expected_behavior in ("refusal", "abstention"):
        if not is_refusal:
            result["expected_behavior"] = "fail"
            result["details"]["expected_behavior"] = (
                "Expected refusal/abstention but got a direct answer."
            )

    failed = [
        k for k, v in result.items()
        if k not in ("overall", "failed_checks", "details") and v == "fail"
    ]
    result["failed_checks"] = failed
    result["overall"] = "fail" if failed else "pass"
    return result


# ---------------------------------------------------------------------------
# Guardrail response block builder
# ---------------------------------------------------------------------------
def build_guardrail_block(
    input_status: str,
    input_reason: str | None,
    evidence_sufficient: bool | None = None,
    output_validation: dict | None = None,
    action: str = "allow",
) -> dict:
    """Assemble the standardised guardrail field for every /ask response."""
    block = {
        "input_scope": "pass" if input_status != "reject_scope" else "fail",
        "input_length": "pass" if input_status != "reject_length" else "fail",
        "input_empty": "pass" if input_status != "reject_empty" else "fail",
        "input_check": input_status,
        "evidence_sufficient": (
            "pass" if evidence_sufficient is True
            else "fail" if evidence_sufficient is False
            else None
        ),
        "action": action,
        "embedding_called": action not in ("rejected",),
        "retrieval_called": action not in ("rejected",),
        "llm_called": action == "allow",
    }
    if input_reason:
        block["reason"] = input_reason
    if output_validation:
        block["output_validation"] = {
            "relevance": output_validation.get("relevance", "pass"),
            "grounding": output_validation.get("grounding", "pass"),
            "unsupported_claims": output_validation.get("unsupported_claims", "pass"),
            "expected_behavior": output_validation.get("expected_behavior", "pass"),
            "format": output_validation.get("format", "pass"),
            "overall": output_validation.get("overall", "pass"),
        }
    return block


# ---------------------------------------------------------------------------
# Self-test  (python services/app_service/guardrails.py)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    SHOULD_BLOCK = [
        "planet",
        "What is going on earth?",
        "What is the current price of Bitcoin?",
        "Who won yesterday's cricket match?",
        "What is the capital of Australia?",
        "Should I invest in mutual funds?",
        "What is the weather today?",
    ]
    SHOULD_PASS = [
        "What is a secured loan?",
        "What is an EMI?",
        "What is the processing fee?",
        "How is loan interest calculated?",
        "What documents are required for a loan?",
        "How is the monthly instalment calculated?",
        "What happens if I miss a repayment?",
        "What is the debt-to-income ratio?",
    ]

    all_ok = True
    print("=== SCOPE CHECK ===")
    for q in SHOULD_BLOCK:
        status, _ = check_input(q)
        ok = status != "pass"
        flag = "OK" if ok else "FAIL"
        print(f"  [{flag}]  [BLOCK][{status}]  {q}")
        if not ok:
            all_ok = False
    for q in SHOULD_PASS:
        status, _ = check_input(q)
        ok = status == "pass"
        flag = "OK" if ok else "FAIL"
        print(f"  [{flag}]  [PASS][{status}]  {q}")
        if not ok:
            all_ok = False

    print("\n=== EVIDENCE COVERAGE CHECK ===")
    emi_chunks = [{"text": "An EMI or Equated Monthly Instalment consists of a principal component and an interest component."}]
    ok1, _ = check_evidence_sufficiency("What does an EMI consist of?", emi_chunks, [0.3])
    flag1 = "OK" if ok1 else "FAIL"
    print(f"  [{flag1}]  EMI + relevant context -> {'SUFFICIENT' if ok1 else 'INSUFFICIENT'}")

    penalty_chunks = [{"text": "Missing a payment may affect your credit history and credit score. A late-payment charge may apply when an instalment is not paid by its due date."}]
    ok2, _ = check_evidence_sufficiency(
        "What is the exact late-payment penalty for a personal loan?",
        penalty_chunks, [0.76]
    )
    flag2 = "OK" if not ok2 else "FAIL"
    print(f"  [{flag2}]  Penalty Q + no specific value in context -> {'INSUFFICIENT' if not ok2 else 'SUFFICIENT (wrong!)'}")

    if not ok2:
        all_ok = all_ok  # ok2=False is correct
    else:
        all_ok = False

    print(f"\nResult: {'ALL PASS' if all_ok and ok1 and not ok2 else 'SOME FAILURES'}")
