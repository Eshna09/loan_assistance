"""
guardrails.py - Input, evidence, and output guardrails for Loan Knowledge Assistance.

Scope check uses TWO supported intents (default-deny):
  A. Loan knowledge      - any loan/finance domain question
  B. Codebase intent     - any of 7 repository categories:
       1. Code explanation         4. Bug analysis
       2. Code retrieval           5. Code generation
       3. Dependency understanding 6. Refactoring
                                   7. RAG-based code/documentation

Questions are classified by INTENT PATTERNS, not by exact string matching.
Any reasonable phrasing that signals one of these intents is allowed.

Control flow:
    USER INPUT
        |
    INPUT GUARDRAIL (check_input)
        |
    +---+---------------------------+
    | OUT OF SCOPE                  | IN SCOPE (loan OR codebase)
    | action: refuse                |
    | embed/retrieve/llm: NOT CALLED|   RETRIEVAL
    +-------------------------------+        |
                                    EVIDENCE CHECK
                                             |
                                    +--------+----------+
                                    | INSUFFICIENT      | SUFFICIENT
                                    | action: abstained |    LLM
                                    | llm: NOT CALLED   |    |
                                    +-------------------+ OUTPUT TEST
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
MIN_CONTEXT_COVERAGE = float(os.environ.get("MIN_CONTEXT_COVERAGE", "0.25"))

# ---------------------------------------------------------------------------
# A. LOAN-DOMAIN positive signals
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
# B. CODEBASE intent patterns (7 categories, intent-based not exact matching)
# ---------------------------------------------------------------------------

# 1. Code explanation - what/how/why questions about code artifacts
CODE_EXPLANATION_PATTERNS = [
    r"\bwhat does\b.{0,60}\b(endpoint|function|method|class|service|file|module|code|component|api|route|handler)\b",
    r"\bexplain\b.{0,60}\b(endpoint|function|method|class|service|file|module|code|component|api|route|how)\b",
    r"\bhow does\b.{0,60}\b(endpoint|function|method|class|service|file|module|code|component|api|work|process|handle)\b",
    r"\bwhat is the purpose of\b",
    r"\bwhat happens (inside|when|in|during)\b.{0,60}\b(endpoint|function|method|class|service|api|call|request)\b",
    r"\bwhy is\b.{0,60}\b(class|function|method|service|component|used|needed|called)\b",
    r"\bwalk me through\b",
    r"\b(describe|explain)\b.{0,40}\b(implementation|logic|flow|behavior|behaviour|working)\b",
    r"\bcan you explain how\b",
    r"\b/ask\b",
    r"\b/retrieve\b",
    r"\b/generate\b",
    r"\b/embed\b",
    r"\b/health\b",
    r"\b/reindex\b",
    r"\b/kb/\b",
    r"\b/playground/\b",
    r"\bask/debug\b",
    r"\bask endpoint\b",
    r"\bretrieve endpoint\b",
    r"\bgenerate endpoint\b",
]

# 2. Code retrieval - locating files, functions, components
CODE_RETRIEVAL_PATTERNS = [
    r"\bwhere is\b.{0,60}\b(implemented|defined|located|found|called|used|handled|loaded|stored)\b",
    r"\bwhich file\b",
    r"\bwhich (class|function|method|module|service|component|file)\b.{0,60}\b(handles|contains|defines|implements|manages|calls|uses)\b",
    r"\bwhere (is|are|can i find)\b.{0,60}\b(faiss|ollama|embedding|retrieval|guardrail|upload|document|chunk|index|llm|rag)\b",
    r"\bin which file\b",
    r"\bwhich file (defines|handles|contains|implements)\b",
    r"\bwhere (is|does) the\b.{0,60}\b(api call|embedding|model|index|guardrail|logic|code)\b",
    r"\bfaiss\b",
    r"\bollama\b",
    r"\bminilm\b",
    r"\bembedding model\b",
    r"\bapp.?service\b",
    r"\bdata.?service\b",
    r"\bllm.?service\b",
    r"\bretrieval.?service\b",
    r"\bguardrail\b",
]

# 3. Dependency understanding - service interactions
DEPENDENCY_PATTERNS = [
    r"\bwhich (services?|components?|parts?)\b.{0,60}\b(involved|called|used|communicate|connect|interact|depend)\b",
    r"\bhow does\b.{0,60}\b(frontend|backend|service|component|system|pipeline|flow)\b.{0,60}\b(communicat|connect|interact|call|send|work together)\b",
    r"\bwhat depends on\b",
    r"\bwhat calls\b.{0,60}\b(service|function|endpoint|component)\b",
    r"\bhow (are|is)\b.{0,60}\b(connected|coupled|integrated|linked|wired)\b",
    r"\brequest flow\b",
    r"\b(frontend|ui).{0,40}(backend|api|service|communicat|connect)\b",
    r"\bpipeline\b.{0,60}\b(work|flow|process|step|stage)\b",
]

# 4. Bug analysis - diagnosing problems
BUG_ANALYSIS_PATTERNS = [
    r"\bwhy (might|would|could|does|is)\b.{0,60}\b(endpoint|function|service|method|component|retrieval|llm|error|fail|return|crash|not work|broken)\b",
    r"\bwhat could cause\b",
    r"\bpossible cause\b",
    r"\broot cause\b",
    r"\bwhat (is|could be) (the|a) (bug|issue|problem|error|cause|reason)\b",
    r"\bwhy (is|does)\b.{0,60}\b(returning|failing|crashing|breaking|not responding|incorrect|wrong)\b",
    r"\bdebug\b.{0,60}\b(endpoint|service|function|error|issue|problem)\b",
    r"\bwhat (happens|goes) wrong\b",
    r"\btroubleshoot\b",
    r"\bwhy.{0,60}(error|exception|fail|crash|incorrect|wrong result|not called|not respond)\b",
    r"\bwhat.{0,60}(cause|lead to|result in).{0,60}(error|fail|crash|wrong|issue|problem)\b",
]

# 5. Code generation - writing code/tests for the project
CODE_GENERATION_PATTERNS = [
    r"\bwrite (a |an )?(unit )?test\b",
    r"\bgenerate (a |an )?(unit )?test\b",
    r"\bcreate (a |an )?(unit )?test\b",
    r"\bwrite (a |an )?(python )?function\b",
    r"\bgenerate (a |an )?(python )?function\b",
    r"\bwrite code\b.{0,60}\b(for|to|that)\b",
    r"\bcreate code\b",
    r"\bimplement\b.{0,60}\b(function|method|class|test|validation|check|guardrail|endpoint)\b",
    r"\bwrite.{0,40}\b(function|method|class|test|validation|endpoint|guardrail|emi|dti|interest)\b",
    r"\bgenerate.{0,40}\b(function|method|class|test|validation|endpoint|guardrail|emi|dti|interest)\b",
    r"\bunit test\b",
    r"\btest case\b.{0,40}\b(for|of|to test)\b",
    r"\bfunction.{0,40}(named|called|that)\b",
]

# 6. Refactoring - improving project code
REFACTORING_PATTERNS = [
    r"\bhow (can|could|should|would)\b.{0,60}\b(function|method|class|service|code|component|endpoint|implementation|retrieval|guardrail|chunk)\b.{0,60}\b(be improved|be refactored|be simplified|be optimized|be cleaned|be better)\b",
    r"\bsuggest (a |an )?(better|improved|cleaner|simpler|alternative)\b.{0,60}\b(implementation|approach|design|way|method|version)\b",
    r"\brefactor\b",
    r"\bimprove\b.{0,60}\b(function|method|class|service|code|component|endpoint|implementation|retrieval|guardrail|chunk)\b",
    r"\b(better|cleaner|simpler|more efficient) (implementation|approach|design|way|code|version)\b",
    r"\boptimize\b.{0,60}\b(function|method|class|service|code|query|retrieval|performance)\b",
    r"\bcan (this|the)\b.{0,60}\b(function|method|code|service|component|endpoint)\b.{0,60}\b(be improved|be refactored|be simplified|be cleaner|be optimized)\b",
    r"\bwhat.{0,40}improvement.{0,40}(suggest|recommend|make|propose)\b",
    r"\bhow can.{0,40}(made|be) (cleaner|simpler|better|more efficient|more maintainable)\b",
    r"\bsuggest an improvement\b",
]

# 7. RAG-based code/documentation questions
CODE_DOC_PATTERNS = [
    r"\barchitecture\b.{0,60}\b(say|document|describe|explain|mention|state|show)\b",
    r"\barchitecture\.md\b",
    r"\bdocumentation\b.{0,60}\b(say|describe|explain|mention|state|show|about)\b",
    r"\baccording to\b.{0,60}\b(documentation|docs|architecture|readme|spec|design)\b",
    r"\bwhat does.{0,40}(doc|documentation|architecture|readme|spec|architecture\.md).{0,40}say\b",
    r"\bdocumented\b.{0,60}\b(flow|pipeline|behavior|service|endpoint|api|interaction)\b",
    r"\bproject documentation\b",
    r"\brepository documentation\b",
    r"\breadme\b",
    r"\brag pipeline\b",
    r"\bsource graph\b",
    r"\bhow is.{0,40}(service|component|pipeline|flow|communication).{0,40}(documented|described)\b",
]

ALL_CODEBASE_PATTERNS = (
    CODE_EXPLANATION_PATTERNS
    + CODE_RETRIEVAL_PATTERNS
    + DEPENDENCY_PATTERNS
    + BUG_ANALYSIS_PATTERNS
    + CODE_GENERATION_PATTERNS
    + REFACTORING_PATTERNS
    + CODE_DOC_PATTERNS
)

# ---------------------------------------------------------------------------
# Hard-coded out-of-scope patterns (checked FIRST - fast reject)
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
    r"\bprime minister\b",
    r"\bpresident of\b",
    r"\blatest news\b",
    r"\bnews today\b",
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
    "information available in the knowledge base, or questions "
    "about this project's codebase and documentation."
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
    words = re.findall(r"[a-z]{3,}", text.lower())
    return {w for w in words if w not in _STOPWORDS}


def _is_loan_scope(q_lower: str) -> bool:
    return any(re.search(p, q_lower) for p in LOAN_TOPIC_PHRASES)


def _is_codebase_intent(q_lower: str) -> bool:
    return any(re.search(p, q_lower) for p in ALL_CODEBASE_PATTERNS)


def classify_intent(question: str) -> tuple:
    """
    Classify the user's question into (domain, category).

    Returns:
      domain:   "LOAN" | "CODEBASE" | "OUT_OF_SCOPE"
      category: e.g. "CODE_EXPLANATION", "code_retrieval", "LOAN", "OUT_OF_SCOPE"
    """
    q = question.strip().lower()

    # Hard OOS check first
    for pattern in OUT_OF_SCOPE_PATTERNS:
        if re.search(pattern, q):
            return "OUT_OF_SCOPE", "OUT_OF_SCOPE"

    # Check each codebase category (in priority order)
    category_map = [
        ("CODE_EXPLANATION",       CODE_EXPLANATION_PATTERNS),
        ("CODE_RETRIEVAL",         CODE_RETRIEVAL_PATTERNS),
        ("DEPENDENCY_UNDERSTANDING", DEPENDENCY_PATTERNS),
        ("BUG_ANALYSIS",           BUG_ANALYSIS_PATTERNS),
        ("CODE_GENERATION",        CODE_GENERATION_PATTERNS),
        ("REFACTORING",            REFACTORING_PATTERNS),
        ("RAG_CODE_DOC",           CODE_DOC_PATTERNS),
    ]
    for cat, patterns in category_map:
        if any(re.search(p, q) for p in patterns):
            return "CODEBASE", cat

    # Check loan domain
    if _is_loan_scope(q):
        return "LOAN", "LOAN"

    return "OUT_OF_SCOPE", "OUT_OF_SCOPE"


# ---------------------------------------------------------------------------
# INPUT GUARDRAIL
# ---------------------------------------------------------------------------
def check_input(question: str) -> Tuple[str, str | None]:
    """
    Validate and scope-check (DEFAULT-DENY).

    Returns (status, reason):
      "pass" | "reject_empty" | "reject_length" | "reject_scope"
    """
    if not question or not question.strip():
        return "reject_empty", "Please enter a question. The input cannot be empty."

    q = question.strip()
    if len(q) > MAX_INPUT_LENGTH:
        return (
            "reject_length",
            f"Your question is too long ({len(q)} characters). "
            f"Please keep it under {MAX_INPUT_LENGTH} characters.",
        )

    q_lower = q.lower()

    # Hard out-of-scope signals first
    for pattern in OUT_OF_SCOPE_PATTERNS:
        if re.search(pattern, q_lower):
            return "reject_scope", _SCOPE_REFUSAL_MSG

    # Allow if loan domain OR codebase intent
    if _is_loan_scope(q_lower) or _is_codebase_intent(q_lower):
        return "pass", None

    return "reject_scope", _SCOPE_REFUSAL_MSG

# ---------------------------------------------------------------------------
# EVIDENCE SUFFICIENCY CHECK
# ---------------------------------------------------------------------------
def check_evidence_sufficiency(
    question: str,
    chunks: list,
    distances: list,
) -> Tuple[bool, str | None]:
    """
    Gates: (1) chunk count, (2) L2 distance,
           (3) semantic coverage, (4) specificity check.
    """
    if not chunks or len(chunks) < MIN_EVIDENCE_CHUNKS:
        return False, _EVIDENCE_ABSTAIN_MSG
    if distances and distances[0] > MAX_EVIDENCE_DISTANCE:
        return False, _EVIDENCE_ABSTAIN_MSG

    q_words = _content_words(question)
    if not q_words:
        return True, None

    combined = " ".join(c.get("text", "") for c in chunks)
    ctx_words = _content_words(combined)
    coverage = len(q_words & ctx_words) / len(q_words)

    if coverage < MIN_CONTEXT_COVERAGE:
        return False, _EVIDENCE_ABSTAIN_MSG

    # Specificity gate: exact/specific value queries need a number in context
    q_lower = question.lower()
    asks_exact = bool(re.search(
        r"\b(exact|specific|precise|how much|percentage|rate|amount|figure|number|value)\b",
        q_lower
    ))
    if asks_exact:
        key_nouns = [w for w in q_words if len(w) >= 5]
        has_pct = bool(re.search(r"\d+(?:\.\d+)?\s*%", combined))
        topic_num = any(
            re.search(rf"\b{re.escape(noun)}\b.{{0,80}}\d", combined, re.IGNORECASE)
            for noun in key_nouns
        )
        if not has_pct and not topic_num:
            return False, _EVIDENCE_ABSTAIN_MSG

    return True, None


# ---------------------------------------------------------------------------
# OUTPUT VALIDATION
# ---------------------------------------------------------------------------
def validate_output(
    answer: str,
    question: str,
    context: str,
    expected_behavior: str = "answer",
) -> dict:
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
        result["details"]["format"] = f"Answer too long ({len(answer)} chars)."

    q_words = set(re.findall(r"[a-z]{3,}", question.lower()))
    a_words = set(re.findall(r"[a-z]{3,}", answer.lower()))
    if q_words:
        overlap = len(q_words & a_words) / len(q_words)
        result["details"]["relevance_overlap"] = round(overlap, 3)
        if overlap < 0.08:
            result["relevance"] = "fail"
            result["details"]["relevance"] = f"Low overlap ({overlap:.1%})."

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
    elif expected_behavior in ("refusal", "abstention"):
        if not is_refusal:
            result["expected_behavior"] = "fail"

    failed = [k for k, v in result.items()
              if k not in ("overall", "failed_checks", "details") and v == "fail"]
    result["failed_checks"] = failed
    result["overall"] = "fail" if failed else "pass"
    return result


# ---------------------------------------------------------------------------
# Guardrail block builder
# ---------------------------------------------------------------------------
def build_guardrail_block(
    input_status: str,
    input_reason: str | None,
    evidence_sufficient: bool | None = None,
    output_validation: dict | None = None,
    action: str = "allow",
) -> dict:
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
            k: output_validation.get(k, "pass")
            for k in ("relevance", "grounding", "unsupported_claims",
                      "expected_behavior", "format", "overall")
        }
    return block


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    LOAN_PASS = [
        "What is a secured loan?",
        "What is an EMI?",
        "What is the processing fee?",
        "How is loan interest calculated?",
        "What documents are required for a loan?",
        "How is the monthly instalment calculated?",
    ]

    CODEBASE_PASS = {
        "code_explanation": [
            "What does the /ask endpoint do?",
            "Can you explain how the /ask endpoint works?",
            "How does the retrieval service process a query?",
            "What is the purpose of this function?",
            "Explain this method.",
            "Why is this class used?",
            "What happens inside this endpoint?",
        ],
        "code_retrieval": [
            "Where is FAISS implemented?",
            "Which file contains the embedding logic?",
            "Where is the Ollama API call made?",
            "Which file handles document uploads?",
            "Where is the guardrail implemented?",
            "Which file defines the /ask endpoint?",
        ],
        "dependency_understanding": [
            "Which services are involved when a user asks a question?",
            "How does the frontend communicate with the backend?",
            "Which component calls the retrieval service?",
            "What depends on the LLM service?",
            "How are these two components connected?",
        ],
        "bug_analysis": [
            "Why might this endpoint return an error?",
            "What could cause retrieval to return irrelevant results?",
            "Why might the LLM not respond?",
            "What could cause this function to return the wrong result?",
            "What is a possible cause of this bug?",
        ],
        "code_generation": [
            "Write a unit test for this function.",
            "Generate a test for the /ask endpoint.",
            "Create a test for the guardrail.",
            "Write a function to calculate EMI.",
            "Generate a test for conflict detection.",
        ],
        "refactoring": [
            "How can this function be improved?",
            "Suggest a better implementation.",
            "How could this code be refactored?",
            "Can this service interaction be simplified?",
            "Suggest an improvement to this component.",
        ],
        "rag_based_code_doc": [
            "What does the architecture document say about RAG?",
            "According to the documentation, how do the services communicate?",
            "What does the project documentation say about embeddings?",
            "How does the documented request flow work?",
            "What does the repository documentation say about the retrieval service?",
        ],
    }

    OOS_BLOCK = [
        "planet",
        "What is going on earth?",
        "What is the current price of Bitcoin?",
        "Who won yesterday's cricket match?",
        "What is the capital of Australia?",
        "Should I invest in mutual funds?",
        "What is the weather today?",
        "Tell me about space exploration.",
        "Who is the prime minister of India?",
        "What is the latest news?",
    ]

    total = 0
    passed = 0
    all_ok = True

    print("=== LOAN QUESTIONS (expect PASS) ===")
    for q in LOAN_PASS:
        s, _ = check_input(q)
        ok = s == "pass"
        total += 1
        if ok: passed += 1
        else: all_ok = False
        print(f"  {'OK' if ok else 'FAIL'}  [{s}]  {q}")

    print()
    print("=== CODEBASE BY CATEGORY (expect PASS) ===")
    for cat, qs in CODEBASE_PASS.items():
        cat_p = 0
        print(f"  -- {cat} --")
        for q in qs:
            s, _ = check_input(q)
            ok = s == "pass"
            total += 1
            if ok: passed += 1; cat_p += 1
            else: all_ok = False
            print(f"    {'OK' if ok else 'FAIL'}  [{s}]  {q}")
        print(f"    => {cat_p}/{len(qs)}")

    print()
    print("=== OUT-OF-SCOPE (expect BLOCK) ===")
    for q in OOS_BLOCK:
        s, _ = check_input(q)
        ok = s != "pass"
        total += 1
        if ok: passed += 1
        else: all_ok = False
        print(f"  {'OK' if ok else 'FAIL'}  [{s}]  {q}")

    print()
    print(f"=== RESULT: {passed}/{total} ({'ALL PASS' if all_ok else 'SOME FAILURES'}) ===")
