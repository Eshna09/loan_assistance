"""
evidence.py — evidence analysis, conflict detection, version resolution,
grounding validation.  All logic runs inside the Application Service.

Conflict detection uses field-aware claim extraction:
  - Extracts (field_key, numeric_value, raw_value_str) tuples from each chunk
  - Two claims conflict when they share the same normalised field key
    but have different numeric values
  - Field normalisation merges synonymous labels (e.g. "processing charge"
    and "processing fee" → "processing_fee")
  - Unrelated numeric values (age, tenure, amounts) DO NOT conflict with fees
"""
import re
from datetime import date

import os

# ── Configuration ──────────────────────────────────────────────────────────
GROUNDING_SUPPORTED_THRESHOLD = float(
    os.environ.get("GROUNDING_SUPPORTED_THRESHOLD", "0.60")
)
GROUNDING_PARTIAL_THRESHOLD = float(
    os.environ.get("GROUNDING_PARTIAL_THRESHOLD", "0.30")
)

# How many chunks to use for conflict/version analysis when the caller
# passes a larger retrieval set.  /ask/debug uses EVIDENCE_TOP_K chunks
# (first N by rank); /ask still uses DEFAULT_TOP_K for LLM context.
EVIDENCE_TOP_K = int(os.environ.get("EVIDENCE_TOP_K", "8"))

STOPWORDS = frozenset(
    "a an the and or but if then that this these those of to in on for with by "
    "from as at is are was were be been being it its do does did not no nor so "
    "such can could may might will would shall should must have has had you your "
    "i we they he she them their our us me my what which who when where why how "
    "about into over under more most less also only just very".split()
)

FALLBACK_PHRASES = (
    "not available in my knowledge base",
    "cannot be found in the context",
    "not found in the context",
    "no information",
    "cannot find",
    "insufficient information",
    "does not contain",
    "does not specify",
    "i don't have",
    "i do not have",
    "unable to answer",
    "could not find",
)

# ── Field normalisation map ────────────────────────────────────────────────
# Maps raw label fragments → canonical field key.
# Only percentage/rate fields matter for conflict; amounts/ages/tenures
# are intentionally excluded (they don't conflict across products).
FIELD_SYNONYMS: list[tuple[list[str], str]] = [
    (["processing fee", "processing charge", "loan processing fee",
      "processing fees", "origination fee", "origination charge"],
     "processing_fee"),
    (["interest rate", "rate of interest", "interest rate range",
      "interest rates", "lending rate"],
     "interest_rate"),
    (["late payment fee", "late payment charge", "late fee",
      "overdue charge", "penalty charge", "late-payment charge"],
     "late_payment_fee"),
    (["prepayment fee", "prepayment charge", "foreclosure fee",
      "foreclosure charge", "prepayment penalty"],
     "prepayment_fee"),
    (["gst", "goods and services tax", "tax rate"],
     "tax_rate"),
]


def _normalise_field(label: str) -> str | None:
    """Return a canonical field key for a label, or None if unrecognised."""
    l = label.lower().strip()
    for synonyms, key in FIELD_SYNONYMS:
        for syn in synonyms:
            if syn in l or l in syn:
                return key
    return None


def _content_words(text: str) -> list:
    words = re.findall(r"[a-z]{3,}", (text or "").lower())
    return [w for w in words if w not in STOPWORDS]


# ── Claim extraction ──────────────────────────────────────────────────────
# Pattern: "<label> is/are/of <value>%" or "<label>: <value>%"
# Captures the label text immediately before a percentage.
_CLAIM_RE = re.compile(
    r"([\w\s\-]{3,50}?)\s*(?:is|are|of|:|=|@)\s*(\d+(?:\.\d+)?)\s*(%|percent)",
    re.IGNORECASE,
)
# Also match table-style: "Processing Fee   1.5% of loan amount"
_TABLE_CLAIM_RE = re.compile(
    r"([\w\s\-]{3,50}?)\s{2,}(\d+(?:\.\d+)?)\s*(%|percent)",
    re.IGNORECASE,
)


def _extract_claims(text: str) -> list[dict]:
    """
    Extract (field_key, numeric_value, raw_value_str) claims from chunk text.
    Returns only claims whose label maps to a known field.
    """
    claims = []
    seen = set()  # (field_key, value) dedup
    for pattern in (_CLAIM_RE, _TABLE_CLAIM_RE):
        for m in pattern.finditer(text):
            label_raw = m.group(1).strip()
            val_str = m.group(2)
            try:
                val = float(val_str)
            except ValueError:
                continue
            field_key = _normalise_field(label_raw)
            if field_key is None:
                continue
            dedup_key = (field_key, val)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            claims.append({
                "field_key": field_key,
                "field_label": label_raw,
                "value": val,
                "value_str": f"{val_str}%",
            })
    return claims


# ── Evidence building ──────────────────────────────────────────────────────
def build_evidence(chunks: list, distances: list) -> list:
    """Construct an evidence record for each retrieved chunk."""
    result = []
    for i, (chunk, dist) in enumerate(zip(chunks, distances)):
        result.append({
            "source": chunk.get("source", "unknown"),
            "chunk_id": chunk.get("chunk_id", i),
            "rank": i + 1,
            "distance": round(float(dist), 4),
            "version": chunk.get("version", "1.0"),
            "effective_date": chunk.get("effective_date"),
            "document_type": chunk.get("document_type", "general"),
            "loan_type": chunk.get("loan_type", "general"),
            "text_preview": (chunk.get("text") or "")[:150],
        })
    return result


# ── Conflict detection ─────────────────────────────────────────────────────
def detect_conflicts(chunks: list) -> dict:
    """
    Detect conflicting factual claims across different source documents.

    For each chunk, extract (field_key, value) claims using pattern matching
    and field normalisation.  Two chunks from DIFFERENT sources conflict when
    they assert the same field_key with different numeric values.

    This avoids false positives (age=21 vs tenure=5) because unrelated labels
    do not map to the same field_key.
    """
    if not chunks:
        return {"conflict_detected": False, "conflicts": []}

    # Build per-chunk claim list with provenance
    chunk_claims: list[dict] = []
    for chunk in chunks:
        src = chunk.get("source", "unknown")
        text = chunk.get("text", "")
        claims = _extract_claims(text)
        for claim in claims:
            chunk_claims.append({
                "source": src,
                "version": chunk.get("version", "1.0"),
                "effective_date": chunk.get("effective_date"),
                "field_key": claim["field_key"],
                "field_label": claim["field_label"],
                "value": claim["value"],
                "value_str": claim["value_str"],
            })

    if not chunk_claims:
        return {"conflict_detected": False, "conflicts": []}

    # Group by field_key
    by_field: dict[str, list[dict]] = {}
    for c in chunk_claims:
        by_field.setdefault(c["field_key"], []).append(c)

    conflicts = []
    for field_key, field_claims in by_field.items():
        # Collect unique (source, value) pairs
        source_values: dict[str, dict] = {}
        for fc in field_claims:
            src = fc["source"]
            if src not in source_values:
                source_values[src] = fc
            # Keep the claim; if same source appears twice with same field,
            # take the first (lowest rank = most relevant)

        if len(source_values) < 2:
            continue

        # Check if any two sources report different values for this field
        src_list = list(source_values.values())
        for i in range(len(src_list)):
            for j in range(i + 1, len(src_list)):
                a, b = src_list[i], src_list[j]
                if abs(a["value"] - b["value"]) > 1e-9:
                    # Conflict found
                    # Compose a human-readable topic from the field labels
                    topic = _make_topic(field_key, a["field_label"], b["field_label"])
                    # Build structured claims list
                    conflict_claims = []
                    for sv in src_list:
                        conflict_claims.append({
                            "value": sv["value_str"],
                            "value_num": sv["value"],
                            "source": sv["source"],
                            "version": sv["version"],
                            "effective_date": sv["effective_date"],
                            "field_label": sv["field_label"],
                        })
                    conflicts.append({
                        "topic": topic,
                        "field_key": field_key,
                        "claims": conflict_claims,
                    })
                    # Only report once per field pair
                    break
            else:
                continue
            break

    return {"conflict_detected": bool(conflicts), "conflicts": conflicts}


def _make_topic(field_key: str, label_a: str, label_b: str) -> str:
    """Create a readable conflict topic string."""
    FIELD_DISPLAY = {
        "processing_fee": "Processing Fee",
        "interest_rate": "Interest Rate",
        "late_payment_fee": "Late Payment Fee",
        "prepayment_fee": "Prepayment Fee",
        "tax_rate": "Tax Rate",
    }
    return FIELD_DISPLAY.get(field_key, field_key.replace("_", " ").title())


# ── Version resolution ─────────────────────────────────────────────────────
def resolve_version(chunks: list, conflicts: list | None = None) -> dict:
    """
    When multiple document versions are present, identify the most authoritative.
    Prefers latest effective_date, then highest version number.

    If conflicts are provided, the resolution result includes which conflicting
    value belongs to the authoritative source.
    """
    by_source: dict = {}
    for chunk in chunks:
        src = chunk.get("source", "unknown")
        if src not in by_source:
            by_source[src] = {
                "source": src,
                "version": chunk.get("version", "1.0"),
                "effective_date": chunk.get("effective_date"),
                "loan_type": chunk.get("loan_type", "general"),
            }

    if len(by_source) < 2:
        src_info = next(iter(by_source.values()), {})
        return {
            "resolution_performed": False,
            "authoritative_source": src_info.get("source"),
            "reason": "single_source",
        }

    # Attempt to parse effective dates
    dated = []
    undated = []
    for info in by_source.values():
        ed = info.get("effective_date")
        if ed:
            try:
                parsed = date.fromisoformat(str(ed)[:10])
                dated.append((parsed, info))
            except (ValueError, TypeError):
                undated.append(info)
        else:
            undated.append(info)

    resolution = None

    if len(dated) >= 2:
        dated.sort(key=lambda x: x[0], reverse=True)
        newest_dt, newest = dated[0]
        older = [d[1] for d in dated[1:]] + undated
        resolution = {
            "resolution_performed": True,
            "authoritative_source": newest["source"],
            "authoritative_version": newest["version"],
            "authoritative_effective_date": str(newest_dt),
            "superseded_sources": [s["source"] for s in older],
            "reason": "latest_effective_date",
            "reason_label": "Latest effective date",
        }
    elif len(dated) == 1:
        newest = dated[0][1]
        resolution = {
            "resolution_performed": True,
            "authoritative_source": newest["source"],
            "authoritative_version": newest["version"],
            "authoritative_effective_date": newest["effective_date"],
            "superseded_sources": [s["source"] for s in undated],
            "reason": "only_dated_source",
            "reason_label": "Only source with effective date",
        }
    else:
        # Fall back to version number comparison
        versioned = []
        for info in undated:
            try:
                ver_tuple = tuple(int(x) for x in str(info.get("version", "1.0")).split("."))
            except ValueError:
                ver_tuple = (1, 0)
            versioned.append((ver_tuple, info))
        versioned.sort(key=lambda x: x[0], reverse=True)

        if len(versioned) >= 2 and versioned[0][0] != versioned[-1][0]:
            newest = versioned[0][1]
            resolution = {
                "resolution_performed": True,
                "authoritative_source": newest["source"],
                "authoritative_version": newest["version"],
                "superseded_sources": [s["source"] for _, s in versioned[1:]],
                "reason": "highest_version_number",
                "reason_label": "Highest version number",
            }
        else:
            return {
                "resolution_performed": False,
                "authoritative_source": None,
                "reason": "insufficient_metadata",
                "message": (
                    "Conflicting information was found in the knowledge base, and the available "
                    "metadata is insufficient to determine which policy is currently applicable."
                ),
            }

    # Attach the authoritative value from conflicts if available
    if resolution and resolution.get("resolution_performed") and conflicts:
        auth_src = resolution["authoritative_source"]
        resolved_values = []
        for conflict in conflicts:
            for claim in conflict.get("claims", []):
                if claim["source"] == auth_src:
                    resolved_values.append({
                        "field": conflict["topic"],
                        "value": claim["value"],
                        "field_key": conflict.get("field_key", ""),
                    })
        if resolved_values:
            resolution["resolved_values"] = resolved_values

        # Also attach superseded values for display
        superseded_values = []
        for conflict in conflicts:
            for claim in conflict.get("claims", []):
                if claim["source"] != auth_src:
                    superseded_values.append({
                        "field": conflict["topic"],
                        "value": claim["value"],
                        "source": claim["source"],
                        "version": claim["version"],
                        "effective_date": claim["effective_date"],
                        "field_key": conflict.get("field_key", ""),
                    })
        if superseded_values:
            resolution["superseded_values"] = superseded_values

    return resolution


# ── Grounding validation ───────────────────────────────────────────────────
def validate_grounding(answer: str, context: str) -> dict:
    """
    Classify the answer as supported/partially_supported/unsupported/
    insufficient_evidence/conflict_detected based on word overlap with context.
    """
    if not answer or not answer.strip():
        return {
            "status": "insufficient_evidence",
            "groundedness": 0.0,
            "explanation": "No answer was generated.",
        }

    al = answer.lower()
    if any(p in al for p in FALLBACK_PHRASES):
        return {
            "status": "insufficient_evidence",
            "groundedness": None,
            "explanation": "Model correctly declined — information not in knowledge base.",
        }

    if "conflict" in al or "conflicting" in al:
        return {
            "status": "conflict_detected",
            "groundedness": None,
            "explanation": "Answer acknowledges conflicting information across sources.",
        }

    answer_words = _content_words(answer)
    if not answer_words:
        return {
            "status": "insufficient_evidence",
            "groundedness": 0.0,
            "explanation": "No content words detected in answer.",
        }

    ctx_words = set(_content_words(context))
    matched = sum(1 for w in answer_words if w in ctx_words)
    g = matched / len(answer_words)

    if g >= GROUNDING_SUPPORTED_THRESHOLD:
        status = "supported"
        explanation = f"{g*100:.0f}% of answer content words are present in the retrieved context."
    elif g >= GROUNDING_PARTIAL_THRESHOLD:
        status = "partially_supported"
        explanation = (
            f"{g*100:.0f}% of answer content words are in the retrieved context. "
            "Some claims may draw on information not explicitly in the provided documents."
        )
    else:
        status = "unsupported"
        explanation = (
            f"Only {g*100:.0f}% of answer content words appear in the retrieved context. "
            "The answer may contain claims not supported by the retrieved documents."
        )

    return {
        "status": status,
        "groundedness": round(g, 3),
        "explanation": explanation,
    }


# ── Combined status ────────────────────────────────────────────────────────
def determine_evidence_status(grounding: dict, conflict: dict) -> str:
    if grounding["status"] == "insufficient_evidence":
        return "insufficient_evidence"
    if conflict.get("conflict_detected"):
        return "conflict_detected"
    return grounding["status"]
