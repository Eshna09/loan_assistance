"""
guardrails.py — input and output guardrails for the Loan Knowledge Assistance system.

Scope-check architecture (STRICT default-deny):

    USER INPUT
         ↓
    INPUT GUARDRAIL  (check_input)
         ↓
    ┌────┴──────────────────────────────────┐
    │ OUT OF SCOPE                          │ IN SCOPE
    │ scope_check: FAIL                     │ scope_check: PASS
    │ action: refuse                        │      ↓
    │ DO NOT embed                          │  EMBEDDING
    │ DO NOT retrieve                       │      ↓
    │ DO NOT call LLM                       │  FAISS RETRIEVAL
    └───────────────────────────────────────│      ↓
                                            │  EVIDENCE CHECK
                                            │      ↓
                                            │  LLM
                                            │      ↓
                                            │  AI OUTPUT TESTING
                                            └──────────────────

IMPORTANT: scope is determined by POSITIVE EVIDENCE of loan-domain content.
A question that contains no loan signals is rejected by default.
"""

import os
import re
from typing import Tuple

# ── Configurable limits ────────────────────────────────────────────────────
MAX_INPUT_LENGTH = int(os.environ.get("MAX_INPUT_LENGTH", "1000"))
MAX_EVIDENCE_DISTANCE = float(os.environ.get("MAX_EVIDENCE_DISTANCE", "1.2"))
MIN_EVIDENCE_CHUNKS = int(os.environ.get("MIN_EVIDENCE_CHUNKS", "1"))

# ── Loan-domain POSITIVE signals ──────────────────────────────────────────
# A question must contain at least one of these to be considered in-scope.
# These are specific enough that false positives are very unlikely.
LOAN_KEYWORDS = [
    # Core loan concepts
    "loan", "loans", "borrow", "borrower", "lender", "lenders", "lending",
    "mortgage", "credit score", "creditworthiness",
    # Financial instruments
    "emi", "equated monthly", "instalment", "installment",
    "amortization", "amortisation", "amortize",
    "prepayment", "prepay", "foreclosure",
    # Interest
    "interest rate", "compound interest", "simple interest",
    "fixed rate", "variable rate", "floating rate",
    # Loan components
    "principal amount", "collateral", "guarantor",
    # Repayment
    "repay", "repayment", "overdue", "default on",
    # Fees & costs
    "processing fee", "processing charge", "late payment fee",
    "late fee", "penalty interest", "documentation charge",
    "loan fee", "loan cost",
    # Eligibility
    "loan eligibility", "eligible for a loan", "eligibility criteria",
    "debt-to-income", "dti ratio",
    # Types
    "home loan", "personal loan", "auto loan", "car loan",
    "education loan", "student loan", "business loan",
    "secured loan", "unsecured loan", "line of credit",
    # Actions
    "apply for a loan", "loan application", "loan approval",
    "loan tenure", "loan term", "loan amount",
    # Documents
    "loan document", "sanction letter", "loan agreement",
]

# ── Loan-domain TOPIC phrases (broader, used as secondary signal) ──────────
# These are loan-related concepts that may appear in valid questions
# even without the word "loan" directly.
LOAN_TOPIC_PHRASES = [
    # EMI / repayment
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
    # Interest
    r"\binterest rate\b",
    r"\bcompound interest\b",
    r"\bsimple interest\b",
    r"\bfixed rate\b",
    r"\bvariable rate\b",
    r"\bfloating rate\b",
    # Loan-specific terms
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

# ── Hard-coded out-of-scope patterns (checked first, fast reject) ─────────
OUT_OF_SCOPE_PATTERNS = [
    r"\bbitcoin\b",
    r"\bcryptocurrency\b",
    r"\bcrypto\b",
    r"\bstock\s+market\b",
    r"\bshare\s+price\b",
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
    r"\bcapital\s+of\b",
    r"\bcapital\s+city\b",
    r"\brepo\s+rate\b",
    r"\breserve\s+bank\s+of\s+india\b",
    r"\brbi\b",
    r"\bmutual\s+fund\b",
    r"\bstock\s+price\b",
    r"\bshare\s+market\b",
    r"\binvest\s+in\b",
    r"\bgoing\s+on\s+(earth|in\s+the\s+world|today)\b",
    r"\bwhat\s+is\s+(going|happening)\s+on\b",
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


# ── Core scope checker ────────────────────────────────────────────────────
def _is_loan_scope(q_lower: str) -> bool:
    """
    Return True ONLY if the question contains positive loan-domain evidence.

    Uses phrase-level regex matching so multi-word terms like
    'monthly instalment', 'compound interest', 'processing fee'
    are detected even without the word 'loan'.
    """
    return any(re.search(p, q_lower) for p in LOAN_TOPIC_PHRASES)


# ── Public: check_input ───────────────────────────────────────────────────
def check_input(question: str) -> Tuple[str, str | None]:
    """
    Validate and scope-check the input question.

    Logic:
      1. Reject if empty / whitespace-only   → reject_empty
      2. Reject if too long                  → reject_length
      3. Reject if explicit OOS pattern      → reject_scope
      4. Reject if NO positive loan signal   → reject_scope  ← default-deny
      5. Otherwise                           → pass

    Returns:
        (status, reason)
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

    # 3. Explicit out-of-scope signals (fast reject before any positive check)
    for pattern in OUT_OF_SCOPE_PATTERNS:
        if re.search(pattern, q_lower):
            return "reject_scope", _SCOPE_REFUSAL_MSG

    # 4. DEFAULT-DENY: require positive loan-domain evidence
    if not _is_loan_scope(q_lower):
        return "reject_scope", _SCOPE_REFUSAL_MSG

    # 5. Pass
    return "pass", None


# ── Evidence guardrail ────────────────────────────────────────────────────
def check_evidence_sufficiency(chunks: list, distances: list) -> Tuple[bool, str | None]:
    """Return (sufficient, reason). Called AFTER retrieval, BEFORE LLM."""
    if not chunks or len(chunks) < MIN_EVIDENCE_CHUNKS:
        return (
            False,
            "I couldn't find sufficient information in the knowledge base to answer this question.",
        )
    if distances and distances[0] > MAX_EVIDENCE_DISTANCE:
        return (
            False,
            "I couldn't find sufficiently relevant information in the knowledge base to answer this question.",
        )
    return True, None


# ── Output validation ─────────────────────────────────────────────────────
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

    if not answer or not answer.strip():
        result["format"] = "fail"
        result["details"]["format"] = "Answer is empty."
    elif len(answer) > 8000:
        result["format"] = "fail"
        result["details"]["format"] = f"Answer is excessively long ({len(answer)} chars)."

    q_words = set(re.findall(r"[a-z]{3,}", question.lower()))
    a_words = set(re.findall(r"[a-z]{3,}", answer.lower()))
    if q_words:
        overlap = len(q_words & a_words) / len(q_words)
        result["details"]["relevance_overlap"] = round(overlap, 3)
        if overlap < 0.08:
            result["relevance"] = "fail"
            result["details"]["relevance"] = f"Very low word overlap ({overlap:.1%}) with question."

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


# ── Guardrail response block builder ─────────────────────────────────────
def build_guardrail_block(
    input_status: str,
    input_reason: str | None,
    evidence_sufficient: bool | None = None,
    output_validation: dict | None = None,
    action: str = "allow",
) -> dict:
    """Assemble the standardised `guardrail` field for every /ask response."""
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
        # Explicitly record which pipeline steps ran
        "embedding_called": action == "allow",
        "retrieval_called": action == "allow",
        "llm_called": action == "allow" and evidence_sufficient is not False,
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


# ── Quick self-test (run directly: python guardrails.py) ──────────────────
if __name__ == "__main__":
    SHOULD_BLOCK = [
        "planet",
        "What is going on earth?",
        "What is the current price of Bitcoin?",
        "Who won yesterday's cricket match?",
        "What is the capital of Australia?",
        "Should I invest in mutual funds?",
        "What is the weather today?",
        "Tell me about space exploration.",
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

    print("=== SHOULD BLOCK ===")
    all_ok = True
    for q in SHOULD_BLOCK:
        status, reason = check_input(q)
        ok = status != "pass"
        flag = "✓" if ok else "✗ FAIL"
        print(f"  {flag}  [{status}]  {q}")
        if not ok:
            all_ok = False

    print("\n=== SHOULD PASS ===")
    for q in SHOULD_PASS:
        status, reason = check_input(q)
        ok = status == "pass"
        flag = "✓" if ok else "✗ FAIL"
        print(f"  {flag}  [{status}]  {q}")
        if not ok:
            all_ok = False

    print(f"\nResult: {'ALL PASS' if all_ok else 'SOME FAILURES'}")
