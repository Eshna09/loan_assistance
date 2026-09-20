"""
demo_guardrails.py — demonstrate WITHOUT vs WITH guardrail behaviour.

Shows side-by-side results for representative examples:
  1. Out-of-scope question  (Bitcoin price)
  2. Empty input
  3. Excessively long input
  4. Unsupported loan question (bank-specific info not in KB)
  5. Well-supported loan question

Usage:
    python evaluation/demo_guardrails.py
"""

import json
import os
import sys
import textwrap

import requests

APP_URL = os.environ.get("APP_URL", "http://127.0.0.1:8000")

DEMO_CASES = [
    {
        "title": "Out-of-scope — Bitcoin price",
        "input": "What is the current price of Bitcoin?",
        "expected": "BLOCKED by scope guardrail",
    },
    {
        "title": "Empty input",
        "input": "",
        "expected": "BLOCKED by empty-input guardrail",
    },
    {
        "title": "Excessively long input",
        "input": "What is a loan? " + "Tell me everything about loan repayment. " * 40,
        "expected": "BLOCKED by length guardrail",
    },
    {
        "title": "Bank-specific info not in KB",
        "input": "What is the exact processing fee at HDFC Bank for a home loan?",
        "expected": "ALLOWED → LLM abstains (info not in KB)",
    },
    {
        "title": "Well-supported loan question",
        "input": "What does an EMI consist of?",
        "expected": "ALLOWED → grounded answer",
    },
    {
        "title": "Out-of-scope — cricket",
        "input": "Who won yesterday's cricket match?",
        "expected": "BLOCKED by scope guardrail",
    },
]


def call_ask(question: str) -> dict:
    try:
        resp = requests.post(
            f"{APP_URL}/ask",
            json={"question": question},
            timeout=60,
        )
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {"error": f"Cannot connect to {APP_URL}"}
    except Exception as e:
        return {"error": str(e)}


def summarise(response: dict) -> str:
    if "error" in response:
        return f"[CONNECTION ERROR] {response['error']}"

    blocked = response.get("blocked", False)
    guardrail = response.get("guardrail", {})
    action = guardrail.get("action", "allow")
    input_check = guardrail.get("input_check", "pass")
    reason = guardrail.get("reason", "")
    answer = response.get("answer") or response.get("controlled_response") or ""

    if blocked:
        return (
            f"BLOCKED\n"
            f"  input_check:  {input_check}\n"
            f"  action:       {action}\n"
            f"  reason:       {reason}"
        )
    else:
        answer_preview = textwrap.shorten(answer, width=120, placeholder="…")
        output_val = response.get("output_validation", {})
        ov_overall = output_val.get("overall", "n/a") if output_val else "n/a"
        return (
            f"ALLOWED\n"
            f"  input_check:  {input_check}\n"
            f"  action:       {action}\n"
            f"  answer:       {answer_preview}\n"
            f"  output_valid: {ov_overall}"
        )


def main():
    print("=" * 70)
    print("  Loan Knowledge Assistance — Guardrail Demonstration")
    print("  WITHOUT GUARDRAIL vs WITH GUARDRAIL")
    print("=" * 70)

    try:
        requests.get(f"{APP_URL}/health", timeout=5)
    except requests.exceptions.ConnectionError:
        print(f"\nERROR: Cannot reach {APP_URL}. Start the application first.")
        sys.exit(1)

    print(f"\nEndpoint: {APP_URL}/ask")
    print(f"Cases: {len(DEMO_CASES)}\n")

    results = []
    for i, case in enumerate(DEMO_CASES, 1):
        print(f"{'─'*70}")
        print(f"Case {i}: {case['title']}")
        print(f"Input:   {case['input'][:80]}{'...' if len(case['input']) > 80 else ''}")
        print(f"Expect:  {case['expected']}")
        print()

        response = call_ask(case["input"])
        summary = summarise(response)

        blocked = response.get("blocked", False)
        guardrail = response.get("guardrail", {})
        input_check = guardrail.get("input_check", "pass")

        # WITHOUT GUARDRAIL simulation:
        # If the guardrail blocked it, the "without" scenario would have sent
        # the question to the LLM anyway. We show what the guardrail caught.
        print("  WITHOUT GUARDRAIL:")
        if blocked:
            print(f"    ⚠  Would have reached the LLM with uncontrolled question")
            print(f"    ⚠  LLM might answer from general knowledge (hallucination risk)")
        else:
            answer = response.get("answer") or ""
            if answer:
                preview = textwrap.shorten(answer, width=100, placeholder="…")
                print(f"    → LLM answer: {preview}")
            else:
                print(f"    → LLM returned no answer (ollama_error or abstention)")

        print()
        print("  WITH GUARDRAIL (actual result):")
        for line in summary.split("\n"):
            print(f"    {line}")

        results.append({
            "case": case["title"],
            "input": case["input"][:100],
            "expected": case["expected"],
            "blocked": blocked,
            "input_check": input_check,
            "action": guardrail.get("action"),
            "answer_preview": textwrap.shorten(
                response.get("answer") or response.get("controlled_response") or "",
                width=100, placeholder="…"
            ),
        })
        print()

    # ── Summary table ─────────────────────────────────────────────────────
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    blocked_count = sum(1 for r in results if r["blocked"])
    allowed_count = len(results) - blocked_count
    print(f"  Total cases:   {len(results)}")
    print(f"  Blocked:       {blocked_count}  (guardrail acted)")
    print(f"  Allowed:       {allowed_count}  (processed normally)")
    print()
    for r in results:
        status = "🚫 BLOCKED" if r["blocked"] else "✓  ALLOWED"
        print(f"  {status}  {r['case']}")

    # Save demo results
    here = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(here, "results", "demo_results.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
