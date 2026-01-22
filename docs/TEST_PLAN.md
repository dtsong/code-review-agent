# Test Plan

## Overview

This document covers both automated tests and manual CLI verification scenarios for the PR Review Agent, including the agentic capabilities (adaptive pre-analysis and intelligent retries).

---

## Running Tests

### Unit Tests

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run with coverage
uv run pytest --cov=src/pr_review_agent

# Run with coverage and missing lines report
uv run pytest --cov=src/pr_review_agent --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_config.py

# Run only unit tests
uv run pytest tests/unit/ -v

# Run only integration tests
uv run pytest tests/integration/ -v

# Run tests matching a pattern
uv run pytest -k "test_retry" -v
```

### Lint Check

```bash
uv run ruff check src/
```

---

## Test Structure

```
tests/
├── __init__.py
├── conftest.py                          # Shared fixtures
├── test_config.py                       # Config loading tests
├── unit/
│   ├── __init__.py
│   ├── test_retry_handler.py            # Intelligent retry tests
│   └── test_pre_analyzer.py             # Pre-analysis tests
└── integration/
    ├── __init__.py
    └── test_adaptive_review_flow.py     # End-to-end adaptive flow tests
```

---

## Unit Test Coverage

### `tests/unit/test_retry_handler.py`

Tests for the intelligent retry handler in `src/pr_review_agent/execution/retry_handler.py`.

| Test Class | Coverage Area |
|------------|---------------|
| `TestBackoff` | Exponential backoff calculation (1s, 2s, 4s..., capped at 30s) |
| `TestAdaptStrategy` | Strategy adaptation based on failure types |
| `TestRetryWithAdaptation` | Main retry loop with validation |

**Key Test Cases:**
- Backoff increases exponentially
- Backoff caps at 30 seconds
- No failures returns base strategy
- `CONTEXT_TOO_LONG` enables diff summarization
- `RATE_LIMIT` falls back to Haiku model
- `LOW_QUALITY_RESPONSE` increases temperature
- Multiple failures compound correctly
- Success on first attempt (no retry)
- Retries on rate limit errors
- Retries on validation failure
- Raises after max attempts exhausted

**Target Coverage:** >90%

---

### `tests/unit/test_pre_analyzer.py`

Tests for the adaptive pre-analyzer in `src/pr_review_agent/analysis/pre_analyzer.py`.

| Test Class | Coverage Area |
|------------|---------------|
| `TestCategorizeFiles` | File categorization by type (test, config, security, docs, api, ui, core) |
| `TestInferPRType` | PR type inference from title and file patterns |
| `TestAssessRisk` | Risk level assessment (low, medium, high, critical) |
| `TestAssessComplexity` | Complexity assessment based on lines/files changed |
| `TestGetFocusAreas` | Focus area determination by PR type and risk |
| `TestAnalyzePR` | Full PR analysis integration |

**Key Test Cases:**
- Categorizes test files correctly
- Categorizes config files (.yaml, .json, .toml, .env)
- Categorizes security-related files (auth, crypto, password)
- Categorizes documentation files
- Infers BUGFIX from title keywords (fix, bug, issue)
- Infers FEATURE from title keywords (feat, add, implement)
- Infers SECURITY from title keywords (security, vuln, cve)
- Infers TEST from file patterns (majority test files)
- Infers DOCS from file patterns (only doc files)
- Critical risk for security files
- High risk for large PRs (>300 lines)
- High risk for many API changes (>3 files)
- Low risk for test/docs-only PRs
- High complexity for >200 lines or >10 files
- Low complexity for <50 lines and <5 files
- Feature PRs focus on logic_correctness, edge_cases, test_coverage
- Security PRs focus on vulnerabilities, auth_logic, input_validation
- High-risk PRs add security_implications to focus

**Target Coverage:** >85%

---

## Integration Test Coverage

### `tests/integration/test_adaptive_review_flow.py`

End-to-end tests for the adaptive review flow.

| Test Class | Coverage Area |
|------------|---------------|
| `TestPreAnalysisIntegration` | Pre-analysis correctly categorizes different PR types |
| `TestRetryIntegration` | Retry handler integrates with LLM calls |
| `TestAdaptiveFlowIntegration` | Model selection based on analysis |
| `TestEndToEndFlow` | Complete flow from fetch to review |

**Key Test Cases:**
- Small feature PR analyzed as low complexity, low/medium risk, uses Haiku
- Security PR gets critical risk, uses Sonnet
- Test-only PR gets low risk, skips security scan
- Successful review with no retry needed
- Retry on rate limit with fallback model
- Large PR fails size gate before LLM call (no token waste)

---

## Coverage Targets

| Module | Target | Rationale |
|--------|--------|-----------|
| `execution/retry_handler.py` | >90% | Critical error handling path |
| `analysis/pre_analyzer.py` | >85% | Core adaptive logic |
| `memory/review_store.py` | >80% | Stretch goal (if implemented) |
| **Overall** | >80% | Project standard |

### Checking Coverage

```bash
# Quick coverage check
uv run pytest --cov=src/pr_review_agent

# Detailed coverage with missing lines
uv run pytest --cov=src/pr_review_agent --cov-report=term-missing

# HTML coverage report
uv run pytest --cov=src/pr_review_agent --cov-report=html
# Then open htmlcov/index.html
```

---

## Manual CLI Test Scenarios

### Scenario 1: Clean PR (Full LLM Review)

**Setup:** Small, well-formed PR under size/lint thresholds

**Command:**
```bash
uv run pr-review-agent --repo danielsong/mtg-commander-roi --pr <PR_NUMBER>
```

**Expected Output:**
```
🔍 Analyzing PR #<N>...
   Type: feature
   Risk: low/medium
   Complexity: low
   Model: claude-haiku-4-5-20251001

📏 Size Gate: PASSED (XX lines changed)
🔧 Lint Gate: PASSED (0 errors)

🤖 Running LLM Review...
   Attempt 1/3 with claude-haiku-4-5-20251001
   ✓ Review complete (confidence: 0.XX)

📊 Token Usage:
   Input: X,XXX tokens
   Output: XXX tokens
   Cost: $0.00XX

📝 Review Summary:
   [Summary of the PR...]

🎯 Issues Found:
   [Any issues or suggestions...]

✅ Recommendation: APPROVE/CHANGES_REQUESTED (confidence level)
```

---

### Scenario 2: Large PR (Size Gate)

**Setup:** PR with > 500 lines changed

**Command:**
```bash
uv run pr-review-agent --repo owner/repo --pr <LARGE_PR_NUMBER>
```

**Expected:**
- Pre-analysis runs and shows high complexity
- Size gate: FAIL
- Lint gate: SKIPPED
- LLM review: SKIPPED (saves tokens)
- Output: Message recommending PR be split

---

### Scenario 3: Lint Failures (Lint Gate)

**Setup:** PR with lint errors exceeding threshold

**Command:**
```bash
uv run pr-review-agent --repo owner/repo --pr <LINT_FAIL_PR_NUMBER>
```

**Expected:**
- Pre-analysis runs
- Size gate: PASS
- Lint gate: FAIL
- LLM review: SKIPPED (saves tokens)
- Output: Lint errors listed, message to fix before AI review

---

### Scenario 4: Security PR (Elevated Scrutiny)

**Setup:** PR touching security-related files (auth, crypto, etc.)

**Command:**
```bash
uv run pr-review-agent --repo owner/repo --pr <SECURITY_PR_NUMBER>
```

**Expected Output:**
```
🔍 Analyzing PR #<N>...
   Type: security
   Risk: critical
   Complexity: medium/high
   Model: claude-sonnet-4-20250514  (upgraded due to risk)

[Review with security focus areas: vulnerabilities, auth_logic, input_validation]
```

---

### Scenario 5: GitHub Comment Posting

**Command:**
```bash
uv run pr-review-agent --repo danielsong/mtg-commander-roi --pr <PR_NUMBER> --post-comment
```

**Expected:**
- All gates pass
- Pre-analysis included in output
- LLM review executes
- Comment posted to GitHub PR
- Comment URL returned in output

---

### Scenario 6: Metrics Logging

**Prerequisites:**
- SUPABASE_URL and SUPABASE_KEY environment variables set

**Command:**
```bash
uv run pr-review-agent --repo danielsong/mtg-commander-roi --pr <PR_NUMBER>
```

**Expected:**
- Review event logged to Supabase `review_events` table
- Verify in Supabase dashboard or via SQL query:
```sql
SELECT * FROM review_events ORDER BY created_at DESC LIMIT 5;
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_TOKEN` | Yes | GitHub PAT for API access |
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `SUPABASE_URL` | No | Supabase project URL |
| `SUPABASE_KEY` | No | Supabase anon key |

---

## Verification Checklist

### Before Committing Changes

- [ ] All unit tests pass: `uv run pytest tests/unit/ -v`
- [ ] All integration tests pass: `uv run pytest tests/integration/ -v`
- [ ] Overall coverage >80%: `uv run pytest --cov=src/pr_review_agent`
- [ ] No lint errors: `uv run ruff check src/`
- [ ] Manual CLI test shows pre-analysis output

### Quick Verification Commands

```bash
# Full test suite
uv run pytest -v

# Coverage check
uv run pytest --cov=src/pr_review_agent --cov-report=term-missing

# CLI works
uv run pr-review-agent --help

# Manual test with real PR
uv run pr-review-agent --repo danielsong/mtg-commander-roi --pr 2
```

---

*Last updated: January 2026*
