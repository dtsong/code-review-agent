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

-- Table: approval_decisions
-- Stores human decisions on escalated reviews for audit trail
CREATE TABLE IF NOT EXISTS approval_decisions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

  -- Link to review event
  review_event_id UUID NOT NULL REFERENCES review_events(id),

  -- Decision details
  decision TEXT NOT NULL CHECK (decision IN ('approved', 'overridden', 'dismissed')),
  decided_by TEXT NOT NULL,
  reason TEXT,

  -- PR context (denormalized for quick access)
  repo_owner TEXT NOT NULL,
  repo_name TEXT NOT NULL,
  pr_number INTEGER NOT NULL,
  pr_url TEXT
);

CREATE INDEX IF NOT EXISTS idx_approval_decisions_review
  ON approval_decisions(review_event_id);
CREATE INDEX IF NOT EXISTS idx_approval_decisions_created
  ON approval_decisions(created_at);
CREATE INDEX IF NOT EXISTS idx_approval_decisions_decided_by
  ON approval_decisions(decided_by);

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
