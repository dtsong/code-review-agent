"""CLI entrypoint for PR Review Agent."""

import argparse
import base64
import fnmatch
import os
import sys
import time
from pathlib import Path
from typing import Any

from pr_review_agent.analysis.pre_analyzer import analyze_pr
from pr_review_agent.config import load_config
from pr_review_agent.escalation.webhook import build_payload, send_webhook, should_escalate
from pr_review_agent.execution.retry_handler import RetryStrategy, retry_with_adaptation
from pr_review_agent.gates.lint_gate import run_lint
from pr_review_agent.gates.security_gate import run_security_scan
from pr_review_agent.gates.size_gate import check_size
from pr_review_agent.github_client import GitHubClient
from pr_review_agent.metrics.supabase_logger import SupabaseLogger
from pr_review_agent.output.console import print_results
from pr_review_agent.output.github_comment import format_as_markdown
from pr_review_agent.review.confidence import calculate_confidence
from pr_review_agent.review.llm_reviewer import LLMReviewer, LLMReviewResult


def run_review(
    repo: str,
    pr_number: int,
    github_client: GitHubClient,
    anthropic_key: str,
    config_path: Path | None,
    post_comment: bool = False,
    supabase_url: str | None = None,
    supabase_key: str | None = None,
) -> dict[str, Any]:
    """Run the full PR review pipeline with adaptive strategy.

    Returns dict with results for metrics logging.
    """
    start_time = time.time()

    # Load config
    config = load_config(config_path or Path(".ai-review.yaml"))

    # Use provided GitHub client
    github = github_client

    # Fetch PR data
    owner, repo_name = repo.split("/")
    pr = github.fetch_pr(owner, repo_name, pr_number)

    # Initialize result tracking
    result: dict[str, Any] = {
        "pr_number": pr_number,
        "repo": repo,
        "size_gate_passed": False,
        "lint_gate_passed": False,
        "security_gate_passed": False,
        "llm_called": False,
        "confidence_score": 0.0,
        "comment_posted": False,
    }

    # Step 1: Pre-analysis (new agentic capability)
    print(f"\n🔍 Analyzing PR #{pr_number}...")
    analysis = analyze_pr(pr)
    print(f"   Type: {analysis.pr_type.value}")
    print(f"   Risk: {analysis.risk_level.value}")
    print(f"   Complexity: {analysis.complexity}")
    print(f"   Focus: {', '.join(analysis.focus_areas)}")
    print(f"   Model: {analysis.suggested_model}")
    print()

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
        f for f in pr.files_changed if not any(_match_pattern(f, p) for p in config.ignore)
    ]
    lint_result = run_lint(files_to_lint, config)
    result["lint_gate_passed"] = lint_result.passed

    if not lint_result.passed:
        print_results(pr, size_result, lint_result, None, None)
        result["duration_ms"] = int((time.time() - start_time) * 1000)
        return result

    # Gate 3: Security scan
    security_result = run_security_scan(files_to_lint, config)
    result["security_gate_passed"] = security_result.passed

    if not security_result.passed:
        print(f"\n🔒 Security gate failed: {security_result.recommendation}")
        result["duration_ms"] = int((time.time() - start_time) * 1000)
        return result

    # All gates passed - run LLM review with adaptive retry
    llm_reviewer = LLMReviewer(anthropic_key)

    # Use the model suggested by pre-analysis
    base_model = analysis.suggested_model

    def do_review(strategy: RetryStrategy) -> LLMReviewResult:
        """Execute review with the given strategy."""
        print(f"   Attempt with {strategy.model}...")
        return llm_reviewer.review(
            diff=pr.diff,
            pr_description=pr.description,
            model=strategy.model,
            config=config,
            focus_areas=analysis.focus_areas,
        )

    def validate_review(review: LLMReviewResult) -> bool:
        """Validate the review has meaningful content."""
        return review is not None and len(review.summary) > 20

    print("🤖 Running LLM Review...")
    review_result = retry_with_adaptation(
        operation=do_review,
        base_model=base_model,
        max_attempts=3,
        validator=validate_review,
    )
    print("   ✓ Review complete (confidence check pending)")
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

    # Escalation webhook for low-confidence reviews
    if should_escalate(confidence, config.escalation):
        escalation_payload = build_payload(pr, confidence, review_result.summary)
        webhook_sent = send_webhook(escalation_payload, config.escalation)
        result["escalation_sent"] = webhook_sent
        if webhook_sent:
            print("\n⚠️  Low confidence — escalation webhook sent")

    result["duration_ms"] = int((time.time() - start_time) * 1000)

    # Log metrics to Supabase if configured
    if supabase_url and supabase_key and review_result:
        try:
            logger = SupabaseLogger(supabase_url, supabase_key)
            outcome = (
                "approved"
                if confidence.level == "high"
                else ("changes_requested" if confidence.level == "medium" else "escalated")
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
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="AI-powered PR review agent",
        prog="pr-review-agent",
    )
    parser.add_argument("--repo", help="GitHub repo (owner/repo)")
    parser.add_argument("--pr", type=int, help="PR number")
    parser.add_argument("--config", default=".ai-review.yaml", help="Config file path")
    parser.add_argument("--post-comment", action="store_true", help="Post comment to GitHub")
    parser.add_argument(
        "--eval",
        action="store_true",
        help="Run in evaluation mode (redirects to eval runner)"
    )

    args = parser.parse_args()

    # Handle evaluation mode
    if args.eval:
        print("Evaluation mode enabled - use 'uv run pr-review-eval --suite evals/cases/' instead")
        return 1

    # Validate required arguments for normal mode
    if not args.repo or not args.pr:
        parser.error("--repo and --pr are required for normal operation")

    # Get credentials from environment
    github_token = os.environ.get("GITHUB_TOKEN")
    app_id = os.environ.get("GITHUB_APP_ID")
    app_installation_id = os.environ.get("GITHUB_APP_INSTALLATION_ID")
    app_private_key_b64 = os.environ.get("GITHUB_APP_PRIVATE_KEY_BASE64")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    # Create GitHub client (prefer App credentials for cross-repo access)
    if app_id and app_installation_id and app_private_key_b64:
        # Handle both raw PEM and base64-encoded PEM
        key_value = app_private_key_b64.strip()
        if "-----BEGIN" in key_value:
            # Raw PEM key - may have escaped newlines from env var
            private_key = key_value.replace("\\n", "\n")
        else:
            # Base64-encoded PEM key
            private_key = base64.b64decode(key_value).decode("utf-8")
        github_client = GitHubClient.from_app_credentials(
            app_id, app_installation_id, private_key
        )
    elif github_token:
        github_client = GitHubClient(github_token)
    else:
        print(
            "Error: Either GITHUB_TOKEN or GitHub App credentials "
            "(GITHUB_APP_ID, GITHUB_APP_INSTALLATION_ID, GITHUB_APP_PRIVATE_KEY_BASE64) required",
            file=sys.stderr,
        )
        return 1

    if not anthropic_key:
        print("Error: ANTHROPIC_API_KEY environment variable required", file=sys.stderr)
        return 1

    try:
        run_review(
            repo=args.repo,
            pr_number=args.pr,
            github_client=github_client,
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
