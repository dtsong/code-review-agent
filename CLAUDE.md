# PR Review Agent

AI-powered PR review agent that integrates with GitHub, runs deterministic checks before calling an LLM, and tracks metrics in a Supabase-backed dashboard. Built to demonstrate: **use LLMs for reasoning, deterministic tools for everything else**.

## Core Principle

Deterministic gates (size check, lint check) run **before** the LLM to save tokens and catch obvious issues cheaply.

```
PR → Size Gate → Lint Gate → LLM Review → Post Comment → Log Metrics
         ↓           ↓
      [STOP]      [STOP]     (early exit saves tokens)
```

## Tech Stack

- **Language:** Python 3.12+ with `uv`
- **LLM:** Anthropic Claude API (direct, no LangChain)
- **Linting:** Ruff
- **GitHub:** PyGithub + GitHub Actions
- **Database:** Supabase (Postgres)
- **Dashboard:** Next.js on Vercel

## Commands

```bash
# Install dependencies
uv sync

# Run review on a GitHub PR
uv run pr-review-agent --repo owner/repo --pr 123

# Run with comment posting
uv run pr-review-agent --repo owner/repo --pr 123 --post-comment

# Run on local diff file
uv run pr-review-agent --diff ./changes.patch

# Run tests
uv run pytest

# Lint
uv run ruff check src/

# Dashboard dev
cd dashboard && pnpm install && pnpm dev
```

## Project Structure

```
src/pr_review_agent/
├── main.py              # CLI entrypoint
├── config.py            # Load .ai-review.yaml
├── github_client.py     # Fetch PR, post comments
├── gates/               # Size and lint gates
├── review/              # LLM reviewer, model selector, confidence
├── output/              # GitHub comment formatting, console output
└── metrics/             # Supabase logging

dashboard/               # Next.js metrics dashboard
tests/                   # Test scenarios
.ai-review.yaml          # Per-repo config (see file for options)
.github/workflows/       # GitHub Action definition
```

## Configuration

See `.ai-review.yaml` for all options. Key settings:

- `limits.max_lines_changed` - Skip LLM if PR too large (default: 500)
- `linting.fail_on_error` - Skip LLM if linting fails
- `llm.simple_threshold_lines` - Use cheaper model for small PRs

## Environment Variables

```bash
GITHUB_TOKEN=ghp_xxx           # GitHub Personal Access Token
ANTHROPIC_API_KEY=sk-ant-xxx   # Anthropic API Key
SUPABASE_URL=https://xxx       # For metrics (optional)
SUPABASE_KEY=eyJxxx            # For metrics (optional)
```

## Commits

Format: `<type>: <description>`

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`

## Don'ts

- Don't skip gates — they exist to save tokens
- Don't add dependencies without asking
- Don't modify `.ai-review.yaml` defaults without discussion

## More Info

- `docs/LOCAL_DEVELOPMENT.md` - Local development and CLI usage
- `docs/TEST_PLAN.md` - Testing guide with scenarios
- `docs/AGENTIC_CAPABILITIES_SPEC.md` - Detailed feature spec
- `docs/DEMO_QUICK_REF.md` - Full MVP spec reference
- `docs/DEPLOYMENT.md` - Deployment instructions
