'use client'

import { useState } from 'react'
import { supabase, EscalatedReview } from '@/lib/supabase'

type FilterState = {
  repo: string
  confidenceMax: number
  ageHours: number
}

type Action = 'approve' | 'override' | 'dismiss'

export default function ReviewQueue({
  reviews,
  onAction,
}: {
  reviews: EscalatedReview[]
  onAction: (id: string, action: Action) => void
}) {
  const [filter, setFilter] = useState<FilterState>({
    repo: '',
    confidenceMax: 1.0,
    ageHours: 0,
  })

  const repos = Array.from(
    new Set(reviews.map((r) => `${r.repo_owner}/${r.repo_name}`))
  )

  const filtered = reviews.filter((r) => {
    if (filter.repo && `${r.repo_owner}/${r.repo_name}` !== filter.repo) {
      return false
    }
    if (r.confidence_score > filter.confidenceMax) {
      return false
    }
    if (filter.ageHours > 0) {
      const age = Date.now() - new Date(r.created_at).getTime()
      if (age > filter.ageHours * 3600000) {
        return false
      }
    }
    return true
  })

  return (
    <div>
      {/* Filters */}
      <div style={{
        display: 'flex',
        gap: 16,
        marginBottom: 20,
        padding: 16,
        background: 'white',
        borderRadius: 8,
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
      }}>
        <div>
          <label style={{ fontSize: 12, color: '#666', display: 'block' }}>
            Repository
          </label>
          <select
            value={filter.repo}
            onChange={(e) => setFilter({ ...filter, repo: e.target.value })}
            style={{ padding: '4px 8px', borderRadius: 4, border: '1px solid #ddd' }}
          >
            <option value="">All repos</option>
            {repos.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </div>
        <div>
          <label style={{ fontSize: 12, color: '#666', display: 'block' }}>
            Max Confidence
          </label>
          <select
            value={filter.confidenceMax}
            onChange={(e) => setFilter({
              ...filter,
              confidenceMax: parseFloat(e.target.value),
            })}
            style={{ padding: '4px 8px', borderRadius: 4, border: '1px solid #ddd' }}
          >
            <option value={1.0}>All</option>
            <option value={0.5}>Below 50%</option>
            <option value={0.3}>Below 30%</option>
          </select>
        </div>
        <div>
          <label style={{ fontSize: 12, color: '#666', display: 'block' }}>
            Age
          </label>
          <select
            value={filter.ageHours}
            onChange={(e) => setFilter({
              ...filter,
              ageHours: parseInt(e.target.value),
            })}
            style={{ padding: '4px 8px', borderRadius: 4, border: '1px solid #ddd' }}
          >
            <option value={0}>Any time</option>
            <option value={24}>Last 24h</option>
            <option value={72}>Last 3 days</option>
            <option value={168}>Last 7 days</option>
          </select>
        </div>
      </div>

      {/* Queue */}
      {filtered.length === 0 ? (
        <div style={{
          padding: 40,
          textAlign: 'center',
          background: 'white',
          borderRadius: 8,
          color: '#666',
        }}>
          No pending reviews match the current filters.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {filtered.map((review) => (
            <div
              key={review.id}
              style={{
                background: 'white',
                padding: 16,
                borderRadius: 8,
                boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
                borderLeft: `4px solid ${
                  review.confidence_score < 0.3 ? '#dc3545' : '#ffc107'
                }`,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <a
                    href={review.pr_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ fontWeight: 'bold', fontSize: 16, color: '#0366d6' }}
                  >
                    {review.repo_name}#{review.pr_number}
                  </a>
                  <div style={{ color: '#333', marginTop: 4 }}>{review.pr_title}</div>
                  <div style={{ color: '#666', fontSize: 13, marginTop: 4 }}>
                    by {review.pr_author} &middot;{' '}
                    {new Date(review.created_at).toLocaleString()}
                  </div>
                </div>
                <div style={{
                  background: review.confidence_score < 0.3 ? '#f8d7da' : '#fff3cd',
                  padding: '4px 10px',
                  borderRadius: 12,
                  fontSize: 13,
                  fontWeight: 'bold',
                }}>
                  {(review.confidence_score * 100).toFixed(0)}%
                </div>
              </div>

              {/* Issues summary */}
              {review.issues_found && review.issues_found.length > 0 && (
                <div style={{ marginTop: 8, fontSize: 13, color: '#555' }}>
                  {review.issues_found.length} issue(s) found
                  {review.issues_found.filter((i: any) => i.severity === 'critical').length > 0 &&
                    ' (includes critical)'}
                </div>
              )}

              {/* Actions */}
              <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
                <button
                  onClick={() => onAction(review.id, 'approve')}
                  style={{
                    padding: '6px 12px',
                    background: '#28a745',
                    color: 'white',
                    border: 'none',
                    borderRadius: 4,
                    cursor: 'pointer',
                    fontSize: 13,
                  }}
                >
                  Approve AI Review
                </button>
                <button
                  onClick={() => onAction(review.id, 'override')}
                  style={{
                    padding: '6px 12px',
                    background: '#0366d6',
                    color: 'white',
                    border: 'none',
                    borderRadius: 4,
                    cursor: 'pointer',
                    fontSize: 13,
                  }}
                >
                  Override (Human Review)
                </button>
                <button
                  onClick={() => onAction(review.id, 'dismiss')}
                  style={{
                    padding: '6px 12px',
                    background: '#6c757d',
                    color: 'white',
                    border: 'none',
                    borderRadius: 4,
                    cursor: 'pointer',
                    fontSize: 13,
                  }}
                >
                  Dismiss
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
