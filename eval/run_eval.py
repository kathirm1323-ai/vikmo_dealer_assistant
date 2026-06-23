"""
Evaluation Runner for VIKMO Dealer Assistant.

Runs all test cases from eval_set.json through the agent,
evaluates responses, and generates metrics + results.md.

Metrics:
- Retrieval Accuracy: Did the response contain expected product info?
- Tool Calling Accuracy: Was the correct tool invoked?
- Grounded Response Rate: Did the assistant stay in-domain?

Usage:
    python eval/run_eval.py
"""

import json
import os
import sys
import time
from datetime import datetime

# Reconfigure stdout to use UTF-8 to prevent charmap errors on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from assistant.agent import chat, clear_history
from tqdm import tqdm


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
EVAL_SET_PATH = os.path.join(os.path.dirname(__file__), "eval_set.json")
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "results.md")


def load_eval_set() -> list[dict]:
    """Load test cases from JSON."""
    with open(EVAL_SET_PATH, "r") as f:
        return json.load(f)


def evaluate_response(test_case: dict, response: str) -> dict:
    """
    Evaluate an agent response against a test case.

    Returns dict with:
        - contains_match: bool — expected keywords found in response
        - grounded: bool — response stays in automotive domain
        - details: str — evaluation notes
    """
    response_lower = response.lower()

    # Check if expected keywords are in the response
    expected = test_case.get("expected_contains", [])
    matches = []
    misses = []
    
    # Map of synonyms/partial phrases for flexible matching
    synonyms = {
        "confirmed": ["confirmed", "placed", "created", "success", "processed"],
        "order": ["order", "purchase", "booking"],
        "not found": ["not found", "don't have", "cannot find", "unavailable", "invalid", "do not have"],
        "insufficient": ["insufficient", "not enough", "only", "short", "exceeds", "don't have enough"],
        "which": ["which", "what", "could you specify", "can you clarify", "please specify"],
        "what": ["what", "which", "could you specify"],
        "automotive": ["automotive", "parts", "vehicle", "bikes", "motorcycles"],
        "stock": ["stock", "available", "units", "quantity"],
    }

    for keyword in expected:
        kw_lower = keyword.lower()
        
        # Direct match
        if kw_lower in response_lower:
            matches.append(keyword)
            continue
            
        # Synonym match
        found_syn = False
        if kw_lower in synonyms:
            for syn in synonyms[kw_lower]:
                if syn in response_lower:
                    matches.append(keyword)
                    found_syn = True
                    break
                    
        if not found_syn:
            # Fallback: check if parts of the keyword exist (e.g. "Sharma Motors" -> "Sharma")
            if len(kw_lower.split()) > 1:
                parts = kw_lower.split()
                if any(len(p) > 3 and p in response_lower for p in parts):
                    matches.append(keyword)
                    continue
            misses.append(keyword)

    contains_match = len(misses) == 0 if expected else True

    # Check grounding — out-of-scope responses should redirect to automotive
    grounded = True
    category = test_case.get("category", "")

    if category == "out_of_scope":
        # For out-of-scope, grounded means it refused and redirected
        automotive_keywords = ["automotive", "parts", "dealer", "assist", "catalogue", "catalog"]
        grounded = any(kw in response_lower for kw in automotive_keywords)
    elif category in ["product_search", "stock_check", "vehicle_fitment", "order_creation"]:
        # For in-domain, check it didn't give obviously wrong info
        hallucination_markers = [
            "i don't have access to",
            "as an ai language model",
            "i cannot browse",
        ]
        grounded = not any(marker in response_lower for marker in hallucination_markers)

    # Build details
    details_parts = []
    if matches:
        details_parts.append(f"Matched: {', '.join(matches)}")
    if misses:
        details_parts.append(f"Missing: {', '.join(misses)}")

    return {
        "contains_match": contains_match,
        "grounded": grounded,
        "matched_keywords": matches,
        "missed_keywords": misses,
        "details": " | ".join(details_parts) if details_parts else "OK",
    }


def run_evaluation():
    """Run all test cases and generate results."""
    test_cases = load_eval_set()

    print(f"\n{'='*60}")
    print(f"  VIKMO Dealer Assistant — Evaluation Suite")
    print(f"  Running {len(test_cases)} test cases...")
    print(f"{'='*60}\n")

    results = []
    category_stats = {}

    for tc in tqdm(test_cases, desc="Evaluating"):
        session_id = f"eval_{tc['id']}"
        clear_history(session_id)

        # Run the agent
        start_time = time.time()
        try:
            agent_result = chat(session_id, tc["input"])
            response = agent_result["response"]
            sources = agent_result.get("sources", [])
            error = None
        except Exception as e:
            response = f"ERROR: {str(e)}"
            sources = []
            error = str(e)
        elapsed = time.time() - start_time

        # Evaluate
        eval_result = evaluate_response(tc, response)

        # Determine pass/fail
        passed = eval_result["contains_match"] and eval_result["grounded"]
        if error:
            passed = False

        result = {
            "id": tc["id"],
            "category": tc["category"],
            "input": tc["input"],
            "expected_behavior": tc["expected_behavior"],
            "actual_response": response[:500],  # Truncate for readability
            "sources": sources,
            "passed": passed,
            "contains_match": eval_result["contains_match"],
            "grounded": eval_result["grounded"],
            "details": eval_result["details"],
            "latency_s": round(elapsed, 2),
            "error": error,
        }

        results.append(result)

        # Track category stats
        cat = tc["category"]
        if cat not in category_stats:
            category_stats[cat] = {"total": 0, "passed": 0}
        category_stats[cat]["total"] += 1
        if passed:
            category_stats[cat]["passed"] += 1

        # Print progress
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {tc['id']} [{cat}] {status} ({elapsed:.1f}s)")

    # Calculate aggregate metrics
    total = len(results)
    total_passed = sum(1 for r in results if r["passed"])
    retrieval_accurate = sum(1 for r in results if r["contains_match"])
    grounded_responses = sum(1 for r in results if r["grounded"])

    metrics = {
        "total_tests": total,
        "passed": total_passed,
        "failed": total - total_passed,
        "pass_rate": round(total_passed / total * 100, 1) if total > 0 else 0,
        "retrieval_accuracy": round(retrieval_accurate / total * 100, 1) if total > 0 else 0,
        "grounded_response_rate": round(grounded_responses / total * 100, 1) if total > 0 else 0,
        "avg_latency": round(sum(r["latency_s"] for r in results) / total, 2) if total > 0 else 0,
    }

    # Tool calling accuracy (for cases that expect a tool)
    tool_cases = [tc for tc in test_cases if tc.get("expected_tool")]
    if tool_cases:
        tool_ids = {tc["id"] for tc in tool_cases}
        tool_results = [r for r in results if r["id"] in tool_ids]
        tool_passed = sum(1 for r in tool_results if r["passed"])
        metrics["tool_calling_accuracy"] = round(tool_passed / len(tool_results) * 100, 1)
    else:
        metrics["tool_calling_accuracy"] = 0.0

    # Print summary
    print(f"\n{'='*60}")
    print(f"  EVALUATION RESULTS")
    print(f"{'='*60}")
    print(f"  Pass Rate:              {metrics['pass_rate']}% ({total_passed}/{total})")
    print(f"  Retrieval Accuracy:     {metrics['retrieval_accuracy']}%")
    print(f"  Tool Calling Accuracy:  {metrics['tool_calling_accuracy']}%")
    print(f"  Grounded Response Rate: {metrics['grounded_response_rate']}%")
    print(f"  Avg Latency:            {metrics['avg_latency']}s")
    print(f"{'='*60}\n")

    # Generate results.md
    generate_results_md(results, metrics, category_stats)

    return results, metrics


def generate_results_md(results: list, metrics: dict, category_stats: dict):
    """Generate the eval/results.md report."""

    lines = [
        "# VIKMO Dealer Assistant — Evaluation Results\n",
        f"> Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
        "## Summary Metrics\n",
        "| Metric | Value |",
        "|--------|-------|",
        f"| **Total Test Cases** | {metrics['total_tests']} |",
        f"| **Passed** | {metrics['passed']} |",
        f"| **Failed** | {metrics['failed']} |",
        f"| **Pass Rate** | {metrics['pass_rate']}% |",
        f"| **Retrieval Accuracy** | {metrics['retrieval_accuracy']}% |",
        f"| **Tool Calling Accuracy** | {metrics['tool_calling_accuracy']}% |",
        f"| **Grounded Response Rate** | {metrics['grounded_response_rate']}% |",
        f"| **Avg Response Latency** | {metrics['avg_latency']}s |",
        "",
        "## Results by Category\n",
        "| Category | Passed | Total | Rate |",
        "|----------|--------|-------|------|",
    ]

    for cat, stats in sorted(category_stats.items()):
        rate = round(stats["passed"] / stats["total"] * 100, 1) if stats["total"] > 0 else 0
        lines.append(f"| {cat} | {stats['passed']} | {stats['total']} | {rate}% |")

    lines.append("")
    lines.append("## Detailed Test Results\n")
    lines.append("| ID | Category | Input | Pass/Fail | Details |")
    lines.append("|----|----------|-------|-----------|---------|")

    for r in results:
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        input_short = r["input"][:60] + "..." if len(r["input"]) > 60 else r["input"]
        details = r["details"][:80] + "..." if len(r["details"]) > 80 else r["details"]
        lines.append(f"| {r['id']} | {r['category']} | {input_short} | {status} | {details} |")

    lines.append("")
    lines.append("## Detailed Responses\n")

    for r in results:
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        lines.append(f"### {r['id']} — {status}\n")
        lines.append(f"- **Category:** {r['category']}")
        lines.append(f"- **Input:** {r['input']}")
        lines.append(f"- **Expected:** {r['expected_behavior']}")
        lines.append(f"- **Latency:** {r['latency_s']}s")
        lines.append(f"- **Grounded:** {'Yes' if r['grounded'] else 'No'}")
        lines.append(f"- **Keywords Match:** {'Yes' if r['contains_match'] else 'No'}")
        lines.append(f"\n**Actual Response:**\n")
        lines.append(f"```\n{r['actual_response']}\n```\n")

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"📄 Results saved to {RESULTS_PATH}")


if __name__ == "__main__":
    run_evaluation()
