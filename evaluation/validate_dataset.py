"""
validate_dataset.py — validate eval_set.json for Week 5 completeness.

Checks:
  1. JSON is valid
  2. Total question count (25-30)
  3. All 17 categories are represented
  4. Referenced source_files exist on disk
  5. Referenced expected_sources exist in backend/finance_kb/
  6. No duplicate question text
  7. Prints category distribution

Exit 0 if all checks pass, 1 if any fail.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KB_DIR = os.path.join(ROOT, "backend", "finance_kb")

REQUIRED_CATEGORIES = [
    "policy_explanation",
    "information_retrieval",
    "comparison",
    "conflict_detection",
    "version_resolution",
    "eligibility_analysis",
    "fee_calculation",
    "rag_based",
    "out_of_scope",
    "evidence_grounding",
    "code_explanation",
    "code_retrieval",
    "dependency_understanding",
    "bug_analysis",
    "code_generation",
    "refactoring",
    "rag_based_code_doc",
]

EVAL_SET_PATH = os.path.join(HERE, "eval_set.json")

errors = []
warnings = []


def check(condition, msg):
    if not condition:
        errors.append(f"  FAIL: {msg}")
    return condition


def warn(msg):
    warnings.append(f"  WARN: {msg}")


# ── 1. Load and validate JSON ─────────────────────────────────────────────
print("=" * 60)
print("Loan Knowledge Assistance — Dataset Validation")
print("=" * 60)

try:
    with open(EVAL_SET_PATH, encoding="utf-8") as f:
        data = json.load(f)
    print(f"\n[1] JSON validity:         PASS  ({EVAL_SET_PATH})")
except json.JSONDecodeError as e:
    print(f"\n[1] JSON validity:         FAIL  ({e})")
    sys.exit(1)
except FileNotFoundError:
    print(f"\n[1] JSON validity:         FAIL  (file not found: {EVAL_SET_PATH})")
    sys.exit(1)

questions = data.get("questions", [])

# ── 2. Question count ─────────────────────────────────────────────────────
total = len(questions)
count_ok = 25 <= total <= 30
print(f"[2] Question count:        {'PASS' if count_ok else 'WARN'}  ({total} questions, expected 25-30)")
if not count_ok:
    warn(f"Question count is {total}, expected between 25 and 30.")

# ── 3. Category distribution ──────────────────────────────────────────────
cat_counts = {}
for q in questions:
    cat = q.get("category", "MISSING")
    cat_counts[cat] = cat_counts.get(cat, 0) + 1

missing_cats = [c for c in REQUIRED_CATEGORIES if c not in cat_counts]
all_cats_ok = len(missing_cats) == 0

print(f"[3] All 17 categories:     {'PASS' if all_cats_ok else 'FAIL'}")
print(f"\n    Category distribution:")
for cat in REQUIRED_CATEGORIES:
    count = cat_counts.get(cat, 0)
    status = "✓" if count > 0 else "✗"
    print(f"      {status} {cat:<30} {count} question(s)")

extra_cats = [c for c in cat_counts if c not in REQUIRED_CATEGORIES]
if extra_cats:
    for c in extra_cats:
        print(f"      + {c:<30} {cat_counts[c]} question(s)  [extra]")

if missing_cats:
    for c in missing_cats:
        errors.append(f"  FAIL: Missing category '{c}'")

# ── 4. source_files exist on disk ─────────────────────────────────────────
print(f"\n[4] source_files exist:")
sf_errors = []
for q in questions:
    for sf in q.get("source_files", []):
        full = os.path.join(ROOT, sf.replace("/", os.sep))
        if not os.path.isfile(full):
            sf_errors.append(f"  FAIL: {q['id']} references '{sf}' — not found at {full}")

if sf_errors:
    for e in sf_errors:
        print(f"    {e}")
    errors.extend(sf_errors)
else:
    print(f"    PASS  (all source_files found)")

# ── 5. expected_sources exist in finance_kb ───────────────────────────────
print(f"\n[5] expected_sources in finance_kb:")
es_errors = []
for q in questions:
    for src in q.get("expected_sources", []):
        kb_path = os.path.join(KB_DIR, src)
        if not os.path.isfile(kb_path):
            es_errors.append(f"  FAIL: {q['id']} references source '{src}' — not found in {KB_DIR}")

if es_errors:
    for e in es_errors:
        print(f"    {e}")
    errors.extend(es_errors)
else:
    print(f"    PASS  (all expected_sources found)")

# ── 6. Duplicate questions ────────────────────────────────────────────────
print(f"\n[6] Duplicate check:")
seen_text = {}
dup_errors = []
for q in questions:
    text = q.get("question", "").strip().lower()
    if text in seen_text:
        dup_errors.append(
            f"  FAIL: Duplicate question text — '{q['id']}' matches '{seen_text[text]}'"
        )
    else:
        seen_text[text] = q["id"]

if dup_errors:
    for e in dup_errors:
        print(f"    {e}")
    errors.extend(dup_errors)
else:
    print(f"    PASS  (no duplicates found)")

# ── Summary ───────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
if errors:
    print(f"RESULT: FAIL  ({len(errors)} error(s), {len(warnings)} warning(s))")
    for e in errors:
        print(e)
    sys.exit(1)
else:
    if warnings:
        print(f"RESULT: PASS with warnings  ({len(warnings)} warning(s))")
        for w in warnings:
            print(w)
    else:
        print(f"RESULT: PASS  ({total} questions, all 17 categories present, no issues)")
    sys.exit(0)
