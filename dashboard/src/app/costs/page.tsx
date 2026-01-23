'use client'

import { useEffect, useState } from 'react'
import { supabase, ReviewEvent } from '@/lib/supabase'
import {
  CostTrendChart,
  CostPerReviewChart,
  CostByRepoChart,
  CostByModelChart,
  OutliersTable,
} from '@/components/CostChart'

type TimeRange = '7d' | '30d' | '90d'

export default function CostsPage() {
  const [reviews, setReviews] = useState<ReviewEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [range, setRange] = useState<TimeRange>('30d')

  useEffect(() => {
    async function fetchData() {
      setLoading(true)
      const daysAgo = range === '7d' ? 7 : range === '30d' ? 30 : 90
      const since = new Date()
      since.setDate(since.getDate() - daysAgo)

      const { data } = await supabase
        .from('review_events')
        .select('*')
        .eq('llm_called', true)
        .gte('created_at', since.toISOString())
        .order('created_at', { ascending: true })

      if (data) {
        setReviews(data)
      }
      setLoading(false)
    }

    fetchData()
  }, [range])

  if (loading) {
    return <div style={{ padding: 40, textAlign: 'center' }}>Loading...</div>
  }

  // Aggregate daily costs
  const dailyCosts = Object.values(
    reviews.reduce<Record<string, { date: string; cost: number; reviews: number }>>((acc, r) => {
      const date = r.created_at.split('T')[0]
      if (!acc[date]) {
        acc[date] = { date, cost: 0, reviews: 0 }
      }
      acc[date].cost += r.cost_usd || 0
      acc[date].reviews += 1
      return acc
    }, {})
  )

  // Cost by repo
  const repoCosts = Object.values(
    reviews.reduce<Record<string, { name: string; cost: number; reviews: number }>>((acc, r) => {
      const key = `${r.repo_owner}/${r.repo_name}`
      if (!acc[key]) {
        acc[key] = { name: key, cost: 0, reviews: 0 }
      }
      acc[key].cost += r.cost_usd || 0
      acc[key].reviews += 1
      return acc
    }, {})
  ).sort((a, b) => b.cost - a.cost)

  // Cost by model
  const modelCosts = Object.values(
    reviews.reduce<Record<string, { model: string; cost: number; tokens: number }>>((acc, r) => {
      const model = r.model_used || 'unknown'
      if (!acc[model]) {
        acc[model] = { model, cost: 0, tokens: 0 }
      }
      acc[model].cost += r.cost_usd || 0
      acc[model].tokens += (r.input_tokens || 0) + (r.output_tokens || 0)
      return acc
    }, {})
  ).sort((a, b) => b.cost - a.cost)

  // Outliers: reviews costing more than 2x the average
  const avgCost = reviews.length > 0
    ? reviews.reduce((sum, r) => sum + (r.cost_usd || 0), 0) / reviews.length
    : 0
  const outliers = reviews
    .filter((r) => (r.cost_usd || 0) > avgCost * 2 && avgCost > 0)
    .sort((a, b) => (b.cost_usd || 0) - (a.cost_usd || 0))
    .slice(0, 10)

  const totalCost = reviews.reduce((sum, r) => sum + (r.cost_usd || 0), 0)

  return (
    <div style={{ padding: 20, maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div>
          <h1 style={{ margin: 0 }}>Cost Attribution</h1>
          <p style={{ color: '#666', margin: '4px 0 0' }}>
            Token spend breakdown by repo, model, and time
          </p>
        </div>
        <a href="/" style={{ color: '#0366d6', textDecoration: 'none' }}>
          ← Dashboard
        </a>
      </div>

      {/* Time range selector */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        {(['7d', '30d', '90d'] as TimeRange[]).map((r) => (
          <button
            key={r}
            onClick={() => setRange(r)}
            style={{
              padding: '6px 14px',
              background: range === r ? '#0366d6' : 'white',
              color: range === r ? 'white' : '#333',
              border: '1px solid #ddd',
              borderRadius: 4,
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            {r === '7d' ? '7 Days' : r === '30d' ? '30 Days' : '90 Days'}
          </button>
        ))}
      </div>

      {/* Summary cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 24 }}>
        <div style={{ background: 'white', padding: 16, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <div style={{ color: '#666', fontSize: 13 }}>Total Spend</div>
          <div style={{ fontSize: 28, fontWeight: 'bold' }}>${totalCost.toFixed(2)}</div>
        </div>
        <div style={{ background: 'white', padding: 16, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <div style={{ color: '#666', fontSize: 13 }}>Reviews</div>
          <div style={{ fontSize: 28, fontWeight: 'bold' }}>{reviews.length}</div>
        </div>
        <div style={{ background: 'white', padding: 16, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <div style={{ color: '#666', fontSize: 13 }}>Avg Cost/Review</div>
          <div style={{ fontSize: 28, fontWeight: 'bold' }}>${avgCost.toFixed(4)}</div>
        </div>
      </div>

      {/* Charts */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
        <CostTrendChart data={dailyCosts} />
        <CostPerReviewChart data={dailyCosts} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
        <CostByRepoChart data={repoCosts.slice(0, 8)} />
        <CostByModelChart data={modelCosts} />
      </div>

      <OutliersTable reviews={outliers} />
    </div>
  )
}
