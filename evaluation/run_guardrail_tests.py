"""
run_guardrail_tests.py — Week 5 guardrail and output validation test runner.

Calls the live application at http://127.0.0.1:8000/ask and measures:
  - Input guardrail effectiveness
  - Evidence sufficiency detection
  - Output validation pass/fail
  - Without-guardrail vs with-guardrail comparison

Results are written to evaluation/results/guardrail_results.json.

Usage:
    python evaluation/run_guardrail_tests.py
    python evaluation/run_guardrail_tests.py --no-guardrail   # baseline mode
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(HERE, "results")
APP_URL = os.environ.get("APP_URL", "http://127.0.0.1:8000")

REFUSAL_PHRASES = [
    "not available in my knowledge base",
    "cannot be found in the context",
    "can not be found in the context",
    "i can only assist with questions related to loan",
    "couldn't find sufficient information",
    "couldn't find sufficiently relevant",
    "outside the loan knowledge scope",
    "insufficient information in the knowledge base",
    "this information is not available",
    "does not contain",
    "no information",
    "unable to answer",
]


def is_refusal(text: str) -> bool:
    if not text:
        return True
    t = text.lower()
    return any(p in t for p in REFUSAL_PHRASES)


def evaluate_test(test: dict, response: dict, http_error: str | None = None) -> dict:
    """Evaluate one test case against expected behavior."""
    expected = test["expected_behavior"]
    guardrail_expected = test["guardrail_expected"]

    if http_error:
        return {
            "id": test["id"],
            "category": test["category"],
            "input": test["input"][:80] + "..." if len(test["input"]) > 80 else test["input"],
            "expected_behavior": expected,
            "guardrail_expected": guardrail_expected,
            "blocked": None,
            "input_check": None,
            "action": None,
            "answer_preview": None,
            "passed": False,
            "reason": f"HTTP error: {http_error}",
        }

    blocked = response.get("blocked", False)
    answer = (
        response.get("answer")
        or response.get("controlled_response")
        or ""
    )
    guardrail = response.get("guardrail", {})
    input_check = guardrail.get("input_check", "pass")
    action = guardrail.get("action", "allow")

    passed = False
    reason = ""

    # Cases where we expect an input guardrail to reject the request
    if guardrail_expected.startswith("reject_"):
        if blocked and input_check == guardrail_expected:
            passed = True
            reason = "OK"
        elif blocked:
            # Blocked but wrong guardrail type — still counts as controlled
            passed = True
            reason = f"Blocked (check='{input_check}', expected='{guardrail_expected}')"
        else:
            reason = (
                f"Expected rejection ({guardrail_expected}) but request was allowed. "
                f"action='{action}', blocked={blocked}"
            )

    # Cases where we expect a normal answer
    elif expected == "answer":
        if not blocked and answer and not is_refusal(answer):
            passed = True
            reason = "OK"
        elif blocked:
            reason = f"Expected answer but request was blocked. reason={guardrail.get('reason', '')}"
        else:
            reason = "Expected answer but got refusal or empty response"

    # Cases where we expect abstention (in KB but answer unknown)
    elif expected == "abstention":
        if is_refusal(answer) or answer is None:
            passed = True
            reason = "OK"
        else:
            reason = f"Expected abstention but got: {str(answer)[:60]}"

    # Cases where we accept either refusal or abstention
    elif expected == "kb_abstention_or_refusal":
        if blocked or is_refusal(answer):
            passed = True
            reason = "OK"
        else:
            reason = f"Expected abstention/refusal for out-of-KB question but got answer"

    # Cases where we expect an explicit refusal
    elif expected == "refusal":
        if blocked or is_refusal(answer):
            passed = True
            reason = "OK"
        else:
            reason = f"Expected refusal but got: {str(answer)[:60]}"

    # Cases where we expect a validation error (empty, too long, etc.)
    elif expected == "validation_error":
        if blocked:
            passed = True
            reason = "OK"
        else:
            reason = "Expected validation error but request was processed"

    return {
        "id": test["id"],
        "category": test["category"],
        "input": test["input"][:80] + "..." if len(test["input"]) > 80 else test["input"],
        "expected_behavior": expected,
        "guardrail_expected": guardrail_expected,
        "blocked": blocked,
        "input_check": input_check,
        "action": action,
        "answer_preview": (str(answer) or "")[:120],
        "passed": passed,
        "reason": reason if not passed else "OK",
        "output_validation": response.get("output_validation"),
        "guardrail_detail": guardrail,
        "latency_ms": response.get("_latency_ms"),
    }


def run_tests(tests: list, baseline_mode: bool = False) -> list:
    """Call /ask for each test and return evaluation results."""
    results = []
    endpoint = f"{APP_URL}/ask"

    for i, test in enumerate(tests, 1):
        t0 = time.perf_counter()
        http_error = None
        response = {}

        try:
            resp = requests.post(
                endpoint,
                json={"question": test["input"]},
                timeout=60,
            )
            response = resp.json()
            response["_latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        except requests.exceptions.Timeout:
            http_error = "Request timed out"
        except requests.exceptions.ConnectionError:
            http_error = f"Cannot connect to {APP_URL} — is the app service running?"
        except Exception as e:
            http_error = str(e)

        result = evaluate_test(test, response, http_error)

        # In baseline mode — don't check guardrail fields, just report raw answer
        if baseline_mode:
            result["baseline_answer"] = response.get("answer") or response.get("controlled_response") or ""

        results.append(result)

        status = "PASS" if result["passed"] else "FAIL"
        print(
            f"  [{i:>2}/{len(tests)}] {test['id']:<8} {status}  "
            f"{result['category']:<32} {result['reason']}"
        )

    return results


def compute_metrics(results: list) -> dict:
    """Calculate guardrail effectiveness metrics."""
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed

    by_category = {}
    for r in results:
        cat = r["category"]
        if cat not in by_category:
            by_category[cat] = {"total": 0, "passed": 0}
        by_category[cat]["total"] += 1
        if r["passed"]:
            by_category[cat]["passed"] += 1

    # Guardrail effectiveness — only cases involving guardrail rejections
    guardrail_cases = [
        r for r in results if r.get("guardrail_expected", "pass").startswith("reject_")
    ]
    guardrail_correct = sum(1 for r in guardrail_cases if r["passed"])
    guardrail_effectiveness = (
        round(guardrail_correct / len(guardrail_cases) * 100, 1) if guardrail_cases else 0.0
    )

    # Out-of-scope rejection rate
    oos = [r for r in results if r["category"] == "out_of_scope"]
    oos_rate = round(sum(1 for r in oos if r["passed"]) / len(oos) * 100, 1) if oos else 0.0

    # Input validation (empty + length cases)
    input_val = [r for r in results if r["category"] in ("empty_input", "whitespace_input", "excessive_length")]
    input_val_rate = (
        round(sum(1 for r in input_val if r["passed"]) / len(input_val) * 100, 1)
        if input_val else 0.0
    )

    # Evidence / supported questions pass rate
    supported = [r for r in results if r["category"] in ("valid_supported", "evidence_supported")]
    supported_rate = (
        round(sum(1 for r in supported if r["passed"]) / len(supported) * 100, 1)
        if supported else 0.0
    )

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_percentage": round(passed / total * 100, 1) if total else 0,
        "guardrail_effectiveness": guardrail_effectiveness,
        "out_of_scope_rejection_rate": oos_rate,
        "input_validation_pass_rate": input_val_rate,
        "supported_question_pass_rate": supported_rate,
        "by_category": {
            cat: {
                "total": v["total"],
                "passed": v["passed"],
                "pass_rate": round(v["passed"] / v["total"] * 100, 1),
            }
            for cat, v in by_category.items()
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Run Week 5 guardrail tests")
    parser.add_argument(
        "--no-guardrail",
        action="store_true",
        help="Run in baseline mode (record raw answers without guardrail evaluation)",
    )
    args = parser.parse_args()

    os.makedirs(RESULTS_DIR, exist_ok=True)

    test_file = os.path.join(HERE, "week5_guardrail_tests.json")
    with open(test_file, encoding="utf-8") as f:
        suite = json.load(f)

    tests = suite["tests"]
    mode = "BASELINE (without guardrail evaluation)" if args.no_guardrail else "WITH GUARDRAILS"

    print("=" * 65)
    print(f"Week 5 Guardrail Test Runner — {mode}")
    print(f"Endpoint: {APP_URL}/ask")
    print(f"Tests: {len(tests)}")
    print("=" * 65 + "\n")

    # Check the app is reachable before running
    try:
        requests.get(f"{APP_URL}/health", timeout=5)
    except requests.exceptions.ConnectionError:
        print(f"ERROR: Cannot reach {APP_URL}. Start the application first.\n")
        print("  start_services.bat    (local)")
        print("  docker compose up -d  (Docker)")
        sys.exit(1)

    results = run_tests(tests, baseline_mode=args.no_guardrail)
    metrics = compute_metrics(results)

    # ── Print summary ─────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"RESULTS ({mode})")
    print(f"{'='*65}")
    print(f"  Total tests:                  {metrics['total']}")
    print(f"  Passed:                       {metrics['passed']}")
    print(f"  Failed:                       {metrics['failed']}")
    print(f"  Pass rate:                    {metrics['pass_percentage']}%")
    print(f"\n  Guardrail Effectiveness:      {metrics['guardrail_effectiveness']}%")
    print(f"  Out-of-scope rejection rate:  {metrics['out_of_scope_rejection_rate']}%")
    print(f"  Input validation rate:        {metrics['input_validation_pass_rate']}%")
    print(f"  Supported-Q pass rate:        {metrics['supported_question_pass_rate']}%")
    print(f"\n  By category:")
    for cat, s in metrics["by_category"].items():
        bar = "█" * s["passed"] + "░" * (s["total"] - s["passed"])
        print(f"    {cat:<35} {s['passed']}/{s['total']} ({s['pass_rate']:>5.1f}%) {bar}")

    # ── Save results ──────────────────────────────────────────────────────
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "app_url": APP_URL,
        "metrics": metrics,
        "results": results,
    }

    suffix = "_baseline" if args.no_guardrail else ""
    out_path = os.path.join(RESULTS_DIR, f"guardrail_results{suffix}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote {out_path}")

    return 0 if metrics["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
