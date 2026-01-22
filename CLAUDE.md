# PR Review Agent — MVP Spec

## Overview

An AI-powered PR review agent that integrates with GitHub, runs deterministic checks before calling an LLM, and tracks metrics in a dashboard hosted in Vercel backed by Supabase. Built to demonstrate the principle: **use LLMs for reasoning, deterministic tools for everything else**.

## Project Name

`code-review-agent` (or `agentic-code-review`)

---

## Goals

1. **Functional GitHub Integration** — Works as a GitHub Action or webhook-triggered review
2. **Deterministic-First Architecture** — Linting/tests gate before LLM costs are incurred
3. **Cost-Conscious Design** — Token tracking, model tiering, early exit on failures
4. **Metrics Dashboard** — Supabase + Vercel to visualize review data over time
5. **Demo-Ready** — Can run on a real repo and demonstrate capabilities

---

## Tech Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Language | Python 3.12+ | Fast development, strong ecosystem |
| Package Manager | `uv` | Modern, fast, reliable |
| LLM | Anthropic Claude API (direct) | Thin abstraction, no LangChain |
| Linting | Ruff | Fast, modern Python linter |
| Git Integration | PyGithub + git CLI | Fetch PR data, post comments |
| GitHub Integration | GitHub Actions | Easiest path to real integration |
| Database | Supabase (Postgres) | Free tier, real-time, easy setup |
| Dashboard | Vercel + Next.js (or simple React) | Fast deploy, free tier |
| Config | YAML (`.ai-review.yaml`) | Per-repo configuration |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         GitHub                                   │
│                                                                  │
│   PR Created/Updated ──▶ GitHub Action Triggered                │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      PR Review Agent                             │
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │ 1. Fetch PR │───▶│ 2. Validate │───▶│ 3. Lint     │         │
│  │    Data     │    │    Size     │    │   (Ruff)    │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│                            │                  │                  │
│                       > limit?            failures?              │
│                            │                  │                  │
│                            ▼                  ▼                  │
│                      [STOP: Too      [STOP: Fix linting          │
│                       large PR]       before AI review]          │
│                                                                  │
│                                              │ pass              │
│                                              ▼                   │
│                                    ┌─────────────────┐           │
│                                    │ 4. Select Model │           │
│                                    │ (Haiku/Sonnet)  │           │
│                                    └────────┬────────┘           │
│                                             │                    │
│                                             ▼                    │
│                                    ┌─────────────────┐           │
│                                    │ 5. LLM Review   │           │
│                                    │ - Logic issues  │           │
│                                    │ - Patterns      │           │
│                                    │ - Missing tests │           │
│                                    │ - Suggestions   │           │
│                                    └────────┬────────┘           │
│                                             │                    │
│                                             ▼                    │
│                                    ┌─────────────────┐           │
│                                    │ 6. Confidence   │           │
│                                    │    Scoring      │           │
│                                    └────────┬────────┘           │
│                                             │                    │
│                                             ▼                    │
│                                    ┌─────────────────┐           │
│                                    │ 7. Post Comment │           │
│                                    │    to GitHub    │           │
│                                    └────────┬────────┘           │
│                                             │                    │
│                                             ▼                    │
│                                    ┌─────────────────┐           │
│                                    │ 8. Log Metrics  │           │
│                                    │   to Supabase   │           │
│                                    └─────────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Supabase + Vercel Dashboard                   │
│                                                                  │
│   • Reviews over time                                            │
│   • Token costs per repo/author                                  │
│   • Confidence score distribution                                │
│   • Escalation rate                                              │
│   • Suggestions accepted vs rejected                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
pr-review-agent/
├── .github/
│   └── workflows/
│       └── pr-review.yml          # GitHub Action definition
├── src/
│   └── pr_review_agent/
│       ├── __init__.py
│       ├── main.py                # CLI entrypoint
│       ├── config.py              # Load .ai-review.yaml
│       ├── github_client.py       # Fetch PR, post comments
│       ├── gates/
│       │   ├── __init__.py
│       │   ├── size_gate.py       # Diff size validation
│       │   └── lint_gate.py       # Ruff linting
│       ├── review/
│       │   ├── __init__.py
│       │   ├── llm_reviewer.py    # Claude API integration
│       │   ├── model_selector.py  # Haiku vs Sonnet logic
│       │   └── confidence.py      # Confidence scoring
│       ├── output/
│       │   ├── __init__.py
│       │   ├── github_comment.py  # Format and post comment
│       │   └── console.py         # CLI output
│       └── metrics/
│           ├── __init__.py
│           └── supabase_logger.py # Log to Supabase
├── dashboard/                      # Vercel dashboard (Next.js or React)
│   ├── package.json
│   ├── src/
│   │   └── ...
│   └── ...
├── tests/
│   └── ...
├── .ai-review.yaml                 # Example config
├── pyproject.toml
├── README.md
└── SPEC.md                         # This file
```

---

## Configuration File (`.ai-review.yaml`)

```yaml
# .ai-review.yaml — Place in repo root

version: 1

# Diff size limits
limits:
  max_lines_changed: 500
  max_files_changed: 20

# Files to skip
ignore:
  - "*.lock"
  - "*.json"
  - "*.md"
  - "package-lock.json"
  - "pnpm-lock.yaml"
  - "uv.lock"

# Linting configuration
linting:
  enabled: true
  tool: ruff
  fail_on_error: true          # If true, skip LLM if linting fails
  fail_threshold: 10           # Skip LLM if more than N lint errors

# LLM configuration
llm:
  provider: anthropic
  default_model: claude-sonnet-4-20250514
  simple_model: claude-haiku-4-5-20251001    # For small/simple PRs
  simple_threshold_lines: 50   # PRs under this use simple_model
  max_tokens: 4096

# Confidence thresholds
confidence:
  high: 0.8                    # Auto-approve threshold
  low: 0.5                     # Escalation threshold

# Review focus areas
review_focus:
  - logic_errors
  - security_issues
  - missing_tests
  - code_patterns
  - naming_conventions
  - documentation

# Metrics
metrics:
  enabled: true
  provider: supabase
  # Supabase URL and key should be in environment variables:
  # SUPABASE_URL, SUPABASE_KEY
```

---

## Supabase Schema

```sql
-- Table: review_events
CREATE TABLE review_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

  -- PR identification
  repo_owner TEXT NOT NULL,
  repo_name TEXT NOT NULL,
  pr_number INTEGER NOT NULL,
  pr_title TEXT,
  pr_author TEXT,
  pr_url TEXT,

  -- Diff stats
  lines_added INTEGER,
  lines_removed INTEGER,
  files_changed INTEGER,

  -- Gate results
  size_gate_passed BOOLEAN,
  lint_gate_passed BOOLEAN,
  lint_errors_count INTEGER,

  -- LLM review (nullable if gated)
  llm_called BOOLEAN DEFAULT FALSE,
  model_used TEXT,
  input_tokens INTEGER,
  output_tokens INTEGER,
  cost_usd DECIMAL(10, 6),

  -- Review results
  confidence_score DECIMAL(3, 2),
  issues_found JSONB,            -- Array of issues
  suggestions JSONB,             -- Array of suggestions

  -- Outcome
  outcome TEXT,                  -- 'approved', 'changes_requested', 'escalated'
  escalated_to_human BOOLEAN DEFAULT FALSE,

  -- Timing
  review_duration_ms INTEGER
);

-- Index for common queries
CREATE INDEX idx_review_events_repo ON review_events(repo_owner, repo_name);
CREATE INDEX idx_review_events_created ON review_events(created_at);
CREATE INDEX idx_review_events_author ON review_events(pr_author);

-- View: Daily summary
CREATE VIEW daily_review_summary AS
SELECT
  DATE(created_at) as review_date,
  COUNT(*) as total_reviews,
  SUM(CASE WHEN llm_called THEN 1 ELSE 0 END) as llm_reviews,
  SUM(CASE WHEN NOT size_gate_passed OR NOT lint_gate_passed THEN 1 ELSE 0 END) as gated_reviews,
  SUM(cost_usd) as total_cost,
  AVG(confidence_score) as avg_confidence,
  SUM(CASE WHEN escalated_to_human THEN 1 ELSE 0 END) as escalations
FROM review_events
GROUP BY DATE(created_at)
ORDER BY review_date DESC;
```

---

## GitHub Action Definition

```yaml
# .github/workflows/pr-review.yml

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
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Full history for diff

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Install dependencies
        run: uv sync

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

---

## Core Module Specs

### `output/github_comment.py` — GitHub Comment Posting

```python
"""
Format review results as GitHub-flavored markdown and post as PR comment.
"""

from pr_review_agent.github_client import GitHubClient, PRData
from pr_review_agent.review.llm_reviewer import LLMReviewResult
from pr_review_agent.review.confidence import ConfidenceResult

def format_as_markdown(
    review: LLMReviewResult,
    confidence: ConfidenceResult,
    lint_errors: int,
    model: str,
    cost: float,
) -> str:
    """Format review results as GitHub-flavored markdown."""
    pass

def post_review_comment(
    client: GitHubClient,
    pr: PRData,
    review: LLMReviewResult,
    confidence: ConfidenceResult,
) -> str:
    """Post review as PR comment. Returns comment URL."""
    pass
```

### `metrics/supabase_logger.py` — Metrics Logging

```python
"""
Log review metrics to Supabase for dashboard visualization.
"""

from dataclasses import dataclass
from supabase import create_client, Client

class SupabaseLogger:
    def __init__(self, url: str, key: str):
        self.client: Client = create_client(url, key)

    def log_review(
        self,
        pr: PRData,
        size_result: SizeGateResult,
        lint_result: LintGateResult,
        review_result: LLMReviewResult | None,
        confidence: ConfidenceResult | None,
        outcome: str,
        duration_ms: int
    ):
        """Log complete review event to Supabase."""
        pass
```

---

## Dashboard (Vercel + Next.js)

### Key Visualizations

1. **Review Volume Over Time** — Line chart of reviews per day
2. **Cost Tracker** — Running total of API costs
3. **Gate Effectiveness** — Pie chart: gated vs. LLM reviews (shows token savings)
4. **Confidence Distribution** — Histogram of confidence scores
5. **Escalation Rate** — Percentage requiring human review
6. **Top Issues by Category** — Bar chart of issue types
7. **Cost per Repo/Author** — For chargeback visibility

### Tech Stack for Dashboard

```
dashboard/
├── package.json
├── next.config.js
├── src/
│   ├── app/
│   │   ├── page.tsx              # Main dashboard
│   │   └── api/
│   │       └── metrics/
│   │           └── route.ts      # API route to fetch from Supabase
│   ├── components/
│   │   ├── ReviewChart.tsx
│   │   ├── CostTracker.tsx
│   │   ├── ConfidenceDistribution.tsx
│   │   └── ...
│   └── lib/
│       └── supabase.ts           # Supabase client
└── ...
```

### Supabase Connection

```typescript
// src/lib/supabase.ts
import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

export const supabase = createClient(supabaseUrl, supabaseKey)
```

---

## Build Phases

### Phase 1: Core Agent (COMPLETED)

**Goal:** Working CLI that can review a PR and output results to console.

- [x] Project scaffold with `uv`
- [x] Config loading (`.ai-review.yaml`)
- [x] GitHub client (fetch PR data)
- [x] Size gate
- [x] Lint gate (Ruff)
- [x] LLM reviewer (Claude API)
- [x] Console output
- [x] Basic confidence scoring

**Test:** `uv run pr-review-agent --repo owner/repo --pr 123`

### Phase 2: GitHub Integration (COMPLETED)

**Goal:** Posts comments to GitHub PRs.

- [x] Format review as GitHub-flavored markdown
- [x] Post comment via GitHub API
- [x] GitHub Action workflow file

**Test:** Create test PR, run action, see comment appear.

### Phase 3: Metrics & Dashboard (COMPLETED)

**Goal:** Supabase logging + basic Vercel dashboard.

- [x] Supabase project setup
- [x] Create `review_events` table
- [x] Supabase logger implementation
- [x] Basic Next.js dashboard
- [x] Deploy to Vercel

**Test:** Run review, see data in Supabase, view in dashboard.

### Phase 4: Polish (COMPLETED)

**Goal:** Demo-ready.

- [x] README with architecture diagram
- [x] Error handling and edge cases
- [x] Example `.ai-review.yaml` configs
- [x] Demo preparation

---

## Environment Variables

```bash
# Required
GITHUB_TOKEN=ghp_xxxxxxxxxxxx          # GitHub Personal Access Token
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx  # Anthropic API Key

# For metrics (optional for MVP, but build it in)
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=eyJxxxxxxxxxxxx

# Optional
LOG_LEVEL=INFO
```

---

## Testing the MVP

### Test Scenario 1: Clean PR (Should Pass)

```bash
# Small, well-written PR
uv run pr-review-agent --repo your-username/test-repo --pr 1
# Expected: Lint passes, LLM reviews, high confidence, suggestions posted
```

### Test Scenario 2: Large PR (Should Gate)

```bash
# PR with 1000+ lines changed
uv run pr-review-agent --repo your-username/test-repo --pr 2
# Expected: Size gate fails, no LLM call, message about splitting PR
```

### Test Scenario 3: Lint Failures (Should Gate)

```bash
# PR with syntax errors or major lint issues
uv run pr-review-agent --repo your-username/test-repo --pr 3
# Expected: Lint gate fails, no LLM call, message to fix linting first
```

---

## Success Criteria for Demo

1. **Live Demo:** Show the agent reviewing a real PR
2. **Architecture Explanation:** Walk through the deterministic vs. LLM split
3. **Cost Consciousness:** Show the gating logic that saves tokens
4. **Metrics:** Show the dashboard with real data
5. **Extensibility:** Explain how this could grow (Slack, monorepo, etc.)

---

## Commands Reference

```bash
# Setup
uv init pr-review-agent
cd pr-review-agent
uv add anthropic pygithub ruff supabase pyyaml

# Run locally
uv run pr-review-agent --repo owner/repo --pr 123

# Run with comment posting
uv run pr-review-agent --repo owner/repo --pr 123 --post-comment

# Run on local diff
uv run pr-review-agent --diff ./changes.patch

# Dashboard dev
cd dashboard
pnpm install
pnpm dev
```

---

*Spec created: January 2026*
*Author: Daniel Song*
*Purpose: Personal Portfolio Project*
