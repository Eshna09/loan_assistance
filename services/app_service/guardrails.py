"""
guardrails.py — input and output guardrails for the Loan Knowledge Assistance system.

Architecture:
    USER
     ↓
    INPUT GUARDRAIL  (check_input)
     ↓
    RAG RETRIEVAL
     ↓
    EVIDENCE CHECK   (check_evidence_sufficiency)
     ↓
    LLM
     ↓
    AI OUTPUT TESTING (validate_output)
     ↓
    ┌────────────┴────────────┐
    ↓                         ↓
   PASS                      FAIL
    ↓                         ↓
  FINAL ANSWER         CONTROLLED RESPONSE
"""

import os
import re
from typing import Tuple

# ── Configurable limits ────────────────────────────────────────────────────
MAX_INPUT_LENGTH = int(os.environ.get("MAX_INPUT_LENGTH", "1000"))

# Minimum evidence threshold: if top-1 L2 distance exceeds this, evidence is
# considered insufficient. Lower distance = more similar = better evidence.
MAX_EVIDENCE_DISTANCE = float(os.environ.get("MAX_EVIDENCE_DISTANCE", "1.2"))

# Minimum number of chunks required to attempt an LLM answer.
MIN_EVIDENCE_CHUNKS = int(os.environ.get("MIN_EVIDENCE_CHUNKS", "1"))

# ── Loan-domain keywords ───────────────────────────────────────────────────
# Any question containing at least one of these is considered in-scope.
LOAN_KEYWORDS = [
    "loan", "loans", "borrow", "borrower", "lender", "lenders", "lending",
    "credit", "interest", "emi", "equated monthly", "repay", "repayment",
    "principal", "collateral", "mortgage", "finance", "financial", "debt",
    "eligibility", "eligible", "default", "rate", "fee", "fees", "payment",
    "amortization", "amortisation", "prepayment", "prepay", "foreclosure",
    "secured", "unsecured", "tenure", "term", "income", "salary",
    "document", "documents", "bank", "asset", "liability", "dti",
    "variable rate", "fixed rate", "compound interest", "simple interest",
    "processing charge", "sanction", "disburse", "disbursement",
    "installment", "instalment", "overdue", "penalty", "guarantor",
    "home loan", "personal loan", "auto loan", "car loan", "education loan",
    "student loan", "business loan", "line of credit",
]

# ── Out-of-scope signal patterns ───────────────────────────────────────────
OUT_OF_SCOPE_PATTERNS = [
    r"\bbitcoin\b",
    r"\bcryptocurrency\b",
    r"\bcrypto\b",
    r"\bstock\s+market\b",
    r"\bshare\s+price\b",
    r"\bweather\b",
    r"\bsports\s+result\b",
    r"\bcricket\s+match\b",
    r"\bfootball\s+match\b",
    r"\brecipe\b",
    r"\bcook(ing)?\b",
    r"\bmovie\b",
    r"\bfilm\b",
    r"\belection\b",
    r"\bpolitics\b",
    r"\bwho\s+won.*match\b",
    r"\bcapital\s+city\b",
    r"\bcapital\s+of\s+\w+\b",
    r"\brepo\s+rate\b",
    r"\breserve\s+bank\s+of\s+india\b",
    r"\brbi\b.*\brate\b",
    r"\brate\b.*\brbi\b",
]

# Patterns that strongly indicate a general-knowledge (non-loan) question
GENERAL_KNOWLEDGE_PATTERNS = [
    r"^what is the capital\b",
    r"^who (is|was|won|scored)\b",
    r"^when did\b",
    r"^translate\b",
    r"^what.*price.*today\b",
    r"^current.*price of\b",
    r"write\s+a\s+python\s+program\b",
    r"write\s+code\s+to\b",
    r"what is the weather\b",
    r"today's news\b",
    r"latest news\b",
    r"current\s+repo\s+rate\b",
    r"\brepo\s+rate\b",
    r"rbi\s+rate\b",
    r"reserve\s+bank.*rate\b",
    r"reserve\s+bank\s+of\s+india\b",
    r"stock\s+performance\b",
    r"share\s+price\b",
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


# ── Input guardrail ────────────────────────────────────────────────────────
def check_input(question: str) -> Tuple[str, str | None]:
    """
    Validate and classify the input question before any processing.

    Returns:
        (status, reason)
        status: "pass" | "reject_empty" | "reject_length" | "reject_scope"
        reason: None if pass, human-readable rejection message otherwise.
    """
    # A. Empty / whitespace-only
    if not question or not question.strip():
        return (
            "reject_empty",
            "Please enter a question. The input cannot be empty.",
        )

    q = question.strip()

    # B. Excessive length
    if len(q) > MAX_INPUT_LENGTH:
        return (
            "reject_length",
            f"Your question is too long ({len(q)} characters). "
            f"Please keep it under {MAX_INPUT_LENGTH} characters.",
        )

    q_lower = q.lower()

    # C. Explicit out-of-scope patterns (high-confidence rejections)
    for pattern in OUT_OF_SCOPE_PATTERNS:
        if re.search(pattern, q_lower):
            return (
                "reject_scope",
                "I can only assist with questions related to the loan "
                "information available in the knowledge base.",
            )

    # D. General-knowledge patterns with no loan keywords
    has_loan_keyword = any(kw in q_lower for kw in LOAN_KEYWORDS)
    is_general = any(re.search(p, q_lower) for p in GENERAL_KNOWLEDGE_PATTERNS)

    if is_general and not has_loan_keyword:
        return (
            "reject_scope",
            "I can only assist with questions related to the loan "
            "information available in the knowledge base.",
        )

    return "pass", None


def build_input_guardrail_result(status: str, reason: str | None) -> dict:
    """Build the structured guardrail block for input checks."""
    passed = status == "pass"
    action_map = {
        "pass": "allow",
        "reject_empty": "rejected",
        "reject_length": "rejected",
        "reject_scope": "rejected",
    }
    return {
        "input_scope": "pass" if status not in ("reject_scope",) else "fail",
        "input_length": "pass" if status != "reject_length" else "fail",
        "input_empty": "pass" if status != "reject_empty" else "fail",
        "input_check": status,
        "evidence_sufficient": None,  # not yet checked
        "action": action_map.get(status, "rejected"),
        "reason": reason,
    }


# ── Evidence guardrail ─────────────────────────────────────────────────────
def check_evidence_sufficiency(chunks: list, distances: list) -> Tuple[bool, str | None]:
    """
    Determine whether retrieved evidence is sufficient to attempt LLM generation.

    Returns:
        (sufficient, reason)
        sufficient: True → proceed to LLM; False → abstain.
    """
    if not chunks or len(chunks) < MIN_EVIDENCE_CHUNKS:
        return (
            False,
            "I couldn't find sufficient information in the knowledge base to answer this question.",
        )

    # If the closest chunk is very far away, the KB likely has nothing relevant.
    if distances and distances[0] > MAX_EVIDENCE_DISTANCE:
        return (
            False,
            "I couldn't find sufficiently relevant information in the knowledge base to answer this question.",
        )

    return True, None


# ── Output validation ──────────────────────────────────────────────────────
def validate_output(
    answer: str,
    question: str,
    context: str,
    expected_behavior: str = "answer",
) -> dict:
    """
    Validate LLM output before returning it to the user.

    Checks:
        1. relevance   — answer shares content with the question
        2. grounding   — reuses validate_grounding from evidence.py
        3. unsupported_claims — numeric/factual claims outside context
        4. expected_behavior  — refusal vs answer vs abstention
        5. format      — not empty, not absurdly long, not malformed

    Returns a dict with individual check results and an overall pass/fail.
    """
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

    # 1. Format — not empty, not excessively long
    if not answer or not answer.strip():
        result["format"] = "fail"
        result["details"]["format"] = "Answer is empty."
    elif len(answer) > 8000:
        result["format"] = "fail"
        result["details"]["format"] = f"Answer is excessively long ({len(answer)} chars)."

    # 2. Relevance — word overlap between question and answer
    q_words = set(re.findall(r"[a-z]{3,}", question.lower()))
    a_words = set(re.findall(r"[a-z]{3,}", answer.lower()))
    if q_words:
        overlap = len(q_words & a_words) / len(q_words)
        result["details"]["relevance_overlap"] = round(overlap, 3)
        if overlap < 0.08:
            result["relevance"] = "fail"
            result["details"]["relevance"] = f"Very low word overlap ({overlap:.1%}) with the question."

    # 3. Grounding — delegate to evidence.py
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
        # If evidence module unavailable, skip this check
        pass

    # 4. Expected behaviour
    answer_lower = answer.lower()
    is_refusal = any(p in answer_lower for p in REFUSAL_PHRASES)

    if expected_behavior == "answer":
        if is_refusal and context.strip():
            # Model refused a question that had context — unexpected
            result["expected_behavior"] = "unexpected_refusal"
            result["details"]["expected_behavior"] = (
                "Model refused to answer despite relevant context being available."
            )
    elif expected_behavior in ("refusal", "abstention"):
        if not is_refusal:
            result["expected_behavior"] = "fail"
            result["details"]["expected_behavior"] = (
                "Expected a refusal/abstention but model provided a direct answer."
            )

    # 5. Collect failures
    failed = [
        k for k, v in result.items()
        if k not in ("overall", "failed_checks", "details") and v == "fail"
    ]
    result["failed_checks"] = failed
    result["overall"] = "fail" if failed else "pass"

    return result


# ── Convenience: build the full guardrail response block ──────────────────
def build_guardrail_block(
    input_status: str,
    input_reason: str | None,
    evidence_sufficient: bool | None = None,
    output_validation: dict | None = None,
    action: str = "allow",
) -> dict:
    """
    Assemble the standardised `guardrail` field returned in every /ask response.
    """
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
