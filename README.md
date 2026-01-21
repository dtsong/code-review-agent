# PR Review Agent

> AI-powered code review with deterministic gates

## Why This Exists

LLMs are expensive. Don't waste tokens on code that fails linting or is too large to review meaningfully.

This agent implements a **gate-first architecture**:
1. **Deterministic checks first** - Size limits and linting catch obvious issues for free
2. **AI reasoning second** - Only well-formed PRs reach the LLM
3. **Model selection** - Small PRs use Haiku (cheap/fast), large PRs use Sonnet (thorough)

The result: lower costs, faster feedback, and better signal-to-noise in reviews.

## Architecture

```
┌──────────┐    ┌────────────┐    ┌────────────┐    ┌──────────────┐
│    PR    │───▶│ Size Gate  │───▶│ Lint Gate  │───▶│ Model Select │
└──────────┘    └────────────┘    └────────────┘    └──────────────┘
                     │                  │                   │
                     ▼                  ▼                   ▼
                  REJECT            REJECT            ┌────────────┐
              (>500 lines)      (lint errors)        │ LLM Review │
                                                     └────────────┘
                                                           │
                    ┌──────────────────────────────────────┴───┐
                    ▼                                          ▼
             ┌─────────────┐                          ┌───────────────┐
             │ Post Comment│                          │ Log to        │
             │ to GitHub   │                          │ Supabase      │
             └─────────────┘                          └───────────────┘
```

## Quick Start

### 1. Install

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/code-review-agent.git
cd code-review-agent

# Install with uv
uv sync
```

### 2. Set Environment Variables

```bash
export GITHUB_TOKEN="ghp_..."
export ANTHROPIC_API_KEY="sk-ant-..."

# Optional: for metrics logging
export SUPABASE_URL="https://xxx.supabase.co"
export SUPABASE_KEY="eyJ..."
```

### 3. Run

```bash
uv run pr-review-agent --repo owner/repo --pr 123

# To post a comment to the PR:
uv run pr-review-agent --repo owner/repo --pr 123 --post-comment
```

## Configuration

Create `.ai-review.yaml` in your repo root:

```yaml
version: 1

# Size limits - PRs exceeding these are rejected
limits:
  max_lines_changed: 500
  max_files_changed: 20

# Files to exclude from linting and review
ignore:
  - "*.lock"
  - "*.json"
  - "*.md"
  - "package-lock.json"

# Linting configuration
linting:
  enabled: true
  tool: ruff
  fail_on_error: true
  fail_threshold: 10  # Max errors before rejection

# LLM configuration
llm:
  provider: anthropic
  default_model: claude-sonnet-4-20250514  # For larger PRs
  simple_model: claude-haiku-4-20250514    # For small PRs (<50 lines)
  simple_threshold_lines: 50
  max_tokens: 4096

# Confidence thresholds for auto-approve/escalate
confidence:
  high: 0.8   # Above this = can auto-approve
  low: 0.5    # Below this = escalate to human

# What the LLM should focus on
review_focus:
  - logic_errors
  - security_issues
  - missing_tests
  - code_patterns
  - naming_conventions
```

### Configuration Reference

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| `limits` | `max_lines_changed` | 500 | Max lines (added + removed) |
| `limits` | `max_files_changed` | 20 | Max files in PR |
| `linting` | `enabled` | true | Run linting gate |
| `linting` | `tool` | ruff | Linter to use |
| `linting` | `fail_threshold` | 10 | Max lint errors |
| `llm` | `simple_threshold_lines` | 50 | Lines below this use Haiku |
| `confidence` | `high` | 0.8 | Auto-approve threshold |
| `confidence` | `low` | 0.5 | Escalation threshold |

## How It Works

### 1. Size Gate
Rejects PRs that exceed configurable limits:
- Default: 500 lines changed, 20 files
- Large PRs are hard to review well - this encourages smaller, focused changes
- Rejected PRs get a comment suggesting they split the PR

### 2. Lint Gate
Runs Ruff on changed Python files:
- Catches syntax errors, unused imports, formatting issues
- Configurable error threshold (default: 10 errors = rejection)
- Why lint before LLM? Saves tokens on obviously broken code

### 3. Model Selection
Picks the right model for the job:
- **Haiku** for small PRs (<50 lines): Fast, cheap, good enough
- **Sonnet** for larger PRs: More thorough analysis

### 4. LLM Review
Claude analyzes the diff looking for:
- Logic errors and bugs
- Security vulnerabilities
- Missing test coverage
- Code pattern issues
- Naming convention violations

### 5. Confidence Scoring
Each review gets a confidence score (0.0-1.0):
- **High (>0.8)**: AI is confident in its assessment
- **Medium (0.5-0.8)**: Some uncertainty, human review recommended
- **Low (<0.5)**: Complex code, definitely needs human review

### 6. Output
- **Console**: Formatted results for local runs
- **GitHub Comment**: Markdown comment on the PR
- **Supabase**: Metrics logged for the dashboard

## Dashboard

The dashboard shows:
- Total reviews and cost over time
- Gate effectiveness (how many tokens saved)
- Average confidence scores
- Recent review history

### Deploy to Vercel

1. Go to [vercel.com](https://vercel.com) and import from GitHub
2. Set root directory to `dashboard`
3. Add environment variables:
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
4. Deploy

## GitHub Action

Copy `.github/workflows/pr-review.yml` to your repo:

```yaml
name: AI PR Review

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: read
  pull-requests: write

jobs:
  ai-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - uses: astral-sh/setup-uv@v4

      - run: uv sync

      - name: Run PR Review Agent
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
        run: |
          uv run pr-review-agent \
            --repo ${{ github.repository }} \
            --pr ${{ github.event.pull_request.number }} \
            --post-comment
```

### Required Secrets

In your repo settings (Settings > Secrets and variables > Actions):

| Secret | Description |
|--------|-------------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `SUPABASE_URL` | Supabase project URL (optional) |
| `SUPABASE_KEY` | Supabase anon key (optional) |

Note: `GITHUB_TOKEN` is automatically provided by GitHub Actions.

## Development

### Setup

```bash
# Install dev dependencies
uv sync

# Run tests
uv run pytest

# Run linting
uv run ruff check .

# Run type checking
uv run ruff check . --select=E,F,I,UP,B,SIM
```

### Project Structure

```
.
├── src/pr_review_agent/
│   ├── main.py              # CLI entrypoint
│   ├── config.py            # Configuration loading
│   ├── github_client.py     # GitHub API client
│   ├── gates/
│   │   ├── size_gate.py     # Size limit checking
│   │   └── lint_gate.py     # Ruff linting
│   ├── review/
│   │   ├── llm_reviewer.py  # Claude API integration
│   │   ├── model_selector.py # Haiku vs Sonnet
│   │   └── confidence.py    # Confidence scoring
│   ├── output/
│   │   ├── console.py       # Terminal output
│   │   └── github_comment.py # PR comment formatting
│   └── metrics/
│       └── supabase_logger.py # Metrics logging
├── tests/                   # Test suite
├── dashboard/               # Next.js metrics dashboard
├── database/
│   └── schema.sql           # Supabase schema
└── .github/workflows/
    └── pr-review.yml        # GitHub Action
```

### Running Tests

```bash
# All tests
uv run pytest

# With coverage
uv run pytest --cov=pr_review_agent

# Specific test file
uv run pytest tests/test_size_gate.py -v
```

## License

MIT
