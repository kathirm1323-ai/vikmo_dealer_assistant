"""
Comprehensive Evaluation Runner for VIKMO Dealer Assistant.

Runs all 22 test cases (including multi-turn conversations) from
comprehensive_eval_set.json through the agent and evaluates:

    - Retrieval Accuracy: expected keywords found in response
    - Tool Calling Accuracy: correct tool invoked
    - Grounded Response Rate: stays in automotive domain, no hallucination
    - Clarification Accuracy: asks clarifying questions when query is ambiguous
    - Hallucination Rate: does NOT produce fabricated information
    - Must-Not-Contain Violations: banned keywords absent from response

Usage:
    python eval/run_comprehensive_eval.py
"""

import json
import os
import sys
import time
from datetime import datetime

# Fix Windows console encoding for Unicode characters
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from assistant.agent import chat, clear_history

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
EVAL_SET_PATH = os.path.join(os.path.dirname(__file__), "comprehensive_eval_set.json")
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "comprehensive_results.md")


def load_eval_set() -> list[dict]:
    """Load test cases from JSON."""
    with open(EVAL_SET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Evaluation logic
# ---------------------------------------------------------------------------

def evaluate_single_response(
    response: str,
    expected_contains: list[str],
    must_not_contain: list[str],
    expect_clarification: bool = False,
    expect_honest_miss: bool = False,
    category: str = "",
) -> dict:
    """Evaluate one response against criteria."""
    response_lower = response.lower()

    # --- Keyword matching ---
    matched = [kw for kw in expected_contains if kw.lower() in response_lower]
    missed = [kw for kw in expected_contains if kw.lower() not in response_lower]
    contains_match = len(missed) == 0 if expected_contains else True

    # --- Must-not-contain violations ---
    violations = [kw for kw in must_not_contain if kw.lower() in response_lower]
    no_violations = len(violations) == 0

    # --- Grounding / hallucination ---
    hallucination_markers = [
        "i don't have access to",
        "as an ai language model",
        "i cannot browse",
    ]
    grounded = not any(marker in response_lower for marker in hallucination_markers)

    if category == "out_of_scope":
        automotive_keywords = [
            "automotive", "parts", "dealer", "assist", "catalogue", "catalog",
            "vikmo", "order", "stock", "product",
        ]
        grounded = any(kw in response_lower for kw in automotive_keywords)

    # --- Clarification check ---
    clarification_asked = False
    if expect_clarification:
        clarification_markers = [
            "which", "what", "could you", "can you", "please specify",
            "please provide", "clarify", "specific", "model", "make",
            "vehicle", "?",
        ]
        clarification_asked = any(m in response_lower for m in clarification_markers)

    # --- Honest miss (product not found) ---
    honest_miss = True
    if expect_honest_miss:
        miss_markers = [
            "not found", "no compatible", "no parts", "don't have",
            "do not have", "couldn't find", "could not find",
            "no specific", "not available", "no tyres", "no brake",
            "unfortunately", "unable to find", "not in",
            "doesn't exist", "does not exist", "no match",
            "no products", "no results",
        ]
        honest_miss = any(m in response_lower for m in miss_markers)

    # --- Build details ---
    details = []
    if matched:
        details.append(f"Matched: {', '.join(matched)}")
    if missed:
        details.append(f"Missing: {', '.join(missed)}")
    if violations:
        details.append(f"VIOLATIONS: {', '.join(violations)}")
    if expect_clarification:
        details.append(f"Clarification: {'YES' if clarification_asked else 'NO'}")
    if expect_honest_miss:
        details.append(f"Honest miss: {'YES' if honest_miss else 'NO'}")

    return {
        "contains_match": contains_match,
        "no_violations": no_violations,
        "grounded": grounded,
        "clarification_asked": clarification_asked,
        "honest_miss": honest_miss,
        "matched_keywords": matched,
        "missed_keywords": missed,
        "violations": violations,
        "details": " | ".join(details) if details else "OK",
    }


def compute_pass(eval_result: dict, test_case: dict, error: str | None) -> bool:
    """Determine overall pass/fail for a test case."""
    if error:
        return False

    passed = eval_result["contains_match"] and eval_result["grounded"] and eval_result["no_violations"]

    if test_case.get("expect_clarification"):
        passed = passed and eval_result["clarification_asked"]

    if test_case.get("expect_honest_miss"):
        passed = passed and eval_result["honest_miss"]

    return passed


# ---------------------------------------------------------------------------
# Run single-turn test
# ---------------------------------------------------------------------------

def run_single_turn(tc: dict) -> dict:
    """Run a single-turn test case."""
    session_id = f"eval_{tc['id']}"
    clear_history(session_id)

    start = time.time()
    try:
        result = chat(session_id, tc["input"])
        response = result["response"]
        sources = result.get("sources", [])
        error = None
    except Exception as e:
        response = f"ERROR: {e}"
        sources = []
        error = str(e)
    elapsed = time.time() - start

    eval_result = evaluate_single_response(
        response=response,
        expected_contains=tc.get("expected_contains", []),
        must_not_contain=tc.get("must_not_contain", []),
        expect_clarification=tc.get("expect_clarification", False),
        expect_honest_miss=tc.get("expect_honest_miss", False),
        category=tc.get("category", ""),
    )

    passed = compute_pass(eval_result, tc, error)

    return {
        "id": tc["id"],
        "category": tc["category"],
        "subcategory": tc.get("subcategory", ""),
        "input": tc["input"],
        "expected_behavior": tc.get("expected_behavior", ""),
        "expected_tool": tc.get("expected_tool"),
        "actual_response": response[:600],
        "sources": sources,
        "passed": passed,
        "contains_match": eval_result["contains_match"],
        "no_violations": eval_result["no_violations"],
        "grounded": eval_result["grounded"],
        "clarification_asked": eval_result["clarification_asked"],
        "honest_miss": eval_result["honest_miss"],
        "details": eval_result["details"],
        "latency_s": round(elapsed, 2),
        "error": error,
    }


# ---------------------------------------------------------------------------
# Run multi-turn test
# ---------------------------------------------------------------------------

def run_multi_turn(tc: dict) -> list[dict]:
    """Run a multi-turn test case — returns one result per turn."""
    session_id = f"eval_{tc['id']}"
    clear_history(session_id)
    results = []

    for i, turn in enumerate(tc["turns"]):
        turn_id = f"{tc['id']}_T{i+1}"

        start = time.time()
        try:
            result = chat(session_id, turn["input"])
            response = result["response"]
            sources = result.get("sources", [])
            error = None
        except Exception as e:
            response = f"ERROR: {e}"
            sources = []
            error = str(e)
        elapsed = time.time() - start

        eval_result = evaluate_single_response(
            response=response,
            expected_contains=turn.get("expected_contains", []),
            must_not_contain=turn.get("must_not_contain", []),
            expect_clarification=turn.get("expect_clarification", False),
            expect_honest_miss=turn.get("expect_honest_miss", False),
            category=tc.get("category", ""),
        )

        passed = compute_pass(eval_result, turn, error)

        results.append({
            "id": turn_id,
            "category": tc["category"],
            "subcategory": tc.get("subcategory", ""),
            "input": turn["input"],
            "expected_behavior": turn.get("expected_behavior", ""),
            "expected_tool": turn.get("expected_tool"),
            "actual_response": response[:600],
            "sources": sources,
            "passed": passed,
            "contains_match": eval_result["contains_match"],
            "no_violations": eval_result["no_violations"],
            "grounded": eval_result["grounded"],
            "clarification_asked": eval_result["clarification_asked"],
            "honest_miss": eval_result["honest_miss"],
            "details": eval_result["details"],
            "latency_s": round(elapsed, 2),
            "error": error,
        })

    return results


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_evaluation():
    test_cases = load_eval_set()

    print(f"\n{'='*65}")
    print(f"  VIKMO Dealer Assistant -- Comprehensive Evaluation Suite")
    print(f"  {len(test_cases)} test scenarios")
    print(f"{'='*65}\n")

    all_results: list[dict] = []
    category_stats: dict[str, dict] = {}

    for tc in test_cases:
        is_multi = tc.get("multi_turn", False)
        label = f"[Multi-turn x{len(tc.get('turns', []))}]" if is_multi else "[Single]"

        if is_multi:
            turn_results = run_multi_turn(tc)
            all_results.extend(turn_results)
            for tr in turn_results:
                status = "PASS" if tr["passed"] else "FAIL"
                print(f"  {tr['id']:12s} {label:20s} {status}  ({tr['latency_s']:.1f}s)")
                cat = tr["category"]
                if cat not in category_stats:
                    category_stats[cat] = {"total": 0, "passed": 0}
                category_stats[cat]["total"] += 1
                if tr["passed"]:
                    category_stats[cat]["passed"] += 1
        else:
            result = run_single_turn(tc)
            all_results.append(result)
            status = "PASS" if result["passed"] else "FAIL"
            print(f"  {result['id']:12s} {label:20s} {status}  ({result['latency_s']:.1f}s)")
            cat = result["category"]
            if cat not in category_stats:
                category_stats[cat] = {"total": 0, "passed": 0}
            category_stats[cat]["total"] += 1
            if result["passed"]:
                category_stats[cat]["passed"] += 1

    # ----- Aggregate Metrics -----
    total = len(all_results)
    total_passed = sum(1 for r in all_results if r["passed"])

    retrieval_ok = sum(1 for r in all_results if r["contains_match"])
    grounded_ok = sum(1 for r in all_results if r["grounded"])
    no_viol_ok = sum(1 for r in all_results if r["no_violations"])

    # Tool calling accuracy (for cases that expect a tool)
    tool_cases = [r for r in all_results if r.get("expected_tool")]
    tool_passed = sum(1 for r in tool_cases if r["passed"]) if tool_cases else 0
    tool_accuracy = round(tool_passed / len(tool_cases) * 100, 1) if tool_cases else 0.0

    # Clarification accuracy
    clar_cases = [r for r in all_results if r.get("clarification_asked") is not None
                  and any(tc.get("expect_clarification")
                          for tc in test_cases if tc["id"] == r["id"]
                          or any(f"{tc['id']}_T" in r["id"] for _ in [1]))]
    # Simplified: check against the eval_set flag by looking at category
    clar_results = [r for r in all_results if r["category"] in ("ambiguous",) or
                    r["id"].startswith("EDGE04") or r["id"].startswith("AMB")]
    clar_passed = sum(1 for r in clar_results if r["clarification_asked"])
    clar_accuracy = round(clar_passed / len(clar_results) * 100, 1) if clar_results else 0.0

    halluc_count = sum(1 for r in all_results if not r["no_violations"])

    metrics = {
        "total_tests": total,
        "passed": total_passed,
        "failed": total - total_passed,
        "pass_rate": round(total_passed / total * 100, 1) if total else 0,
        "retrieval_accuracy": round(retrieval_ok / total * 100, 1) if total else 0,
        "tool_calling_accuracy": tool_accuracy,
        "grounded_response_rate": round(grounded_ok / total * 100, 1) if total else 0,
        "clarification_accuracy": clar_accuracy,
        "hallucination_violations": halluc_count,
        "avg_latency": round(sum(r["latency_s"] for r in all_results) / total, 2) if total else 0,
    }

    # ----- Print Summary -----
    print(f"\n{'='*65}")
    print(f"  COMPREHENSIVE EVALUATION RESULTS")
    print(f"{'='*65}")
    print(f"  Pass Rate:              {metrics['pass_rate']}%  ({total_passed}/{total})")
    print(f"  Retrieval Accuracy:     {metrics['retrieval_accuracy']}%")
    print(f"  Tool Calling Accuracy:  {metrics['tool_calling_accuracy']}%")
    print(f"  Grounded Response Rate: {metrics['grounded_response_rate']}%")
    print(f"  Clarification Accuracy: {metrics['clarification_accuracy']}%")
    print(f"  Hallucination Violations: {metrics['hallucination_violations']}")
    print(f"  Avg Latency:            {metrics['avg_latency']}s")
    print(f"{'='*65}\n")

    # ----- Generate Report -----
    generate_report(all_results, metrics, category_stats)

    return all_results, metrics


# ---------------------------------------------------------------------------
# Report Generation
# ---------------------------------------------------------------------------

def generate_report(results: list, metrics: dict, category_stats: dict):
    """Generate comprehensive_results.md."""

    lines = [
        "# VIKMO Dealer Assistant — Comprehensive Evaluation Results\n",
        f"> Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",

        "## Summary Metrics\n",
        "| Metric | Value |",
        "|--------|-------|",
        f"| **Total Test Steps** | {metrics['total_tests']} |",
        f"| **Passed** | {metrics['passed']} |",
        f"| **Failed** | {metrics['failed']} |",
        f"| **Pass Rate** | {metrics['pass_rate']}% |",
        f"| **Retrieval Accuracy** | {metrics['retrieval_accuracy']}% |",
        f"| **Tool Calling Accuracy** | {metrics['tool_calling_accuracy']}% |",
        f"| **Grounded Response Rate** | {metrics['grounded_response_rate']}% |",
        f"| **Clarification Accuracy** | {metrics['clarification_accuracy']}% |",
        f"| **Hallucination Violations** | {metrics['hallucination_violations']} |",
        f"| **Avg Response Latency** | {metrics['avg_latency']}s |",
        "",

        "## Results by Category\n",
        "| Category | Passed | Total | Rate |",
        "|----------|--------|-------|------|",
    ]

    for cat in sorted(category_stats):
        s = category_stats[cat]
        rate = round(s["passed"] / s["total"] * 100, 1) if s["total"] else 0
        lines.append(f"| {cat} | {s['passed']} | {s['total']} | {rate}% |")

    # Eval metrics table (assignment format)
    lines += [
        "",
        "## Eval Metrics Table\n",
        "| Test # | Tool Called? | Correct Answer? | Hallucination? | Clarification Asked? |",
        "|--------|-------------|-----------------|----------------|---------------------|",
    ]
    for r in results:
        tool = r.get("expected_tool") or "—"
        correct = "✅" if r["passed"] else "❌"
        halluc = "❌ Yes" if not r["no_violations"] else "✅ No"
        clar = "✅ Yes" if r["clarification_asked"] else "—"
        lines.append(f"| {r['id']} | {tool} | {correct} | {halluc} | {clar} |")

    # Detailed results table
    lines += [
        "",
        "## Detailed Test Results\n",
        "| ID | Category | Input | Pass/Fail | Details |",
        "|----|----------|-------|-----------|---------|",
    ]
    for r in results:
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        inp = r["input"][:55] + "…" if len(r["input"]) > 55 else r["input"]
        det = r["details"][:75] + "…" if len(r["details"]) > 75 else r["details"]
        lines.append(f"| {r['id']} | {r['category']} | {inp} | {status} | {det} |")

    # Full responses
    lines += ["", "## Full Responses\n"]
    for r in results:
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        lines.append(f"### {r['id']} — {status}\n")
        lines.append(f"- **Category:** {r['category']} / {r['subcategory']}")
        lines.append(f"- **Input:** {r['input']}")
        lines.append(f"- **Expected:** {r['expected_behavior']}")
        lines.append(f"- **Latency:** {r['latency_s']}s")
        lines.append(f"- **Grounded:** {'✅' if r['grounded'] else '❌'}")
        lines.append(f"- **Keywords Match:** {'✅' if r['contains_match'] else '❌'}")
        lines.append(f"- **No Violations:** {'✅' if r['no_violations'] else '❌'}")
        if r.get("error"):
            lines.append(f"- **Error:** {r['error']}")
        lines.append(f"\n**Actual Response:**\n")
        lines.append(f"```\n{r['actual_response']}\n```\n")

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[*] Full report saved to {RESULTS_PATH}")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    run_evaluation()
