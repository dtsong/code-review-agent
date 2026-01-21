# Deployment & E2E Testing Guide

This guide walks through deploying the PR Review Agent and verifying it works end-to-end.

## Prerequisites

- GitHub account
- Anthropic API key ([console.anthropic.com](https://console.anthropic.com))
- Supabase account (free tier works)
- Vercel account (free tier works)

## Step 1: Push to GitHub

```bash
# Create a new repo on GitHub first (via web UI or gh CLI)
gh repo create code-review-agent --public --source=. --remote=origin

# Or if repo already exists:
git remote add origin https://github.com/YOUR_USERNAME/code-review-agent.git

# Push
git push -u origin main
```

## Step 2: Set Up Supabase

### 2.1 Create Project

1. Go to [supabase.com](https://supabase.com) and sign in
2. Click "New Project"
3. Choose an organization and enter:
   - Project name: `pr-review-agent`
   - Database password: (generate a strong one)
   - Region: (choose closest to you)
4. Click "Create new project"

### 2.2 Run Schema Migration

1. In your Supabase dashboard, click "SQL Editor" in the left sidebar
2. Click "New query"
3. Copy and paste the contents of `database/schema.sql`:

```sql
-- PR Review Agent - Supabase Schema
-- Run this in your Supabase SQL editor to set up the database

-- Table: review_events
CREATE TABLE IF NOT EXISTS review_events (
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
  issues_found JSONB,

  -- Outcome
  outcome TEXT,
  escalated_to_human BOOLEAN DEFAULT FALSE,

  -- Timing
  review_duration_ms INTEGER
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_review_events_repo
  ON review_events(repo_owner, repo_name);
CREATE INDEX IF NOT EXISTS idx_review_events_created
  ON review_events(created_at);
CREATE INDEX IF NOT EXISTS idx_review_events_author
  ON review_events(pr_author);

-- View: Daily summary for dashboard
CREATE OR REPLACE VIEW daily_review_summary AS
SELECT
  DATE(created_at) as review_date,
  COUNT(*) as total_reviews,
  SUM(CASE WHEN llm_called THEN 1 ELSE 0 END) as llm_reviews,
  SUM(CASE WHEN NOT size_gate_passed OR NOT COALESCE(lint_gate_passed, TRUE) THEN 1 ELSE 0 END) as gated_reviews,
  COALESCE(SUM(cost_usd), 0) as total_cost,
  AVG(confidence_score) as avg_confidence,
  SUM(CASE WHEN escalated_to_human THEN 1 ELSE 0 END) as escalations
FROM review_events
GROUP BY DATE(created_at)
ORDER BY review_date DESC;

-- View: Stats by repository
CREATE OR REPLACE VIEW repo_stats AS
SELECT
  repo_owner,
  repo_name,
  COUNT(*) as total_reviews,
  COALESCE(SUM(cost_usd), 0) as total_cost,
  AVG(confidence_score) as avg_confidence,
  SUM(CASE WHEN escalated_to_human THEN 1 ELSE 0 END) as escalations
FROM review_events
GROUP BY repo_owner, repo_name
ORDER BY total_reviews DESC;
```

4. Click "Run" to execute the SQL

### 2.3 Get API Credentials

1. Click "Project Settings" (gear icon) in the left sidebar
2. Click "API" under "Configuration"
3. Copy these values:
   - **Project URL**: `https://xxx.supabase.co`
   - **anon public** key: `eyJ...` (under "Project API keys")

Save these - you'll need them for both the dashboard and GitHub secrets.

## Step 3: Deploy Dashboard to Vercel

### 3.1 Import Project

1. Go to [vercel.com](https://vercel.com) and sign in
2. Click "Add New..." → "Project"
3. Import your GitHub repository
4. Configure:
   - **Framework Preset**: Next.js (auto-detected)
   - **Root Directory**: `dashboard`
5. Add environment variables:
   - `NEXT_PUBLIC_SUPABASE_URL` = your Supabase Project URL
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY` = your Supabase anon key
6. Click "Deploy"

### 3.2 Verify Deployment

Once deployed, visit your Vercel URL (e.g., `https://code-review-agent.vercel.app`).

You should see the dashboard with:
- Empty charts (no data yet)
- "0" for all metrics
- Empty recent reviews table

This is expected - we haven't run any reviews yet.

## Step 4: Configure GitHub Secrets

### 4.1 Add Repository Secrets

In your GitHub repository:

1. Go to "Settings" → "Secrets and variables" → "Actions"
2. Click "New repository secret"
3. Add these secrets:

| Name | Value |
|------|-------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key (`sk-ant-...`) |
| `SUPABASE_URL` | Your Supabase Project URL |
| `SUPABASE_KEY` | Your Supabase anon key |

Note: `GITHUB_TOKEN` is automatically provided by GitHub Actions.

## Step 5: E2E Test

### 5.1 Create a Test Branch

```bash
# Create a test branch
git checkout -b test/e2e-verification

# Make a small change (e.g., add a comment)
echo "# Test comment" >> src/pr_review_agent/__init__.py

# Commit and push
git add .
git commit -m "test: verify PR review agent"
git push -u origin test/e2e-verification
```

### 5.2 Open a Pull Request

1. Go to your GitHub repository
2. Click "Compare & pull request" for the new branch
3. Create the PR with title: "Test: E2E Verification"

### 5.3 Watch the Action Run

1. Go to "Actions" tab in your repository
2. You should see "AI PR Review" workflow running
3. Click on it to watch progress

Expected flow:
1. Checkout code
2. Set up Python 3.12
3. Install uv
4. Install dependencies
5. Run PR Review Agent

### 5.4 Verify Results

**GitHub PR Comment:**
- A comment should appear on your PR
- It should contain the AI review with findings and confidence score

**Supabase Data:**
1. Go to your Supabase dashboard
2. Click "Table Editor" in the left sidebar
3. Select `review_events` table
4. You should see a new row with your review data

**Dashboard:**
1. Visit your Vercel dashboard URL
2. Refresh the page
3. You should now see:
   - Total Reviews: 1
   - A data point in the charts
   - Your review in the "Recent Reviews" table

### 5.5 Clean Up

```bash
# Delete the test branch
git checkout main
git branch -D test/e2e-verification
git push origin --delete test/e2e-verification

# Close the PR on GitHub (if not auto-closed)
```

## Troubleshooting

### Action Fails: "ANTHROPIC_API_KEY required"

- Verify the secret is set in repository settings
- Check the secret name is exactly `ANTHROPIC_API_KEY`

### No Comment Posted

- Check the workflow has `pull-requests: write` permission
- Verify `--post-comment` flag is in the workflow

### No Data in Supabase

- Verify `SUPABASE_URL` and `SUPABASE_KEY` secrets are set
- Check the URL format: `https://xxx.supabase.co` (no trailing slash)
- Check Supabase logs for errors

### Dashboard Shows No Data

- Verify environment variables in Vercel
- Check browser console for errors
- Ensure the Supabase views were created (check SQL Editor)

### Size Gate Rejects PR

- This is expected for large PRs (>500 lines)
- Adjust `limits.max_lines_changed` in `.ai-review.yaml`

### Lint Gate Fails

- This means there are lint errors in the Python code
- Run `uv run ruff check .` locally to see errors
- Fix errors or adjust `linting.fail_threshold`

## Cost Estimation

With default settings:

| PR Size | Model | Approx Cost |
|---------|-------|-------------|
| <50 lines | Haiku | ~$0.001 |
| 50-500 lines | Sonnet | ~$0.01-0.05 |
| Gated (too large/lint fails) | None | $0 |

The gate-first architecture means you only pay for well-formed PRs that deserve AI review.

## Next Steps

- [ ] Customize `.ai-review.yaml` for your codebase
- [ ] Add the workflow to other repositories
- [ ] Set up alerts for low-confidence reviews
- [ ] Monitor costs via the dashboard
