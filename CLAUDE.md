# PR Review Agent - Development Guidelines

## Architecture

Gate-first architecture: deterministic checks before LLM costs.

```
PR → Size Gate → Lint Gate → Model Select → LLM Review → Output
```

## Key Modules

| Module | Purpose |
|--------|---------|
| `gates/size_gate.py` | Reject PRs exceeding size limits |
| `gates/lint_gate.py` | Run Ruff, fail on threshold |
| `review/model_selector.py` | Haiku for small, Sonnet for large |
| `review/llm_reviewer.py` | Claude API integration |
| `review/confidence.py` | Score-based escalation |
| `output/github_comment.py` | Post formatted PR comments |
| `metrics/supabase_logger.py` | Dashboard data logging |

## Running Locally

```bash
# Review a PR (console output only)
uv run pr-review-agent --repo owner/repo --pr 123

# Review and post comment
uv run pr-review-agent --repo owner/repo --pr 123 --post-comment
```

## Testing

```bash
uv run pytest                    # All tests
uv run pytest tests/test_*.py -v # Verbose
```

## Configuration

Edit `.ai-review.yaml` for:
- Size limits (`limits.max_lines_changed`)
- Lint thresholds (`linting.fail_threshold`)
- Model selection (`llm.simple_threshold_lines`)
- Confidence thresholds (`confidence.high`, `confidence.low`)

## Commit Convention

Format: `<type>: <description>`
Types: feat, fix, refactor, test, docs, chore
