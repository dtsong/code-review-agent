import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

export const supabase = createClient(supabaseUrl, supabaseKey)

export interface ReviewEvent {
  id: string
  created_at: string
  repo_owner: string
  repo_name: string
  pr_number: number
  pr_title: string
  pr_author: string
  pr_url: string
  lines_added: number
  lines_removed: number
  files_changed: number
  size_gate_passed: boolean
  lint_gate_passed: boolean
  lint_errors_count: number
  llm_called: boolean
  model_used: string
  input_tokens: number
  output_tokens: number
  cost_usd: number
  confidence_score: number
  issues_found: any[]
  outcome: string
  escalated_to_human: boolean
  review_duration_ms: number
}

export interface DailySummary {
  review_date: string
  total_reviews: number
  llm_reviews: number
  gated_reviews: number
  total_cost: number
  avg_confidence: number
  escalations: number
}

export interface CostByRepo {
  repo_owner: string
  repo_name: string
  total_cost: number
  review_count: number
}

export interface CostByModel {
  model_used: string
  total_cost: number
  total_tokens: number
  review_count: number
}

export interface EscalatedReview {
  id: string
  created_at: string
  repo_owner: string
  repo_name: string
  pr_number: number
  pr_title: string
  pr_author: string
  pr_url: string
  confidence_score: number
  issues_found: any[]
  outcome: string
  review_duration_ms: number
}

export interface EvalRun {
  id: string
  created_at: string
  eval_suite: string
  model_used: string
  precision: number
  recall: number
  f1_score: number
  total_cases: number
  true_positives: number
  false_positives: number
  false_negatives: number
  avg_confidence: number
  avg_cost_usd: number
  total_duration_ms: number
}

export interface EvalIssueBreakdown {
  category: string
  true_positives: number
  false_positives: number
  false_negatives: number
  precision: number
  recall: number
}
