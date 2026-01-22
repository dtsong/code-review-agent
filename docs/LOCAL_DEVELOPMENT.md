# Local Development Guide

Run the PR review agent locally to review PRs on any GitHub repository.

## Quick Start

```bash
# Install dependencies
uv sync

# Set credentials
export GITHUB_TOKEN="ghp_xxx"
export ANTHROPIC_API_KEY="sk-ant-xxx"

# Review a PR
uv run pr-review-agent --repo owner/repo --pr 123
```

## Prerequisites

- **Python 3.12+** - Required for the agent
- **uv** - Python package manager ([install](https://docs.astral.sh/uv/getting-started/installation/))
- **GitHub Personal Access Token** - To access PR data
- **Anthropic API Key** - For Claude-powered reviews

## GitHub Token Setup

Create a fine-grained token at [github.com/settings/tokens](https://github.com/settings/tokens?type=beta):

1. Click **"Generate new token"** → **"Fine-grained token"**
2. Set a token name and expiration
3. Under **Repository access**, select the repos you want to review (or "All repositories" for any public repo)
4. Under **Permissions**, set:

| Permission | Access Level | Purpose |
|------------|--------------|---------|
| Contents | Read | Fetch PR diffs |
| Pull requests | Read | Fetch PR metadata |
| Pull requests | Write | Only needed with `--post-comment` |

5. Click **"Generate token"** and copy it immediately

**Classic token alternative:** Use `public_repo` scope for public repos, or `repo` for private repos.

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `GITHUB_TOKEN` | Yes | GitHub Personal Access Token |
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `SUPABASE_URL` | No | Metrics dashboard URL |
| `SUPABASE_KEY` | No | Metrics dashboard key |

Set them in your shell or create a `.env` file (see `.env.example`).

## CLI Usage

```bash
uv run pr-review-agent --repo OWNER/REPO --pr NUMBER [--config PATH] [--post-comment]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `--repo` | Yes | Repository in `owner/repo` format |
| `--pr` | Yes | Pull request number |
| `--config` | No | Path to `.ai-review.yaml` config file |
| `--post-comment` | No | Post review as a comment on the PR |

## Example: Reviewing an External Repo

Review any public PR without `--post-comment` (read-only):

```bash
# Set credentials
export GITHUB_TOKEN="ghp_your_token_here"
export ANTHROPIC_API_KEY="sk-ant-your_key_here"

# Review a PR on someone else's repo
uv run pr-review-agent --repo facebook/react --pr 28000

# Review a PR on your own repo
uv run pr-review-agent --repo yourusername/yourrepo --pr 5
```

The review output appears in your terminal. Use `--post-comment` only on repos where you have write access.

## Development Commands

```bash
# Run tests
uv run pytest

# Lint code
uv run ruff check src/

# Format code
uv run ruff format src/
```

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `401 Unauthorized` | Invalid or expired token | Regenerate your GitHub token |
| `403 Forbidden` | Token lacks access to the repo | Add repo to token's repository access |
| `404 Not Found` | Wrong repo/PR number or private repo without access | Check the repo name and PR number |
| `Rate limit exceeded` | Too many GitHub API requests | Wait for rate limit reset or use authenticated requests |
| `ANTHROPIC_API_KEY not set` | Missing API key | Export `ANTHROPIC_API_KEY` |

## Related Docs

- [TEST_PLAN.md](./TEST_PLAN.md) - Testing guide with scenarios
- [DEPLOYMENT.md](./DEPLOYMENT.md) - Production deployment
- [DEMO_QUICK_REF.md](./DEMO_QUICK_REF.md) - Full MVP spec reference
