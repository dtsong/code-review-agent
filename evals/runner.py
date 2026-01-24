"""Evaluation runner for PR review agent.

Runs evaluation suites against the PR review agent without GitHub/Supabase dependencies.
Focuses on measuring precision, recall, F1, and confidence accuracy.
"""

import argparse
import sys
import time
from pathlib import Path

import yaml

from .scoring import EvalResult, EvalSuite, calculate_metrics


def load_eval_suite(suite_path: Path) -> EvalSuite:
    """Load evaluation suite from directory of YAML case files."""
    cases = []
    case_files = list(suite_path.glob("*.yaml")) + list(suite_path.glob("*.yml"))

    if not case_files:
        raise ValueError(f"No YAML case files found in {suite_path}")

    for case_file in sorted(case_files):
        with open(case_file) as f:
            case_data = yaml.safe_load(f)
            cases.append(case_data)

    return EvalSuite(cases=cases, suite_name=suite_path.name)


def run_evaluation(
    suite: EvalSuite,
    anthropic_key: str,
    verbose: bool = False
) -> EvalResult:
    """Run evaluation suite against the PR review agent."""
    from pr_review_agent.config import load_config
    from pr_review_agent.review.llm_reviewer import LLMReviewer

    start_time = time.time()
    reviewer = LLMReviewer(anthropic_key)

    # Load default config for consistency
    config = load_config(Path(".ai-review.yaml"))

    results = []
    total_cost = 0.0

    print(f"Running evaluation suite: {suite.suite_name}")
    print(f"Cases to evaluate: {len(suite.cases)}")
    print()

    for i, case in enumerate(suite.cases, 1):
        case_name = case.get("name", f"case_{i}")
        diff_file = case["diff_file"]
        expected_issues = case["expected_issues"]
        expected_confidence_range = case.get("expected_confidence", [0.0, 1.0])

        if verbose:
            print(f"  [{i}/{len(suite.cases)}] {case_name}")

        # Read diff content
        diff_path = Path("evals/diffs") / diff_file
        if not diff_path.exists():
            raise FileNotFoundError(f"Diff file not found: {diff_path}")

        with open(diff_path) as f:
            diff_content = f.read()

        # Run review (using lightweight model for speed)
        try:
            review_result = reviewer.review(
                diff=diff_content,
                pr_description=case.get("pr_description", ""),
                model="haiku",  # Use fastest model for evals
                config=config,
                focus_areas=case.get("focus_areas", [])
            )

            case_result = {
                "case_name": case_name,
                "predicted_issues": review_result.issues,
                "expected_issues": expected_issues,
                "predicted_confidence": review_result.confidence,
                "expected_confidence_range": expected_confidence_range,
                "tokens_used": getattr(review_result, 'tokens_used', 0),
                "cost_usd": getattr(review_result, 'cost_usd', 0.0),
                "success": True,
                "error": None
            }
            total_cost += case_result["cost_usd"]

        except Exception as e:
            case_result = {
                "case_name": case_name,
                "predicted_issues": [],
                "expected_issues": expected_issues,
                "predicted_confidence": 0.0,
                "expected_confidence_range": expected_confidence_range,
                "tokens_used": 0,
                "cost_usd": 0.0,
                "success": False,
                "error": str(e)
            }
            if verbose:
                print(f"    ERROR: {e}")

        results.append(case_result)

        if verbose and case_result["success"]:
            print(f"    Found {len(case_result['predicted_issues'])} issues "
                  f"(expected {len(expected_issues)})")

    duration = time.time() - start_time

    return EvalResult(
        suite_name=suite.suite_name,
        case_results=results,
        total_cost_usd=total_cost,
        duration_seconds=duration
    )


def main() -> int:
    """CLI entry point for evaluation runner."""
    parser = argparse.ArgumentParser(
        description="Evaluate PR review agent performance",
        prog="pr-review-eval"
    )
    parser.add_argument(
        "--suite",
        required=True,
        type=Path,
        help="Path to evaluation suite directory (contains YAML case files)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Save detailed results to JSON file"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output during evaluation"
    )

    args = parser.parse_args()

    # Get Anthropic API key
    import os
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if not anthropic_key:
        print("Error: ANTHROPIC_API_KEY environment variable required", file=sys.stderr)
        return 1

    try:
        # Load evaluation suite
        suite = load_eval_suite(args.suite)

        # Run evaluation
        result = run_evaluation(suite, anthropic_key, verbose=args.verbose)

        # Calculate and display metrics
        metrics = calculate_metrics(result)

        print("\n" + "="*50)
        print("EVALUATION RESULTS")
        print("="*50)
        print(f"Suite: {result.suite_name}")
        print(f"Cases: {len(result.case_results)}")
        print(f"Duration: {result.duration_seconds:.1f}s")
        print(f"Total Cost: ${result.total_cost_usd:.4f}")
        print()

        print("METRICS:")
        print(f"  Precision:     {metrics.precision:.3f}")
        print(f"  Recall:        {metrics.recall:.3f}")
        print(f"  F1 Score:      {metrics.f1:.3f}")
        print(f"  Confidence MAE: {metrics.confidence_mae:.3f}")
        print(f"  False Pos Rate: {metrics.false_positive_rate:.3f}")
        print(f"  Success Rate:   {metrics.success_rate:.3f}")
        print()

        # Show failed cases
        failed_cases = [r for r in result.case_results if not r["success"]]
        if failed_cases:
            print("FAILED CASES:")
            for case in failed_cases:
                print(f"  {case['case_name']}: {case['error']}")
            print()

        # Save detailed results if requested
        if args.output:
            import json
            output_data = {
                "result": result.__dict__,
                "metrics": metrics.__dict__
            }
            # Convert any non-serializable objects
            output_json = json.dumps(output_data, indent=2, default=str)
            args.output.write_text(output_json)
            print(f"Detailed results saved to {args.output}")

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())