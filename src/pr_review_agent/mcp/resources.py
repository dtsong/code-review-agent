"""MCP resources exposing config, reviews, and metrics."""

import os
from pathlib import Path

from mcp.types import Resource

from pr_review_agent.mcp.server import server


@server.list_resources()
async def list_resources() -> list[Resource]:
    """Return available MCP resources."""
    return [
        Resource(
            uri="config://ai-review.yaml",
            name="Review Configuration",
            description="Current .ai-review.yaml configuration",
            mimeType="text/yaml",
        ),
        Resource(
            uri="review://latest",
            name="Latest Review",
            description=(
                "Cached result of the most recent review "
                "(use review://{owner}/{repo}/{pr_number} for specific)"
            ),
            mimeType="application/json",
        ),
        Resource(
            uri="metrics://summary",
            name="Metrics Summary",
            description=(
                "Review metrics summary "
                "(use metrics://{owner}/{repo}/summary for specific repo)"
            ),
            mimeType="application/json",
        ),
    ]


@server.read_resource()
async def read_resource(uri: str) -> str:
    """Read a resource by URI."""
    if uri.startswith("config://"):
        return await _read_config(uri)
    elif uri.startswith("review://"):
        return await _read_review(uri)
    elif uri.startswith("metrics://"):
        return await _read_metrics(uri)
    else:
        return f"Unknown resource: {uri}"


async def _read_config(uri: str) -> str:
    """Read .ai-review.yaml configuration."""
    config_path = Path(".ai-review.yaml")
    if not config_path.exists():
        return "No .ai-review.yaml found in current directory"
    return config_path.read_text()


async def _read_review(uri: str) -> str:
    """Read a cached review result from Supabase."""
    import json

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        return json.dumps({"error": "SUPABASE_URL and SUPABASE_KEY required"})

    from supabase import create_client

    client = create_client(supabase_url, supabase_key)

    # Parse URI: review://latest or review://{owner}/{repo}/{pr_number}
    path = uri.removeprefix("review://")

    if path == "latest":
        result = (
            client.table("review_events")
            .select("*")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
    else:
        parts = path.split("/")
        if len(parts) == 3:
            owner, repo, pr_number = parts
            result = (
                client.table("review_events")
                .select("*")
                .eq("repo_owner", owner)
                .eq("repo_name", repo)
                .eq("pr_number", int(pr_number))
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
        else:
            return json.dumps({"error": f"Invalid review URI: {uri}"})

    data = result.data[0] if result.data else None
    if not data:
        return json.dumps({"error": "No review found"})

    return json.dumps(data, default=str)


async def _read_metrics(uri: str) -> str:
    """Read metrics summary from Supabase."""
    import json

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        return json.dumps({"error": "SUPABASE_URL and SUPABASE_KEY required"})

    from supabase import create_client

    client = create_client(supabase_url, supabase_key)

    # Parse URI: metrics://summary or metrics://{owner}/{repo}/summary
    path = uri.removeprefix("metrics://")

    query = (
        client.table("review_events")
        .select("cost_usd,confidence_score,outcome,llm_called")
    )

    if path != "summary":
        parts = path.split("/")
        if len(parts) == 3 and parts[2] == "summary":
            owner, repo = parts[0], parts[1]
            query = query.eq("repo_owner", owner).eq("repo_name", repo)
        else:
            return json.dumps({"error": f"Invalid metrics URI: {uri}"})

    result = query.execute()
    reviews = result.data if result.data else []

    total = len(reviews)
    llm_calls = sum(1 for r in reviews if r.get("llm_called"))
    total_cost = sum(r.get("cost_usd", 0) or 0 for r in reviews)
    avg_confidence = (
        sum(r.get("confidence_score", 0) or 0 for r in reviews) / total
        if total > 0
        else 0
    )

    summary = {
        "total_reviews": total,
        "llm_calls": llm_calls,
        "total_cost_usd": round(total_cost, 2),
        "avg_confidence": round(avg_confidence, 3),
        "gate_skip_rate": (
            round((total - llm_calls) / total, 3) if total > 0 else 0
        ),
    }

    return json.dumps(summary)
