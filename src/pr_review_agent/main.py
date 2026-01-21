"""CLI entrypoint for PR Review Agent."""

import argparse
import fnmatch
import os
import sys
import time
from pathlib import Path
from typing import Any

from pr_review_agent.config import load_config
from pr_review_agent.gates.lint_gate import run_lint
from pr_review_agent.gates.size_gate import check_size
from pr_review_agent.github_client import GitHubClient
from pr_review_agent.metrics.supabase_logger import SupabaseLogger
from pr_review_agent.output.console import print_results
from pr_review_agent.output.github_comment import format_as_markdown
from pr_review_agent.review.confidence import calculate_confidence
from pr_review_agent.review.llm_reviewer import LLMReviewer
from pr_review_agent.review.model_selector import select_model


def run_review(
    repo: str,
    pr_number: int,
    github_token: str,
    anthropic_key: str,
    config_path: Path | None,
    post_comment: bool = False,
    supabase_url: str | None = None,
    supabase_key: str | None = None,
) -> dict[str, Any]:
    """Run the full PR review pipeline.

    Returns dict with results for metrics logging.
    """
    start_time = time.time()

    # Load config
    config = load_config(config_path or Path(".ai-review.yaml"))

    # Initialize clients
    github = GitHubClient(github_token)

    # Fetch PR data
    owner, repo_name = repo.split("/")
    pr = github.fetch_pr(owner, repo_name, pr_number)

    # Initialize result tracking
    result: dict[str, Any] = {
        "pr_number": pr_number,
        "repo": repo,
        "size_gate_passed": False,
        "lint_gate_passed": False,
        "llm_called": False,
        "confidence_score": 0.0,
        "comment_posted": False,
    }

    # Gate 1: Size check
    size_result = check_size(pr, config)
    result["size_gate_passed"] = size_result.passed

    if not size_result.passed:
        print_results(pr, size_result, None, None, None)
        result["duration_ms"] = int((time.time() - start_time) * 1000)
        return result

    # Gate 2: Lint check
    # Filter files based on ignore patterns
    files_to_lint = [
        f for f in pr.files_changed
        if not any(_match_pattern(f, p) for p in config.ignore)
    ]
    lint_result = run_lint(files_to_lint, config)
    result["lint_gate_passed"] = lint_result.passed

    if not lint_result.passed:
        print_results(pr, size_result, lint_result, None, None)
        result["duration_ms"] = int((time.time() - start_time) * 1000)
        return result

    # All gates passed - run LLM review
    llm_reviewer = LLMReviewer(anthropic_key)
    model = select_model(pr, config)
    review_result = llm_reviewer.review(
        diff=pr.diff,
        pr_description=pr.description,
        model=model,
        config=config,
    )
    result["llm_called"] = True

    # Calculate confidence
    confidence = calculate_confidence(review_result, pr, config)
    result["confidence_score"] = confidence.score

    # Output results
    print_results(pr, size_result, lint_result, review_result, confidence)

    # Post comment to GitHub if requested
    if post_comment and review_result:
        comment_body = format_as_markdown(review_result, confidence)
        comment_url = github.post_comment(owner, repo_name, pr_number, comment_body)
        result["comment_posted"] = True
        result["comment_url"] = comment_url
        print(f"\nComment posted: {comment_url}")

    result["duration_ms"] = int((time.time() - start_time) * 1000)

    # Log metrics to Supabase if configured
    if supabase_url and supabase_key and review_result:
        try:
            logger = SupabaseLogger(supabase_url, supabase_key)
            outcome = "approved" if confidence.level == "high" else (
                "changes_requested" if confidence.level == "medium" else "escalated"
            )
            logger.log_review(
                pr=pr,
                size_result=size_result,
                lint_result=lint_result,
                review_result=review_result,
                confidence=confidence,
                outcome=outcome,
                duration_ms=result["duration_ms"],
            )
            result["metrics_logged"] = True
        except Exception:
            result["metrics_logged"] = False

    return result


def _match_pattern(filename: str, pattern: str) -> bool:
    """Simple glob pattern matching."""
    return fnmatch.fnmatch(filename, pattern)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="AI-powered PR review agent",
        prog="pr-review-agent",
    )
    parser.add_argument("--repo", required=True, help="GitHub repo (owner/repo)")
    parser.add_argument("--pr", required=True, type=int, help="PR number")
    parser.add_argument("--config", default=".ai-review.yaml", help="Config file path")
    parser.add_argument("--post-comment", action="store_true", help="Post comment to GitHub")

    args = parser.parse_args()

    # Get credentials from environment
    github_token = os.environ.get("GITHUB_TOKEN")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    if not github_token:
        print("Error: GITHUB_TOKEN environment variable required", file=sys.stderr)
        return 1

    if not anthropic_key:
        print("Error: ANTHROPIC_API_KEY environment variable required", file=sys.stderr)
        return 1

    try:
        run_review(
            repo=args.repo,
            pr_number=args.pr,
            github_token=github_token,
            anthropic_key=anthropic_key,
            config_path=Path(args.config) if args.config else None,
            post_comment=args.post_comment,
            supabase_url=supabase_url,
            supabase_key=supabase_key,
        )
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
