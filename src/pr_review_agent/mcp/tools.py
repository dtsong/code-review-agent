"""MCP tools exposing review agent functionality."""

import os
from pathlib import Path

from mcp.types import TextContent, Tool

from pr_review_agent.mcp.server import get_anthropic_key, get_github_token, server


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return available MCP tools."""
    return [
        Tool(
            name="review_pr",
            description="Run the full review pipeline on a GitHub PR",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "GitHub repo in owner/repo format",
                    },
                    "pr_number": {
                        "type": "integer",
                        "description": "PR number to review",
                    },
                },
                "required": ["repo", "pr_number"],
            },
        ),
        Tool(
            name="check_pr_size",
            description="Run only the size gate on a PR",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "GitHub repo in owner/repo format",
                    },
                    "pr_number": {
                        "type": "integer",
                        "description": "PR number to check",
                    },
                },
                "required": ["repo", "pr_number"],
            },
        ),
        Tool(
            name="check_pr_lint",
            description="Run only the lint gate on a PR",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "GitHub repo in owner/repo format",
                    },
                    "pr_number": {
                        "type": "integer",
                        "description": "PR number to check",
                    },
                },
                "required": ["repo", "pr_number"],
            },
        ),
        Tool(
            name="get_review_history",
            description="Get past reviews for a repo or specific file",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "GitHub repo in owner/repo format",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Optional file path to filter by",
                    },
                },
                "required": ["repo"],
            },
        ),
        Tool(
            name="get_cost_summary",
            description="Get cost metrics for reviews",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Optional repo filter (owner/repo)",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back (default 30)",
                    },
                },
                "required": [],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    if name == "review_pr":
        return await _review_pr(arguments)
    elif name == "check_pr_size":
        return await _check_pr_size(arguments)
    elif name == "check_pr_lint":
        return await _check_pr_lint(arguments)
    elif name == "get_review_history":
        return await _get_review_history(arguments)
    elif name == "get_cost_summary":
        return await _get_cost_summary(arguments)
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def _review_pr(args: dict) -> list[TextContent]:
    """Run full review pipeline."""
    from pr_review_agent.config import load_config
    from pr_review_agent.gates.lint_gate import run_lint
    from pr_review_agent.gates.size_gate import check_size
    from pr_review_agent.github_client import GitHubClient
    from pr_review_agent.review.confidence import calculate_confidence
    from pr_review_agent.review.llm_reviewer import LLMReviewer

    repo = args["repo"]
    pr_number = args["pr_number"]
    owner, repo_name = repo.split("/")

    config = load_config(Path(".ai-review.yaml"))
    github = GitHubClient(get_github_token())
    pr = github.fetch_pr(owner, repo_name, pr_number)

    # Size gate
    size_result = check_size(pr, config)
    if not size_result.passed:
        return [TextContent(
            type="text",
            text=f"Size gate failed: {size_result.reason}",
        )]

    # Lint gate
    lint_result = run_lint(pr.files_changed, config)
    if not lint_result.passed:
        return [TextContent(
            type="text",
            text=f"Lint gate failed: {lint_result.error_count} errors",
        )]

    # LLM review
    reviewer = LLMReviewer(get_anthropic_key())
    review = reviewer.review(
        diff=pr.diff,
        pr_description=pr.description,
        model=config.llm.default_model,
        config=config,
    )

    confidence = calculate_confidence(review, pr, config)

    lines = [
        f"## Review: {repo}#{pr_number}",
        f"**Confidence:** {confidence.score:.0%} ({confidence.level})",
        f"**Summary:** {review.summary}",
        "",
    ]

    if review.issues:
        lines.append(f"**Issues ({len(review.issues)}):**")
        for issue in review.issues:
            loc = f"{issue.file}:{issue.line}" if issue.line else issue.file
            lines.append(f"- [{issue.severity}] {loc}: {issue.description}")

    lines.append(f"\nModel: {review.model} | Cost: ${review.cost_usd:.4f}")

    return [TextContent(type="text", text="\n".join(lines))]


async def _check_pr_size(args: dict) -> list[TextContent]:
    """Run size gate only."""
    from pr_review_agent.config import load_config
    from pr_review_agent.gates.size_gate import check_size
    from pr_review_agent.github_client import GitHubClient

    repo = args["repo"]
    pr_number = args["pr_number"]
    owner, repo_name = repo.split("/")

    config = load_config(Path(".ai-review.yaml"))
    github = GitHubClient(get_github_token())
    pr = github.fetch_pr(owner, repo_name, pr_number)

    result = check_size(pr, config)
    status = "PASSED" if result.passed else "FAILED"
    text = (
        f"Size gate: {status}\n"
        f"Lines: {pr.lines_added + pr.lines_removed} "
        f"(limit: {config.limits.max_lines_changed})\n"
        f"Files: {len(pr.files_changed)} "
        f"(limit: {config.limits.max_files_changed})"
    )
    if not result.passed:
        text += f"\nReason: {result.reason}"

    return [TextContent(type="text", text=text)]


async def _check_pr_lint(args: dict) -> list[TextContent]:
    """Run lint gate only."""
    from pr_review_agent.config import load_config
    from pr_review_agent.gates.lint_gate import run_lint
    from pr_review_agent.github_client import GitHubClient

    repo = args["repo"]
    pr_number = args["pr_number"]
    owner, repo_name = repo.split("/")

    config = load_config(Path(".ai-review.yaml"))
    github = GitHubClient(get_github_token())
    pr = github.fetch_pr(owner, repo_name, pr_number)

    result = run_lint(pr.files_changed, config)
    status = "PASSED" if result.passed else "FAILED"
    text = f"Lint gate: {status}\nErrors: {result.error_count}"
    if not result.passed:
        text += f"\nThreshold: {config.linting.fail_threshold}"

    return [TextContent(type="text", text=text)]


async def _get_review_history(args: dict) -> list[TextContent]:
    """Get review history from Supabase."""
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        return [TextContent(
            type="text",
            text="SUPABASE_URL and SUPABASE_KEY required for review history",
        )]

    from supabase import create_client

    client = create_client(supabase_url, supabase_key)
    repo = args["repo"]
    owner, repo_name = repo.split("/")

    query = (
        client.table("review_events")
        .select("*")
        .eq("repo_owner", owner)
        .eq("repo_name", repo_name)
        .order("created_at", desc=True)
        .limit(20)
    )

    result = query.execute()
    reviews = result.data if result.data else []

    if not reviews:
        return [TextContent(type="text", text=f"No reviews found for {repo}")]

    lines = [f"## Review History: {repo} ({len(reviews)} recent)"]
    for r in reviews:
        confidence = r.get("confidence_score")
        conf_str = f"{confidence:.0%}" if confidence else "N/A"
        lines.append(
            f"- PR#{r['pr_number']}: {r.get('outcome', 'unknown')} "
            f"(confidence: {conf_str}, cost: ${r.get('cost_usd', 0):.4f})"
        )

    return [TextContent(type="text", text="\n".join(lines))]


async def _get_cost_summary(args: dict) -> list[TextContent]:
    """Get cost summary from Supabase."""
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        return [TextContent(
            type="text",
            text="SUPABASE_URL and SUPABASE_KEY required for cost summary",
        )]

    from datetime import UTC, datetime

    from supabase import create_client

    client = create_client(supabase_url, supabase_key)
    days = args.get("days", 30)

    since = datetime.now(UTC)
    since = since.replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta

    since = since - timedelta(days=days)

    query = (
        client.table("review_events")
        .select("cost_usd,model_used,repo_owner,repo_name")
        .eq("llm_called", True)
        .gte("created_at", since.isoformat())
    )

    repo = args.get("repo")
    if repo:
        owner, repo_name = repo.split("/")
        query = query.eq("repo_owner", owner).eq("repo_name", repo_name)

    result = query.execute()
    reviews = result.data if result.data else []

    total_cost = sum(r.get("cost_usd", 0) or 0 for r in reviews)
    review_count = len(reviews)
    avg_cost = total_cost / review_count if review_count > 0 else 0

    lines = [
        f"## Cost Summary (last {days} days)",
        f"Total spend: ${total_cost:.2f}",
        f"Reviews: {review_count}",
        f"Avg cost/review: ${avg_cost:.4f}",
    ]

    return [TextContent(type="text", text="\n".join(lines))]
