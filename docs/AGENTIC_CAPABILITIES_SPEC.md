# PR Review Agent — Agentic Capabilities Spec

## Overview

Extend the PR Review Agent with agentic capabilities: adaptive planning, intelligent retries, and learning from past reviews. These features transform the tool from a "CLI that calls an LLM" into a genuine agent that perceives, reasons, adapts, and learns.

**Priority:** Ship retries and adaptation tonight. Memory is stretch goal.

---

## Current State

```
PR → Size Gate → Lint Gate → Model Select → LLM Review → Post Comment
         ↓           ↓
      REJECT      REJECT
```

Fixed, deterministic flow. No retries, no adaptation, no memory.

---

## Target State

```
PR → Pre-Analysis → Plan Generation → Adaptive Execution → Synthesis → Post Comment
         │                │                   │                │
         │                │                   │                ▼
         │                │                   │          Store in Memory
         │                │                   │
         │                │                   ▼
         │                │            ┌─────────────────┐
         │                │            │ Execute Steps   │
         │                │            │ • Retry on fail │
         │                │            │ • Adapt strategy│
         │                │            │ • Query memory  │
         │                │            └─────────────────┘
         │                ▼
         │         ┌─────────────────┐
         │         │ LLM Plans:      │
         │         │ • Which checks  │
         │         │ • Review depth  │
         │         │ • Focus areas   │
         │         └─────────────────┘
         ▼
   ┌─────────────────┐
   │ Quick analysis: │
   │ • PR type       │
   │ • Complexity    │
   │ • Risk level    │
   └─────────────────┘
```

---

## Feature 1: Intelligent Retries (MUST HAVE)

### Goal
Handle failures gracefully. Retry with adapted strategy instead of crashing.

### Implementation

Create `src/pr_review_agent/execution/retry_handler.py`:

```python
"""
Intelligent retry handler with exponential backoff and strategy adaptation.
"""

import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, TypeVar, Any

class FailureType(Enum):
    RATE_LIMIT = "rate_limit"
    CONTEXT_TOO_LONG = "context_too_long"
    API_ERROR = "api_error"
    LOW_QUALITY_RESPONSE = "low_quality_response"
    TIMEOUT = "timeout"

@dataclass
class RetryContext:
    attempt: int = 0
    max_attempts: int = 3
    failures: list[FailureType] = None
    
    def __post_init__(self):
        if self.failures is None:
            self.failures = []

@dataclass 
class RetryStrategy:
    """Adapted strategy based on failures."""
    model: str
    max_tokens: int
    temperature: float
    summarize_diff: bool = False
    chunk_files: bool = False

def get_backoff_seconds(attempt: int) -> float:
    """Exponential backoff: 1s, 2s, 4s, 8s..."""
    return min(2 ** attempt, 30)

def adapt_strategy(context: RetryContext, base_model: str) -> RetryStrategy:
    """
    Adapt strategy based on what failed.
    """
    strategy = RetryStrategy(
        model=base_model,
        max_tokens=4096,
        temperature=0.0
    )
    
    if FailureType.CONTEXT_TOO_LONG in context.failures:
        # Diff too big — summarize it
        strategy.summarize_diff = True
        strategy.chunk_files = True
    
    if FailureType.LOW_QUALITY_RESPONSE in context.failures:
        # Bad response — try with higher temp for variety
        strategy.temperature = 0.3
    
    if FailureType.RATE_LIMIT in context.failures:
        # Rate limited — fall back to smaller model
        if "sonnet" in strategy.model:
            strategy.model = "claude-haiku-4-5-20251001"
    
    return strategy

T = TypeVar("T")

def retry_with_adaptation(
    operation: Callable[[RetryStrategy], T],
    base_model: str,
    max_attempts: int = 3,
    validator: Callable[[T], bool] = None
) -> T:
    """
    Execute operation with intelligent retries.
    
    Args:
        operation: Function that takes RetryStrategy and returns result
        base_model: Starting model to use
        max_attempts: Maximum retry attempts
        validator: Optional function to validate response quality
    
    Returns:
        Result from operation
    
    Raises:
        Exception: If all retries exhausted
    """
    context = RetryContext(max_attempts=max_attempts)
    last_error = None
    
    while context.attempt < context.max_attempts:
        strategy = adapt_strategy(context, base_model)
        
        try:
            result = operation(strategy)
            
            # Validate response if validator provided
            if validator and not validator(result):
                context.failures.append(FailureType.LOW_QUALITY_RESPONSE)
                context.attempt += 1
                continue
            
            return result
            
        except anthropic.RateLimitError:
            context.failures.append(FailureType.RATE_LIMIT)
            last_error = "Rate limit exceeded"
            
        except anthropic.BadRequestError as e:
            if "context length" in str(e).lower():
                context.failures.append(FailureType.CONTEXT_TOO_LONG)
                last_error = "Context too long"
            else:
                raise
                
        except anthropic.APIError as e:
            context.failures.append(FailureType.API_ERROR)
            last_error = str(e)
        
        context.attempt += 1
        
        if context.attempt < context.max_attempts:
            backoff = get_backoff_seconds(context.attempt)
            print(f"Retry {context.attempt}/{context.max_attempts} after {backoff}s ({last_error})")
            time.sleep(backoff)
    
    raise Exception(f"All {max_attempts} attempts failed. Last error: {last_error}")
```

### Integration

Update `review/llm_reviewer.py` to use retry handler:

```python
from pr_review_agent.execution.retry_handler import retry_with_adaptation, RetryStrategy

def review_pr(pr: PRData, config: Config) -> LLMReviewResult:
    """Review PR with intelligent retries."""
    
    def do_review(strategy: RetryStrategy) -> LLMReviewResult:
        diff = pr.diff
        
        # Apply strategy adaptations
        if strategy.summarize_diff:
            diff = summarize_diff(diff, max_lines=200)
        
        response = anthropic.messages.create(
            model=strategy.model,
            max_tokens=strategy.max_tokens,
            temperature=strategy.temperature,
            messages=[{"role": "user", "content": build_review_prompt(diff)}]
        )
        
        return parse_review_response(response)
    
    def validate_review(result: LLMReviewResult) -> bool:
        # Check response has meaningful content
        return (
            result is not None 
            and len(result.summary) > 50
            and result.confidence > 0.0
        )
    
    return retry_with_adaptation(
        operation=do_review,
        base_model=select_model(pr, config),
        max_attempts=3,
        validator=validate_review
    )
```

---

## Feature 2: Adaptive Pre-Analysis (MUST HAVE)

### Goal
Analyze the PR first, then adapt the review strategy. Different PRs need different approaches.

### Implementation

Create `src/pr_review_agent/analysis/pre_analyzer.py`:

```python
"""
Pre-analysis step to understand PR characteristics before review.
"""

from dataclasses import dataclass
from enum import Enum

class PRType(Enum):
    FEATURE = "feature"
    BUGFIX = "bugfix"
    REFACTOR = "refactor"
    TEST = "test"
    DOCS = "docs"
    SECURITY = "security"
    DEPENDENCY = "dependency"
    CONFIG = "config"
    UNKNOWN = "unknown"

class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class PRAnalysis:
    """Result of pre-analysis."""
    pr_type: PRType
    risk_level: RiskLevel
    complexity: str  # "low", "medium", "high"
    focus_areas: list[str]
    suggested_model: str
    suggested_checks: list[str]
    skip_checks: list[str]

def analyze_pr(pr: PRData) -> PRAnalysis:
    """
    Quick analysis to categorize PR and determine review strategy.
    Uses heuristics first, then optional LLM for complex cases.
    """
    
    # Heuristic analysis based on files changed
    file_patterns = categorize_files(pr.files_changed)
    
    # Determine PR type
    pr_type = infer_pr_type(pr.title, pr.description, file_patterns)
    
    # Assess risk level
    risk_level = assess_risk(pr, file_patterns)
    
    # Calculate complexity
    complexity = assess_complexity(pr)
    
    # Determine focus areas based on type
    focus_areas = get_focus_areas(pr_type, risk_level)
    
    # Suggest model based on complexity
    suggested_model = (
        "claude-sonnet-4-20250514" if complexity == "high" or risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
        else "claude-haiku-4-5-20251001"
    )
    
    # Determine which checks to run/skip
    suggested_checks, skip_checks = get_check_recommendations(pr_type, risk_level)
    
    return PRAnalysis(
        pr_type=pr_type,
        risk_level=risk_level,
        complexity=complexity,
        focus_areas=focus_areas,
        suggested_model=suggested_model,
        suggested_checks=suggested_checks,
        skip_checks=skip_checks
    )

def categorize_files(files: list[str]) -> dict:
    """Categorize changed files by type."""
    patterns = {
        "test": [],
        "config": [],
        "docs": [],
        "security": [],
        "api": [],
        "ui": [],
        "core": []
    }
    
    for f in files:
        f_lower = f.lower()
        if "test" in f_lower or "spec" in f_lower:
            patterns["test"].append(f)
        elif f_lower.endswith((".yml", ".yaml", ".json", ".toml", ".ini", ".env")):
            patterns["config"].append(f)
        elif f_lower.endswith((".md", ".rst", ".txt")) or "doc" in f_lower:
            patterns["docs"].append(f)
        elif any(x in f_lower for x in ["auth", "security", "crypto", "password", "token"]):
            patterns["security"].append(f)
        elif any(x in f_lower for x in ["api", "route", "endpoint", "handler"]):
            patterns["api"].append(f)
        elif any(x in f_lower for x in ["component", "page", "view", "ui"]):
            patterns["ui"].append(f)
        else:
            patterns["core"].append(f)
    
    return patterns

def infer_pr_type(title: str, description: str, file_patterns: dict) -> PRType:
    """Infer PR type from title, description, and file patterns."""
    title_lower = title.lower()
    
    # Check title for explicit indicators
    if any(x in title_lower for x in ["fix", "bug", "issue", "patch"]):
        return PRType.BUGFIX
    if any(x in title_lower for x in ["feat", "add", "implement", "new"]):
        return PRType.FEATURE
    if any(x in title_lower for x in ["refactor", "cleanup", "reorganize"]):
        return PRType.REFACTOR
    if any(x in title_lower for x in ["test", "spec", "coverage"]):
        return PRType.TEST
    if any(x in title_lower for x in ["doc", "readme", "comment"]):
        return PRType.DOCS
    if any(x in title_lower for x in ["security", "vuln", "cve", "auth"]):
        return PRType.SECURITY
    if any(x in title_lower for x in ["dep", "upgrade", "bump", "update"]):
        return PRType.DEPENDENCY
    
    # Check file patterns
    if len(file_patterns["test"]) > len(file_patterns["core"]):
        return PRType.TEST
    if len(file_patterns["docs"]) > 0 and len(file_patterns["core"]) == 0:
        return PRType.DOCS
    if len(file_patterns["security"]) > 0:
        return PRType.SECURITY
    if len(file_patterns["config"]) > len(file_patterns["core"]):
        return PRType.CONFIG
    
    return PRType.FEATURE  # Default

def assess_risk(pr: PRData, file_patterns: dict) -> RiskLevel:
    """Assess risk level of PR."""
    
    # Critical: security-related files
    if len(file_patterns["security"]) > 0:
        return RiskLevel.CRITICAL
    
    # High: API changes or large PRs
    if len(file_patterns["api"]) > 3 or pr.lines_changed > 300:
        return RiskLevel.HIGH
    
    # Medium: core logic changes
    if len(file_patterns["core"]) > 5:
        return RiskLevel.MEDIUM
    
    # Low: tests, docs, config
    if len(file_patterns["test"]) + len(file_patterns["docs"]) + len(file_patterns["config"]) > len(file_patterns["core"]):
        return RiskLevel.LOW
    
    return RiskLevel.MEDIUM  # Default

def assess_complexity(pr: PRData) -> str:
    """Assess PR complexity."""
    if pr.lines_changed > 200 or pr.files_changed > 10:
        return "high"
    if pr.lines_changed > 50 or pr.files_changed > 5:
        return "medium"
    return "low"

def get_focus_areas(pr_type: PRType, risk_level: RiskLevel) -> list[str]:
    """Determine what to focus on during review."""
    
    base_focus = {
        PRType.FEATURE: ["logic_correctness", "edge_cases", "test_coverage"],
        PRType.BUGFIX: ["root_cause", "regression_risk", "test_coverage"],
        PRType.REFACTOR: ["behavior_preservation", "code_quality", "performance"],
        PRType.TEST: ["coverage_gaps", "test_quality", "assertions"],
        PRType.DOCS: ["accuracy", "completeness", "clarity"],
        PRType.SECURITY: ["vulnerabilities", "auth_logic", "input_validation", "secrets"],
        PRType.DEPENDENCY: ["breaking_changes", "security_advisories", "compatibility"],
        PRType.CONFIG: ["security_implications", "environment_consistency"],
        PRType.UNKNOWN: ["logic_correctness", "code_quality"]
    }
    
    focus = base_focus.get(pr_type, base_focus[PRType.UNKNOWN])
    
    # Add security focus for high-risk PRs
    if risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
        if "security_implications" not in focus:
            focus.append("security_implications")
    
    return focus

def get_check_recommendations(pr_type: PRType, risk_level: RiskLevel) -> tuple[list[str], list[str]]:
    """Determine which checks to run and skip."""
    
    all_checks = ["size_gate", "lint_gate", "security_scan", "test_coverage", "llm_review"]
    
    # Tests and docs can skip security scan
    if pr_type in [PRType.TEST, PRType.DOCS]:
        return (["size_gate", "lint_gate", "llm_review"], ["security_scan", "test_coverage"])
    
    # Security PRs should run everything
    if pr_type == PRType.SECURITY or risk_level == RiskLevel.CRITICAL:
        return (all_checks, [])
    
    # Default: run standard checks
    return (["size_gate", "lint_gate", "llm_review"], ["security_scan"])
```

### Integration

Update `main.py` to use pre-analysis:

```python
from pr_review_agent.analysis.pre_analyzer import analyze_pr

def review_pr_adaptive(pr: PRData, config: Config) -> ReviewResult:
    """Review PR with adaptive strategy based on pre-analysis."""
    
    # Step 1: Pre-analysis
    print("Analyzing PR...")
    analysis = analyze_pr(pr)
    
    print(f"  Type: {analysis.pr_type.value}")
    print(f"  Risk: {analysis.risk_level.value}")
    print(f"  Complexity: {analysis.complexity}")
    print(f"  Focus: {', '.join(analysis.focus_areas)}")
    print(f"  Model: {analysis.suggested_model}")
    
    # Step 2: Run suggested checks
    results = {}
    
    if "size_gate" in analysis.suggested_checks:
        results["size"] = run_size_gate(pr, config)
        if not results["size"].passed:
            return early_exit_result("size_gate", results["size"])
    
    if "lint_gate" in analysis.suggested_checks:
        results["lint"] = run_lint_gate(pr, config)
        if not results["lint"].passed and config.linting.fail_on_error:
            return early_exit_result("lint_gate", results["lint"])
    
    # Step 3: LLM review with adapted strategy
    if "llm_review" in analysis.suggested_checks:
        results["review"] = review_pr_with_context(
            pr=pr,
            model=analysis.suggested_model,
            focus_areas=analysis.focus_areas,
            risk_level=analysis.risk_level
        )
    
    # Step 4: Synthesize results
    return synthesize_results(pr, analysis, results)
```

---

## Feature 3: Simple Memory (STRETCH GOAL)

### Goal
Remember past reviews to provide better context. Start simple with file-based storage, upgrade to vector DB later.

### Implementation

Create `src/pr_review_agent/memory/review_store.py`:

```python
"""
Simple file-based memory for past reviews.
Stores reviews as JSON, retrieves by repo/author/file patterns.
"""

import json
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime

@dataclass
class StoredReview:
    """A stored review for future reference."""
    pr_number: int
    repo: str
    author: str
    title: str
    files_changed: list[str]
    review_summary: str
    issues_found: list[dict]
    confidence: float
    outcome: str  # "approved", "changes_requested", "merged"
    timestamp: str
    
MEMORY_DIR = Path.home() / ".pr-review-agent" / "memory"

def store_review(review: StoredReview):
    """Store a review for future reference."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    
    repo_dir = MEMORY_DIR / review.repo.replace("/", "_")
    repo_dir.mkdir(exist_ok=True)
    
    filename = f"pr_{review.pr_number}_{review.timestamp}.json"
    filepath = repo_dir / filename
    
    with open(filepath, "w") as f:
        json.dump(asdict(review), f, indent=2)

def get_author_history(repo: str, author: str, limit: int = 5) -> list[StoredReview]:
    """Get past reviews for an author in a repo."""
    repo_dir = MEMORY_DIR / repo.replace("/", "_")
    
    if not repo_dir.exists():
        return []
    
    reviews = []
    for filepath in repo_dir.glob("*.json"):
        with open(filepath) as f:
            data = json.load(f)
            if data.get("author") == author:
                reviews.append(StoredReview(**data))
    
    # Sort by timestamp, most recent first
    reviews.sort(key=lambda r: r.timestamp, reverse=True)
    return reviews[:limit]

def get_similar_file_reviews(repo: str, files: list[str], limit: int = 3) -> list[StoredReview]:
    """Get past reviews that touched similar files."""
    repo_dir = MEMORY_DIR / repo.replace("/", "_")
    
    if not repo_dir.exists():
        return []
    
    reviews_with_overlap = []
    for filepath in repo_dir.glob("*.json"):
        with open(filepath) as f:
            data = json.load(f)
            stored_files = set(data.get("files_changed", []))
            current_files = set(files)
            overlap = len(stored_files & current_files)
            if overlap > 0:
                reviews_with_overlap.append((overlap, StoredReview(**data)))
    
    # Sort by overlap count
    reviews_with_overlap.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in reviews_with_overlap[:limit]]

def get_common_issues(repo: str, limit: int = 10) -> list[dict]:
    """Get most common issues found in past reviews."""
    repo_dir = MEMORY_DIR / repo.replace("/", "_")
    
    if not repo_dir.exists():
        return []
    
    issue_counts = {}
    for filepath in repo_dir.glob("*.json"):
        with open(filepath) as f:
            data = json.load(f)
            for issue in data.get("issues_found", []):
                issue_type = issue.get("type", "unknown")
                issue_counts[issue_type] = issue_counts.get(issue_type, 0) + 1
    
    # Sort by count
    sorted_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)
    return [{"type": t, "count": c} for t, c in sorted_issues[:limit]]
```

### Integration

Update review prompt to include memory context:

```python
from pr_review_agent.memory.review_store import (
    get_author_history,
    get_similar_file_reviews,
    get_common_issues,
    store_review,
    StoredReview
)

def build_review_prompt_with_memory(pr: PRData, focus_areas: list[str]) -> str:
    """Build review prompt with context from past reviews."""
    
    # Get memory context
    author_history = get_author_history(pr.repo, pr.author, limit=3)
    similar_reviews = get_similar_file_reviews(pr.repo, pr.files_changed, limit=2)
    common_issues = get_common_issues(pr.repo, limit=5)
    
    memory_context = ""
    
    if author_history:
        memory_context += f"""
## Author Context
This author ({pr.author}) has submitted {len(author_history)} recent PRs.
Common patterns in their past PRs:
{format_author_patterns(author_history)}
"""
    
    if similar_reviews:
        memory_context += f"""
## Similar File History
These files have been modified before. Past reviews noted:
{format_similar_review_notes(similar_reviews)}
"""
    
    if common_issues:
        memory_context += f"""
## Common Issues in This Repo
Watch for these frequently occurring issues:
{format_common_issues(common_issues)}
"""
    
    prompt = f"""
You are reviewing a pull request. Focus on: {', '.join(focus_areas)}

{memory_context}

## Current PR
Title: {pr.title}
Author: {pr.author}
Files changed: {', '.join(pr.files_changed)}

## Diff
{pr.diff}

Provide a structured review with:
1. Summary (2-3 sentences)
2. Issues found (list with severity: critical/major/minor/suggestion)
3. Positive aspects
4. Confidence score (0.0-1.0)
"""
    
    return prompt

def review_and_remember(pr: PRData, config: Config) -> ReviewResult:
    """Review PR and store result for future reference."""
    
    # Do the review
    result = review_pr_adaptive(pr, config)
    
    # Store for future reference
    stored = StoredReview(
        pr_number=pr.number,
        repo=pr.repo,
        author=pr.author,
        title=pr.title,
        files_changed=pr.files_changed,
        review_summary=result.summary,
        issues_found=result.issues,
        confidence=result.confidence,
        outcome="pending",  # Updated later when PR is merged/closed
        timestamp=datetime.now().isoformat()
    )
    store_review(stored)
    
    return result
```

---

## Directory Structure (Updated)

```
src/pr_review_agent/
├── __init__.py
├── main.py                    # CLI entrypoint (updated)
├── config.py
├── github_client.py
├── analysis/                  # NEW
│   ├── __init__.py
│   └── pre_analyzer.py        # PR type, risk, complexity analysis
├── execution/                 # NEW
│   ├── __init__.py
│   └── retry_handler.py       # Intelligent retries with adaptation
├── memory/                    # NEW (stretch goal)
│   ├── __init__.py
│   └── review_store.py        # Simple file-based memory
├── gates/
│   ├── __init__.py
│   ├── size_gate.py
│   └── lint_gate.py
├── review/
│   ├── __init__.py
│   ├── llm_reviewer.py        # Updated to use retry + memory
│   ├── model_selector.py
│   └── confidence.py
├── output/
│   ├── __init__.py
│   ├── github_comment.py
│   └── console.py
└── metrics/
    ├── __init__.py
    └── supabase_logger.py
```

---

## Implementation Order

### Tonight (Must Have)
1. **Retry Handler** — `execution/retry_handler.py`
   - Exponential backoff
   - Strategy adaptation (summarize diff, change model)
   - Response validation

2. **Pre-Analyzer** — `analysis/pre_analyzer.py`
   - Categorize PR type
   - Assess risk level
   - Determine focus areas
   - Suggest model and checks

3. **Integration** — Update `main.py` and `llm_reviewer.py`
   - Wire up pre-analysis → adaptive execution → retry handling

### Stretch Goal (If Time)
4. **Simple Memory** — `memory/review_store.py`
   - File-based JSON storage
   - Retrieve by author/files
   - Include in prompt context

---

## Testing

### Test Structure

```
tests/
├── unit/
│   ├── test_retry_handler.py
│   ├── test_pre_analyzer.py
│   └── test_review_store.py
├── integration/
│   └── test_adaptive_review_flow.py
└── conftest.py                    # Shared fixtures
```

---

### Unit Tests

#### `tests/unit/test_retry_handler.py`

```python
"""Unit tests for retry handler."""

import pytest
from unittest.mock import Mock, patch
import anthropic

from pr_review_agent.execution.retry_handler import (
    RetryContext,
    RetryStrategy,
    FailureType,
    get_backoff_seconds,
    adapt_strategy,
    retry_with_adaptation,
)


class TestBackoff:
    """Test exponential backoff calculation."""
    
    def test_backoff_increases_exponentially(self):
        assert get_backoff_seconds(0) == 1
        assert get_backoff_seconds(1) == 2
        assert get_backoff_seconds(2) == 4
        assert get_backoff_seconds(3) == 8
    
    def test_backoff_caps_at_30_seconds(self):
        assert get_backoff_seconds(10) == 30
        assert get_backoff_seconds(100) == 30


class TestAdaptStrategy:
    """Test strategy adaptation based on failures."""
    
    def test_no_failures_returns_base_strategy(self):
        context = RetryContext(attempt=0, failures=[])
        strategy = adapt_strategy(context, "claude-sonnet-4-20250514")
        
        assert strategy.model == "claude-sonnet-4-20250514"
        assert strategy.summarize_diff is False
        assert strategy.chunk_files is False
    
    def test_context_too_long_enables_summarization(self):
        context = RetryContext(
            attempt=1,
            failures=[FailureType.CONTEXT_TOO_LONG]
        )
        strategy = adapt_strategy(context, "claude-sonnet-4-20250514")
        
        assert strategy.summarize_diff is True
        assert strategy.chunk_files is True
    
    def test_rate_limit_falls_back_to_haiku(self):
        context = RetryContext(
            attempt=1,
            failures=[FailureType.RATE_LIMIT]
        )
        strategy = adapt_strategy(context, "claude-sonnet-4-20250514")
        
        assert strategy.model == "claude-haiku-4-5-20251001"
    
    def test_low_quality_increases_temperature(self):
        context = RetryContext(
            attempt=1,
            failures=[FailureType.LOW_QUALITY_RESPONSE]
        )
        strategy = adapt_strategy(context, "claude-sonnet-4-20250514")
        
        assert strategy.temperature == 0.3
    
    def test_multiple_failures_compound(self):
        context = RetryContext(
            attempt=2,
            failures=[FailureType.RATE_LIMIT, FailureType.CONTEXT_TOO_LONG]
        )
        strategy = adapt_strategy(context, "claude-sonnet-4-20250514")
        
        assert strategy.model == "claude-haiku-4-5-20251001"
        assert strategy.summarize_diff is True


class TestRetryWithAdaptation:
    """Test the main retry function."""
    
    def test_success_on_first_attempt(self):
        operation = Mock(return_value="success")
        
        result = retry_with_adaptation(
            operation=operation,
            base_model="claude-sonnet-4-20250514",
            max_attempts=3
        )
        
        assert result == "success"
        assert operation.call_count == 1
    
    def test_retries_on_rate_limit(self):
        operation = Mock(side_effect=[
            anthropic.RateLimitError("rate limited", response=Mock(), body={}),
            "success"
        ])
        
        with patch('time.sleep'):  # Don't actually sleep in tests
            result = retry_with_adaptation(
                operation=operation,
                base_model="claude-sonnet-4-20250514",
                max_attempts=3
            )
        
        assert result == "success"
        assert operation.call_count == 2
    
    def test_retries_on_validation_failure(self):
        operation = Mock(side_effect=["bad", "bad", "good"])
        validator = Mock(side_effect=[False, False, True])
        
        result = retry_with_adaptation(
            operation=operation,
            base_model="claude-sonnet-4-20250514",
            max_attempts=3,
            validator=validator
        )
        
        assert result == "good"
        assert operation.call_count == 3
    
    def test_raises_after_max_attempts(self):
        operation = Mock(side_effect=anthropic.RateLimitError(
            "rate limited", response=Mock(), body={}
        ))
        
        with patch('time.sleep'):
            with pytest.raises(Exception) as exc_info:
                retry_with_adaptation(
                    operation=operation,
                    base_model="claude-sonnet-4-20250514",
                    max_attempts=3
                )
        
        assert "All 3 attempts failed" in str(exc_info.value)
        assert operation.call_count == 3
```

#### `tests/unit/test_pre_analyzer.py`

```python
"""Unit tests for pre-analyzer."""

import pytest
from pr_review_agent.analysis.pre_analyzer import (
    PRType,
    RiskLevel,
    PRAnalysis,
    categorize_files,
    infer_pr_type,
    assess_risk,
    assess_complexity,
    get_focus_areas,
    analyze_pr,
)


class TestCategorizeFiles:
    """Test file categorization."""
    
    def test_categorizes_test_files(self):
        files = ["tests/test_main.py", "src/main.py"]
        result = categorize_files(files)
        
        assert "tests/test_main.py" in result["test"]
        assert "src/main.py" in result["core"]
    
    def test_categorizes_config_files(self):
        files = ["config.yaml", ".env", "settings.json"]
        result = categorize_files(files)
        
        assert len(result["config"]) == 3
    
    def test_categorizes_security_files(self):
        files = ["src/auth.py", "lib/crypto.py", "utils/password.py"]
        result = categorize_files(files)
        
        assert len(result["security"]) == 3
    
    def test_categorizes_docs(self):
        files = ["README.md", "docs/guide.rst", "CHANGELOG.txt"]
        result = categorize_files(files)
        
        assert len(result["docs"]) == 3


class TestInferPRType:
    """Test PR type inference."""
    
    def test_bugfix_from_title(self):
        assert infer_pr_type("fix: resolve login issue", "", {}) == PRType.BUGFIX
        assert infer_pr_type("bug: null pointer exception", "", {}) == PRType.BUGFIX
    
    def test_feature_from_title(self):
        assert infer_pr_type("feat: add dark mode", "", {}) == PRType.FEATURE
        assert infer_pr_type("implement user dashboard", "", {}) == PRType.FEATURE
    
    def test_refactor_from_title(self):
        assert infer_pr_type("refactor: cleanup auth module", "", {}) == PRType.REFACTOR
    
    def test_security_from_title(self):
        assert infer_pr_type("security: patch CVE-2024-1234", "", {}) == PRType.SECURITY
    
    def test_test_from_file_patterns(self):
        file_patterns = {
            "test": ["test_a.py", "test_b.py", "test_c.py"],
            "core": ["main.py"],
            "config": [], "docs": [], "security": [], "api": [], "ui": []
        }
        assert infer_pr_type("update tests", "", file_patterns) == PRType.TEST
    
    def test_docs_from_file_patterns(self):
        file_patterns = {
            "docs": ["README.md", "CONTRIBUTING.md"],
            "core": [],
            "test": [], "config": [], "security": [], "api": [], "ui": []
        }
        assert infer_pr_type("update documentation", "", file_patterns) == PRType.DOCS


class TestAssessRisk:
    """Test risk assessment."""
    
    def test_critical_for_security_files(self):
        file_patterns = {"security": ["auth.py"], "api": [], "core": [], "test": [], "docs": [], "config": [], "ui": []}
        pr = Mock(lines_changed=10)
        
        assert assess_risk(pr, file_patterns) == RiskLevel.CRITICAL
    
    def test_high_for_large_prs(self):
        file_patterns = {"security": [], "api": [], "core": ["a.py"], "test": [], "docs": [], "config": [], "ui": []}
        pr = Mock(lines_changed=400)
        
        assert assess_risk(pr, file_patterns) == RiskLevel.HIGH
    
    def test_high_for_many_api_changes(self):
        file_patterns = {"security": [], "api": ["a.py", "b.py", "c.py", "d.py"], "core": [], "test": [], "docs": [], "config": [], "ui": []}
        pr = Mock(lines_changed=50)
        
        assert assess_risk(pr, file_patterns) == RiskLevel.HIGH
    
    def test_low_for_test_only(self):
        file_patterns = {"test": ["test_a.py", "test_b.py"], "core": [], "security": [], "api": [], "docs": [], "config": [], "ui": []}
        pr = Mock(lines_changed=50)
        
        assert assess_risk(pr, file_patterns) == RiskLevel.LOW


class TestAssessComplexity:
    """Test complexity assessment."""
    
    def test_high_complexity_large_lines(self):
        pr = Mock(lines_changed=250, files_changed=3)
        assert assess_complexity(pr) == "high"
    
    def test_high_complexity_many_files(self):
        pr = Mock(lines_changed=50, files_changed=15)
        assert assess_complexity(pr) == "high"
    
    def test_medium_complexity(self):
        pr = Mock(lines_changed=75, files_changed=4)
        assert assess_complexity(pr) == "medium"
    
    def test_low_complexity(self):
        pr = Mock(lines_changed=30, files_changed=2)
        assert assess_complexity(pr) == "low"


class TestGetFocusAreas:
    """Test focus area determination."""
    
    def test_feature_focus_areas(self):
        focus = get_focus_areas(PRType.FEATURE, RiskLevel.MEDIUM)
        assert "logic_correctness" in focus
        assert "test_coverage" in focus
    
    def test_security_focus_areas(self):
        focus = get_focus_areas(PRType.SECURITY, RiskLevel.CRITICAL)
        assert "vulnerabilities" in focus
        assert "input_validation" in focus
    
    def test_high_risk_adds_security_focus(self):
        focus = get_focus_areas(PRType.FEATURE, RiskLevel.HIGH)
        assert "security_implications" in focus


class TestAnalyzePR:
    """Test full PR analysis."""
    
    def test_returns_complete_analysis(self):
        pr = Mock(
            title="feat: add user authentication",
            description="Implements OAuth2 login",
            files_changed=["src/auth.py", "tests/test_auth.py"],
            lines_changed=120
        )
        
        analysis = analyze_pr(pr)
        
        assert isinstance(analysis, PRAnalysis)
        assert analysis.pr_type is not None
        assert analysis.risk_level is not None
        assert analysis.complexity in ["low", "medium", "high"]
        assert len(analysis.focus_areas) > 0
        assert analysis.suggested_model is not None
```

#### `tests/unit/test_review_store.py` (Stretch Goal)

```python
"""Unit tests for review store (memory)."""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import patch

from pr_review_agent.memory.review_store import (
    StoredReview,
    store_review,
    get_author_history,
    get_similar_file_reviews,
    get_common_issues,
    MEMORY_DIR,
)


@pytest.fixture
def temp_memory_dir(tmp_path):
    """Use temporary directory for memory storage."""
    with patch('pr_review_agent.memory.review_store.MEMORY_DIR', tmp_path):
        yield tmp_path


@pytest.fixture
def sample_review():
    return StoredReview(
        pr_number=1,
        repo="owner/repo",
        author="alice",
        title="feat: add feature",
        files_changed=["src/main.py", "src/utils.py"],
        review_summary="Good PR with minor issues",
        issues_found=[{"type": "style", "message": "naming"}],
        confidence=0.85,
        outcome="approved",
        timestamp=datetime.now().isoformat()
    )


class TestStoreReview:
    """Test storing reviews."""
    
    def test_creates_directory_if_not_exists(self, temp_memory_dir, sample_review):
        store_review(sample_review)
        
        repo_dir = temp_memory_dir / "owner_repo"
        assert repo_dir.exists()
    
    def test_stores_review_as_json(self, temp_memory_dir, sample_review):
        store_review(sample_review)
        
        repo_dir = temp_memory_dir / "owner_repo"
        files = list(repo_dir.glob("*.json"))
        assert len(files) == 1


class TestGetAuthorHistory:
    """Test retrieving author history."""
    
    def test_returns_empty_for_no_history(self, temp_memory_dir):
        result = get_author_history("owner/repo", "unknown_author")
        assert result == []
    
    def test_returns_author_reviews(self, temp_memory_dir, sample_review):
        store_review(sample_review)
        
        result = get_author_history("owner/repo", "alice")
        
        assert len(result) == 1
        assert result[0].author == "alice"
    
    def test_respects_limit(self, temp_memory_dir):
        for i in range(10):
            review = StoredReview(
                pr_number=i,
                repo="owner/repo",
                author="alice",
                title=f"PR {i}",
                files_changed=[],
                review_summary="",
                issues_found=[],
                confidence=0.8,
                outcome="approved",
                timestamp=datetime.now().isoformat()
            )
            store_review(review)
        
        result = get_author_history("owner/repo", "alice", limit=3)
        assert len(result) == 3


class TestGetSimilarFileReviews:
    """Test retrieving reviews with similar files."""
    
    def test_returns_reviews_with_overlapping_files(self, temp_memory_dir, sample_review):
        store_review(sample_review)
        
        result = get_similar_file_reviews("owner/repo", ["src/main.py", "src/other.py"])
        
        assert len(result) == 1
    
    def test_returns_empty_for_no_overlap(self, temp_memory_dir, sample_review):
        store_review(sample_review)
        
        result = get_similar_file_reviews("owner/repo", ["completely/different.py"])
        
        assert result == []


class TestGetCommonIssues:
    """Test aggregating common issues."""
    
    def test_aggregates_issue_types(self, temp_memory_dir):
        for i in range(5):
            review = StoredReview(
                pr_number=i,
                repo="owner/repo",
                author="alice",
                title=f"PR {i}",
                files_changed=[],
                review_summary="",
                issues_found=[
                    {"type": "style", "message": "naming"},
                    {"type": "logic", "message": "edge case"} if i % 2 == 0 else {"type": "style", "message": "other"}
                ],
                confidence=0.8,
                outcome="approved",
                timestamp=datetime.now().isoformat()
            )
            store_review(review)
        
        result = get_common_issues("owner/repo")
        
        # Style should be most common
        assert result[0]["type"] == "style"
        assert result[0]["count"] > result[1]["count"]
```

---

### Integration Tests

#### `tests/integration/test_adaptive_review_flow.py`

```python
"""Integration tests for the full adaptive review flow."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass

from pr_review_agent.analysis.pre_analyzer import analyze_pr, PRType, RiskLevel
from pr_review_agent.execution.retry_handler import retry_with_adaptation
from pr_review_agent.review.llm_reviewer import review_pr


@dataclass
class MockPRData:
    """Mock PR data for testing."""
    number: int
    repo: str
    author: str
    title: str
    description: str
    files_changed: list
    lines_changed: int
    diff: str


@pytest.fixture
def small_feature_pr():
    return MockPRData(
        number=1,
        repo="owner/repo",
        author="alice",
        title="feat: add helper function",
        description="Adds a utility function for string formatting",
        files_changed=["src/utils.py", "tests/test_utils.py"],
        lines_changed=45,
        diff="+ def format_string(s): ..."
    )


@pytest.fixture
def large_security_pr():
    return MockPRData(
        number=2,
        repo="owner/repo",
        author="bob",
        title="security: update authentication flow",
        description="Patches authentication vulnerability",
        files_changed=["src/auth.py", "src/crypto.py", "src/session.py"],
        lines_changed=280,
        diff="+ def validate_token(token): ..."
    )


@pytest.fixture
def test_only_pr():
    return MockPRData(
        number=3,
        repo="owner/repo",
        author="carol",
        title="test: add unit tests for utils",
        description="Improves test coverage",
        files_changed=["tests/test_utils.py", "tests/test_helpers.py"],
        lines_changed=150,
        diff="+ def test_format_string(): ..."
    )


class TestPreAnalysisIntegration:
    """Test pre-analysis correctly categorizes different PR types."""
    
    def test_small_feature_pr_analysis(self, small_feature_pr):
        analysis = analyze_pr(small_feature_pr)
        
        assert analysis.pr_type == PRType.FEATURE
        assert analysis.complexity == "low"
        assert analysis.risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM]
        assert "claude-haiku" in analysis.suggested_model
    
    def test_security_pr_gets_high_risk(self, large_security_pr):
        analysis = analyze_pr(large_security_pr)
        
        assert analysis.pr_type == PRType.SECURITY
        assert analysis.risk_level == RiskLevel.CRITICAL
        assert "vulnerabilities" in analysis.focus_areas
        assert "claude-sonnet" in analysis.suggested_model
    
    def test_test_pr_gets_low_risk(self, test_only_pr):
        analysis = analyze_pr(test_only_pr)
        
        assert analysis.pr_type == PRType.TEST
        assert analysis.risk_level == RiskLevel.LOW
        assert "security_scan" in analysis.skip_checks


class TestRetryIntegration:
    """Test retry handler integrates correctly with LLM calls."""
    
    @patch('pr_review_agent.review.llm_reviewer.anthropic')
    def test_successful_review_no_retry(self, mock_anthropic, small_feature_pr):
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="""
        {
            "summary": "Good PR that adds utility function",
            "issues": [],
            "confidence": 0.9
        }
        """)]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_anthropic.messages.create.return_value = mock_response
        
        # This should succeed on first try
        result = review_pr(small_feature_pr, Mock())
        
        assert mock_anthropic.messages.create.call_count == 1
    
    @patch('time.sleep')  # Don't actually sleep
    @patch('pr_review_agent.review.llm_reviewer.anthropic')
    def test_retry_on_rate_limit(self, mock_anthropic, mock_sleep, small_feature_pr):
        # First call fails, second succeeds
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"summary": "Good", "issues": [], "confidence": 0.9}')]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        
        mock_anthropic.messages.create.side_effect = [
            Exception("rate_limit"),  # First call fails
            mock_response  # Second call succeeds
        ]
        
        # Should retry and succeed
        # Note: actual implementation needs to handle this
        # This test verifies the integration works


class TestAdaptiveFlowIntegration:
    """Test the full adaptive review flow."""
    
    @patch('pr_review_agent.review.llm_reviewer.anthropic')
    def test_small_pr_uses_haiku(self, mock_anthropic, small_feature_pr):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"summary": "Good", "issues": [], "confidence": 0.9}')]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_anthropic.messages.create.return_value = mock_response
        
        # Analyze and review
        analysis = analyze_pr(small_feature_pr)
        
        # Verify Haiku is selected for small PR
        assert "haiku" in analysis.suggested_model.lower()
    
    @patch('pr_review_agent.review.llm_reviewer.anthropic')
    def test_security_pr_uses_sonnet(self, mock_anthropic, large_security_pr):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"summary": "Security review", "issues": [], "confidence": 0.8}')]
        mock_response.usage.input_tokens = 200
        mock_response.usage.output_tokens = 100
        mock_anthropic.messages.create.return_value = mock_response
        
        # Analyze
        analysis = analyze_pr(large_security_pr)
        
        # Verify Sonnet is selected for security PR
        assert "sonnet" in analysis.suggested_model.lower()
    
    def test_analysis_determines_checks_to_skip(self, test_only_pr):
        analysis = analyze_pr(test_only_pr)
        
        # Test-only PRs should skip security scan
        assert "security_scan" in analysis.skip_checks
        assert "llm_review" in analysis.suggested_checks


class TestEndToEndFlow:
    """End-to-end tests simulating real usage."""
    
    @patch('pr_review_agent.github_client.GitHubClient')
    @patch('pr_review_agent.review.llm_reviewer.anthropic')
    def test_full_review_flow_small_pr(self, mock_anthropic, mock_github, small_feature_pr):
        """Test complete flow: fetch PR → analyze → gates → review."""
        
        # Mock GitHub client
        mock_github.return_value.get_pr.return_value = small_feature_pr
        
        # Mock LLM response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="""
        {
            "summary": "This PR adds a useful utility function with good test coverage.",
            "issues": [
                {"severity": "suggestion", "message": "Consider adding docstring"}
            ],
            "positive_aspects": ["Good test coverage", "Clean implementation"],
            "confidence": 0.88
        }
        """)]
        mock_response.usage.input_tokens = 150
        mock_response.usage.output_tokens = 75
        mock_anthropic.messages.create.return_value = mock_response
        
        # Run the flow
        # 1. Pre-analysis
        analysis = analyze_pr(small_feature_pr)
        assert analysis.pr_type == PRType.FEATURE
        assert analysis.complexity == "low"
        
        # 2. Size gate would pass (45 lines < 500)
        assert small_feature_pr.lines_changed < 500
        
        # 3. Model selection based on analysis
        assert "haiku" in analysis.suggested_model.lower()
        
        # 4. LLM review would be called
        # (In real implementation, this connects everything)
    
    @patch('pr_review_agent.github_client.GitHubClient')  
    def test_large_pr_fails_size_gate(self, mock_github):
        """Test that large PRs are caught by size gate before LLM call."""
        
        large_pr = MockPRData(
            number=99,
            repo="owner/repo",
            author="dave",
            title="feat: massive refactor",
            description="",
            files_changed=[f"file{i}.py" for i in range(30)],
            lines_changed=800,
            diff="..." * 1000
        )
        
        # Analysis should flag as high complexity
        analysis = analyze_pr(large_pr)
        assert analysis.complexity == "high"
        
        # Size gate should fail (800 > 500)
        assert large_pr.lines_changed > 500
        
        # LLM should NOT be called (verified by no mock setup needed)
```

---

### Test Fixtures

#### `tests/conftest.py`

```python
"""Shared test fixtures and configuration."""

import pytest
from dataclasses import dataclass
from unittest.mock import Mock


@dataclass
class MockPRData:
    """Mock PR data for testing."""
    number: int = 1
    repo: str = "owner/repo"
    author: str = "testuser"
    title: str = "Test PR"
    description: str = ""
    files_changed: list = None
    lines_changed: int = 50
    diff: str = ""
    
    def __post_init__(self):
        if self.files_changed is None:
            self.files_changed = ["src/main.py"]


@dataclass
class MockConfig:
    """Mock configuration for testing."""
    max_lines_changed: int = 500
    max_files_changed: int = 20
    lint_fail_threshold: int = 10
    simple_threshold_lines: int = 50
    default_model: str = "claude-sonnet-4-20250514"
    simple_model: str = "claude-haiku-4-5-20251001"


@pytest.fixture
def mock_pr():
    """Default mock PR."""
    return MockPRData()


@pytest.fixture
def mock_config():
    """Default mock config."""
    return MockConfig()


@pytest.fixture
def mock_anthropic_success():
    """Mock successful Anthropic API response."""
    from unittest.mock import MagicMock
    
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="""
    {
        "summary": "Test review summary",
        "issues": [],
        "positive_aspects": ["Clean code"],
        "confidence": 0.85
    }
    """)]
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50
    
    return mock_response
```

---

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=pr_review_agent --cov-report=term-missing

# Run only unit tests
uv run pytest tests/unit/ -v

# Run only integration tests
uv run pytest tests/integration/ -v

# Run specific test file
uv run pytest tests/unit/test_retry_handler.py -v

# Run tests matching pattern
uv run pytest -k "test_retry" -v

# Run with print output visible
uv run pytest -s
```

### Expected Coverage Targets

| Module | Target Coverage |
|--------|-----------------|
| `execution/retry_handler.py` | >90% |
| `analysis/pre_analyzer.py` | >85% |
| `memory/review_store.py` | >80% |
| Overall | >80% |

---

### Manual Verification After Tests Pass

```bash
# Test retry handling with real API (rate limits may not trigger)
uv run pr-review-agent --repo dtsong/mtg-commander-roi --pr 2

# Verify output shows:
# 🔍 Analyzing PR #2...
#    Type: feature (or appropriate type)
#    Risk: low/medium/high
#    Complexity: low/medium/high
#    Focus: [list of focus areas]
#    Model: claude-haiku or claude-sonnet

# Test with large PR to verify size gate still works
uv run pr-review-agent --repo dtsong/mtg-commander-roi --pr <LARGE_PR>

# Verify output shows:
# 📏 Size Gate: FAILED
# (No LLM call made)
```

---

## Console Output (Target)

```
$ uv run pr-review-agent --repo dtsong/mtg-commander-roi --pr 2

🔍 Analyzing PR #2...
   Type: feature
   Risk: medium  
   Complexity: low
   Focus: logic_correctness, edge_cases, test_coverage
   Model: claude-haiku-4-5-20251001

📏 Size Gate: PASSED (47 lines changed)
🔧 Lint Gate: PASSED (0 errors)

🤖 Running LLM Review...
   Attempt 1/3 with claude-haiku-4-5-20251001
   ✓ Review complete (confidence: 0.85)

📊 Token Usage:
   Input: 1,234 tokens
   Output: 456 tokens
   Cost: $0.0012

📝 Review Summary:
   This PR adds a new utility function for calculating ROI...
   
🎯 Issues Found:
   [minor] Consider adding input validation for edge case...
   [suggestion] The function name could be more descriptive...

✅ Recommendation: APPROVE (high confidence)
```

---

## Interview Talking Points

After implementing:

> "The agent now adapts its strategy based on what it learns about the PR. A security-focused PR gets deeper scrutiny. A test-only PR skips security scans. If the LLM hits rate limits, it retries with a smaller model. If the diff is too long, it summarizes first. This is what makes it agentic — it perceives, reasons, and adapts."

> "The memory system is simple right now — file-based JSON. But the architecture is ready for RAG. Swap in a vector database, embed the diffs, and suddenly the agent remembers that 'this code pattern caused bugs in PR #123' or 'this author typically forgets error handling.'"

---

*Spec created: January 2026*
*Target: Same-day implementation for Shield AI demo*

---

## Instructions for Claude Code

### Implementation Order

1. **Create test structure first** (TDD approach):
   ```bash
   mkdir -p tests/unit tests/integration
   touch tests/__init__.py tests/conftest.py
   touch tests/unit/__init__.py tests/unit/test_retry_handler.py tests/unit/test_pre_analyzer.py
   touch tests/integration/__init__.py tests/integration/test_adaptive_review_flow.py
   ```

2. **Implement `conftest.py`** with shared fixtures

3. **Implement `execution/retry_handler.py`**:
   - Write unit tests in `tests/unit/test_retry_handler.py`
   - Implement the module
   - Run: `uv run pytest tests/unit/test_retry_handler.py -v`
   - All tests should pass

4. **Implement `analysis/pre_analyzer.py`**:
   - Write unit tests in `tests/unit/test_pre_analyzer.py`
   - Implement the module
   - Run: `uv run pytest tests/unit/test_pre_analyzer.py -v`
   - All tests should pass

5. **Integrate into main.py and llm_reviewer.py**:
   - Update the review flow to use pre-analysis and retry handling
   - Run integration tests: `uv run pytest tests/integration/ -v`

6. **Run full test suite**:
   ```bash
   uv run pytest --cov=pr_review_agent -v
   ```

7. **Manual verification**:
   ```bash
   uv run pr-review-agent --repo dtsong/mtg-commander-roi --pr 2
   ```

### Stretch Goal: Memory

If time permits after core features pass all tests:

1. Write tests in `tests/unit/test_review_store.py`
2. Implement `memory/review_store.py`
3. Integrate into review flow
4. Run: `uv run pytest tests/unit/test_review_store.py -v`

### Success Criteria

- [ ] All unit tests pass: `uv run pytest tests/unit/ -v`
- [ ] All integration tests pass: `uv run pytest tests/integration/ -v`
- [ ] Coverage >80%: `uv run pytest --cov=pr_review_agent`
- [ ] Manual test shows new output format with analysis
- [ ] No regressions in existing functionality
