# PR Review Agent Roadmap

> Pass this document to Claude Code to generate a task graph for building out the PR Review Agent.

## Project Context

This is an existing PR review agent with a gate-first architecture:
- **Current gates**: Size gate, Lint gate
- **Current flow**: PR → Size Gate → Lint Gate → Pre-Analysis → LLM Review → Post Comment → Log Metrics
- **Tech stack**: Python 3.12+, uv, Anthropic Claude API, PyGitHub, Supabase, Next.js dashboard
- **Core principle**: Deterministic checks before LLM to save tokens

## Phase 1: Additional Deterministic Gates

These gates run BEFORE the LLM to catch issues cheaply.

### 1.1 Security Scan Gate
**Depends on**: Nothing (can start immediately)
**Files to create/modify**:
- `src/pr_review_agent/gates/security_gate.py`
- `tests/test_security_gate.py`

**Requirements**:
- Integrate with `bandit` for Python security scanning
- Configurable severity threshold in `.ai-review.yaml`
- Return structured results: `SecurityGateResult(passed, findings, severity_counts)`
- Block PR if critical/high severity findings exceed threshold
- Add to pipeline in `main.py` after lint gate

**Config additions** (`.ai-review.yaml`):
```yaml
security:
  enabled: true
  tool: bandit
  fail_on_severity: high  # critical, high, medium, low
  max_findings: 5
```

### 1.2 Test Coverage Gate
**Depends on**: Nothing (can start immediately)
**Files to create/modify**:
- `src/pr_review_agent/gates/coverage_gate.py`
- `tests/test_coverage_gate.py`

**Requirements**:
- Parse coverage reports (support pytest-cov XML format)
- Compare coverage delta: current PR vs base branch
- Fail if coverage drops below threshold or delta is negative
- Return: `CoverageGateResult(passed, current_coverage, delta, uncovered_lines)`

**Config additions**:
```yaml
coverage:
  enabled: true
  min_coverage: 80
  fail_on_decrease: true
  report_path: coverage.xml
```

### 1.3 Dependency Audit Gate
**Depends on**: Nothing (can start immediately)
**Files to create/modify**:
- `src/pr_review_agent/gates/dependency_gate.py`
- `tests/test_dependency_gate.py`

**Requirements**:
- Detect new dependencies added in PR (parse pyproject.toml/requirements.txt diff)
- Check for known vulnerabilities using `pip-audit` or `safety`
- Flag deprecated packages
- Return: `DependencyGateResult(passed, new_deps, vulnerable_deps, deprecated_deps)`

**Config additions**:
```yaml
dependencies:
  enabled: true
  block_vulnerable: true
  block_deprecated: false
  allowed_licenses: [MIT, Apache-2.0, BSD-3-Clause]
```

---

## Phase 2: Review Quality Improvements

Enhance the LLM review output.

### 2.1 Inline Comment Support
**Depends on**: Phase 1 complete (gates stabilized)
**Files to create/modify**:
- `src/pr_review_agent/review/llm_reviewer.py` (modify)
- `src/pr_review_agent/output/github_comment.py` (modify)
- `src/pr_review_agent/github_client.py` (add `post_review_comments`)

**Requirements**:
- Modify LLM prompt to return line-specific feedback with file path and line number
- Use GitHub Review Comments API (not just PR comments)
- Structure: `InlineComment(file, line, body, suggestion)`
- Post as a proper GitHub review (not individual comments)

**Schema for LLM response**:
```python
@dataclass
class InlineComment:
    file: str
    start_line: int
    end_line: int | None
    body: str
    suggestion: str | None  # Code suggestion in diff format
```

### 2.2 Suggested Fixes
**Depends on**: 2.1 Inline Comment Support
**Files to create/modify**:
- `src/pr_review_agent/review/llm_reviewer.py` (modify prompt)
- `src/pr_review_agent/output/github_comment.py` (format suggestions)

**Requirements**:
- Enhance LLM prompt to generate concrete code fixes
- Format as GitHub suggestion blocks (```suggestion)
- User can click "Apply suggestion" directly in GitHub
- Only suggest fixes for high-confidence issues

---

## Phase 3: Smarter Pre-Analysis

Make the pre-analyzer more intelligent.

### 3.1 File-Type Aware Routing
**Depends on**: Nothing (can start immediately)
**Files to create/modify**:
- `src/pr_review_agent/analysis/pre_analyzer.py` (modify)
- `src/pr_review_agent/analysis/file_classifiers.py` (new)

**Requirements**:
- Classify files by domain: infrastructure, frontend, backend, tests, docs, config
- Adjust review focus based on file types in PR
- Route infrastructure changes (Terraform, Docker, CI) to security-focused review
- Route frontend changes to UX/accessibility focus
- Maintain file classification rules in config

**Config additions**:
```yaml
file_routing:
  infrastructure:
    patterns: ["*.tf", "Dockerfile", ".github/workflows/*", "docker-compose.*"]
    focus: [security, idempotency, secrets_exposure]
  frontend:
    patterns: ["*.tsx", "*.jsx", "*.css", "*.scss"]
    focus: [accessibility, performance, xss]
  backend:
    patterns: ["*.py", "*.go", "*.rs"]
    focus: [logic_errors, security, error_handling]
```

### 3.2 Historical Context
**Depends on**: Supabase metrics logging working
**Files to create/modify**:
- `src/pr_review_agent/analysis/history.py` (new)
- `src/pr_review_agent/analysis/pre_analyzer.py` (modify)

**Requirements**:
- Query past reviews for files touched in current PR
- Identify "hot" files (frequently reviewed, high issue density)
- Surface past issues that may be relevant
- Add historical context to LLM prompt
- Store file-level metrics in Supabase

**New Supabase table**:
```sql
CREATE TABLE file_review_history (
  id UUID PRIMARY KEY,
  repo TEXT NOT NULL,
  file_path TEXT NOT NULL,
  review_count INT DEFAULT 0,
  issue_count INT DEFAULT 0,
  last_reviewed_at TIMESTAMPTZ,
  common_issues JSONB
);
```

---

## Phase 4: Human Escalation Workflow

Handle low-confidence reviews gracefully.

### 4.1 Webhook Notifications
**Depends on**: Confidence scoring working
**Files to create/modify**:
- `src/pr_review_agent/escalation/webhook.py` (new)
- `src/pr_review_agent/main.py` (integrate)

**Requirements**:
- Fire webhook on low-confidence reviews
- Configurable webhook URL per repo
- Payload includes: PR link, confidence score, review summary, reason for escalation
- Support Slack incoming webhook format

**Config additions**:
```yaml
escalation:
  enabled: true
  webhook_url: ${ESCALATION_WEBHOOK_URL}
  trigger_below_confidence: 0.5
  slack_format: true
```

### 4.2 Review Queue Dashboard
**Depends on**: 4.1 Webhook Notifications, Dashboard exists
**Files to create/modify**:
- `dashboard/app/queue/page.tsx` (new)
- `dashboard/components/ReviewQueue.tsx` (new)

**Requirements**:
- Display pending escalated reviews
- Show confidence score, PR summary, escalation reason
- Actions: Approve AI review, Override with human review, Dismiss
- Filter by repo, confidence level, age

### 4.3 Approval Workflow
**Depends on**: 4.2 Review Queue Dashboard
**Files to create/modify**:
- `src/pr_review_agent/escalation/approval.py` (new)
- `database/schema.sql` (add approvals table)

**Requirements**:
- Store approval decisions in Supabase
- Track who approved/overrode and when
- Update GitHub PR with approval status
- Audit trail for compliance

---

## Phase 5: Cost Tracking & Optimization

Monitor and control LLM costs.

### 5.1 Token Usage Tracking
**Depends on**: Nothing (can start immediately)
**Files to create/modify**:
- `src/pr_review_agent/metrics/token_tracker.py` (new)
- `src/pr_review_agent/review/llm_reviewer.py` (modify to capture usage)
- `src/pr_review_agent/metrics/supabase_logger.py` (modify)

**Requirements**:
- Capture input/output tokens from Anthropic API response
- Calculate cost based on model pricing
- Log per-review: tokens_in, tokens_out, model, cost_usd
- Add to existing metrics logging

**Supabase schema addition**:
```sql
ALTER TABLE reviews ADD COLUMN tokens_in INT;
ALTER TABLE reviews ADD COLUMN tokens_out INT;
ALTER TABLE reviews ADD COLUMN model TEXT;
ALTER TABLE reviews ADD COLUMN cost_usd DECIMAL(10, 6);
```

### 5.2 Cost Attribution Dashboard
**Depends on**: 5.1 Token Usage Tracking
**Files to create/modify**:
- `dashboard/app/costs/page.tsx` (new)
- `dashboard/components/CostChart.tsx` (new)

**Requirements**:
- Daily/weekly/monthly cost charts
- Breakdown by repo, team, model
- Show cost per review trends
- Identify expensive reviews (outliers)

### 5.3 Budget Alerts
**Depends on**: 5.1 Token Usage Tracking
**Files to create/modify**:
- `src/pr_review_agent/metrics/budget_monitor.py` (new)

**Requirements**:
- Configurable daily/monthly budget limits
- Alert via webhook when approaching limit (80%, 100%)
- Option to pause reviews when budget exceeded
- Per-repo budget allocation

**Config additions**:
```yaml
budget:
  enabled: true
  monthly_limit_usd: 500
  alert_at: [0.8, 1.0]
  pause_on_exceed: false
  webhook_url: ${BUDGET_ALERT_WEBHOOK_URL}
```

---

## Phase 6: MCP Server Integration

Expose the agent as MCP tools for Claude Code.

### 6.1 MCP Server Scaffold
**Depends on**: Core review functionality stable
**Files to create/modify**:
- `src/pr_review_agent/mcp/server.py` (new)
- `src/pr_review_agent/mcp/__init__.py` (new)
- `pyproject.toml` (add mcp dependency, add entry point)

**Requirements**:
- Implement MCP server protocol
- Expose as stdio transport initially
- Add entry point: `pr-review-mcp`

### 6.2 MCP Tools
**Depends on**: 6.1 MCP Server Scaffold
**Files to create/modify**:
- `src/pr_review_agent/mcp/tools.py` (new)

**Tools to expose**:
```
review_pr(repo, pr_number) -> ReviewResult
  Run full review pipeline on a PR

check_pr_size(repo, pr_number) -> SizeCheckResult
  Run only the size gate

check_pr_lint(repo, pr_number) -> LintCheckResult
  Run only the lint gate

get_review_history(repo, file_path?) -> ReviewHistory
  Get past reviews for repo or specific file

get_cost_summary(repo?, days?) -> CostSummary
  Get cost metrics
```

### 6.3 MCP Resources
**Depends on**: 6.2 MCP Tools
**Files to create/modify**:
- `src/pr_review_agent/mcp/resources.py` (new)

**Resources to expose**:
```
config://ai-review.yaml -> Current configuration
review://{repo}/{pr_number} -> Cached review result
metrics://{repo}/summary -> Review metrics summary
```

---

## GitHub Integration Workflow

This roadmap is designed to be executed via GitHub issues and PRs.

### Step 1: Create GitHub Issues

For each task section (1.1, 1.2, etc.), create a GitHub issue:

```bash
# Create milestones first
gh api repos/:owner/:repo/milestones -f title="Phase 1: Additional Gates" -f state="open"
gh api repos/:owner/:repo/milestones -f title="Phase 2: Review Quality" -f state="open"
gh api repos/:owner/:repo/milestones -f title="Phase 3: Smarter Analysis" -f state="open"
gh api repos/:owner/:repo/milestones -f title="Phase 4: Human Escalation" -f state="open"
gh api repos/:owner/:repo/milestones -f title="Phase 5: Cost Tracking" -f state="open"
gh api repos/:owner/:repo/milestones -f title="Phase 6: MCP Server" -f state="open"

# Create labels
gh label create "phase-1" --color "1d76db" --description "Phase 1: Additional Gates"
gh label create "phase-2" --color "0e8a16" --description "Phase 2: Review Quality"
gh label create "phase-3" --color "fbca04" --description "Phase 3: Smarter Analysis"
gh label create "phase-4" --color "d93f0b" --description "Phase 4: Human Escalation"
gh label create "phase-5" --color "5319e7" --description "Phase 5: Cost Tracking"
gh label create "phase-6" --color "006b75" --description "Phase 6: MCP Server"
gh label create "roadmap" --color "c5def5" --description "Part of roadmap execution"
gh label create "gate" --color "bfdadc" --description "Deterministic gate"
gh label create "blocked" --color "b60205" --description "Blocked by dependency"
```

### Step 2: Issue Template

Each issue should follow this structure:

```markdown
## Overview
Brief description of the task.

## Requirements
- Requirement 1
- Requirement 2

## Files to Create/Modify
- [ ] `src/pr_review_agent/path/to/file.py`
- [ ] `tests/test_file.py`

## Config Changes
```yaml
# Any .ai-review.yaml additions
```

## Dependencies
Blocked by #N (if applicable)

## Acceptance Criteria
- [ ] Implementation complete
- [ ] Tests passing (>80% coverage for new code)
- [ ] Documentation updated
- [ ] PR approved and merged
```

### Step 3: Implementation Workflow

For each issue:

```bash
# 1. Create branch
git checkout main && git pull
git checkout -b feat/ISSUE_NUMBER-short-description

# 2. Implement (Claude Code does this)

# 3. Test
uv run ruff check src/
uv run pytest tests/ -v

# 4. Commit with issue reference
git add .
git commit -m "feat: implement security scan gate

- Add bandit integration
- Configure thresholds
- Add to pipeline

Implements #ISSUE_NUMBER"

# 5. Push and create PR
git push -u origin HEAD
gh pr create \
  --title "feat: implement security scan gate" \
  --body "Closes #ISSUE_NUMBER" \
  --label "roadmap,phase-1"
```

### Step 4: Progress Tracking

```bash
# View roadmap progress
gh issue list --label "roadmap" --state all --json number,title,state \
  --jq 'group_by(.state) | map({state: .[0].state, count: length, issues: map("#\(.number) \(.title)")})'
```

---

## Task Generation Instructions for Claude Code

When generating tasks from this roadmap:

1. **Create tasks with dependencies** - Respect the "Depends on" relationships
2. **Start with Phase 1** - These are independent and can parallelize
3. **Group by phase** - Keep phases coherent
4. **Include test tasks** - Every new module needs tests
5. **Add documentation tasks** - Update README, add docstrings
6. **Estimate complexity** - Tag tasks as small/medium/large

**Suggested task naming convention**:
```
[PHASE].[SECTION]-[DESCRIPTION]
Example: 1.1-security-gate-implementation
Example: 2.1-inline-comments-github-api
```

**Priority order for MVP**:
1. Phase 5.1 (Token tracking - quick win, immediate value)
2. Phase 1.1 (Security gate - high value, independent)
3. Phase 2.1 (Inline comments - major UX improvement)
4. Phase 4.1 (Webhook escalation - safety net)
5. Phase 6.1-6.2 (MCP server - enables Claude Code integration)

---

## Success Criteria

The roadmap is complete when:
- [ ] All 3 additional gates implemented and tested
- [ ] Inline comments posting to GitHub Reviews API
- [ ] File-type routing adjusts review focus automatically
- [ ] Low-confidence reviews trigger Slack notification
- [ ] Dashboard shows cost breakdown by repo
- [ ] MCP server exposes `review_pr` tool usable from Claude Code
- [ ] All new code has >80% test coverage
- [ ] README updated with new features
