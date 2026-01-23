'use client'

import { useEffect, useState } from 'react'
import { supabase, DailySummary, ReviewEvent } from '@/lib/supabase'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
} from 'recharts'

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042']

export default function Dashboard() {
  const [dailyStats, setDailyStats] = useState<DailySummary[]>([])
  const [recentReviews, setRecentReviews] = useState<ReviewEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [totalCost, setTotalCost] = useState(0)
  const [totalReviews, setTotalReviews] = useState(0)

  useEffect(() => {
    async function fetchData() {
      // Fetch daily summary
      const { data: daily } = await supabase
        .from('daily_review_summary')
        .select('*')
        .order('review_date', { ascending: false })
        .limit(30)

      if (daily) {
        setDailyStats(daily.reverse())
        setTotalCost(daily.reduce((sum, d) => sum + (d.total_cost || 0), 0))
        setTotalReviews(daily.reduce((sum, d) => sum + d.total_reviews, 0))
      }

      // Fetch recent reviews
      const { data: reviews } = await supabase
        .from('review_events')
        .select('*')
        .order('created_at', { ascending: false })
        .limit(10)

      if (reviews) {
        setRecentReviews(reviews)
      }

      setLoading(false)
    }

    fetchData()
  }, [])

  if (loading) {
    return <div style={{ padding: 40, textAlign: 'center' }}>Loading...</div>
  }

  // Calculate gate effectiveness
  const gatedCount = dailyStats.reduce((sum, d) => sum + d.gated_reviews, 0)
  const llmCount = dailyStats.reduce((sum, d) => sum + d.llm_reviews, 0)
  const gateData = [
    { name: 'Gated (saved tokens)', value: gatedCount },
    { name: 'LLM Reviews', value: llmCount },
  ]

  return (
    <div style={{ padding: 20, maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 30 }}>
        <div>
          <h1 style={{ margin: 0 }}>PR Review Dashboard</h1>
          <p style={{ color: '#666', margin: '4px 0 0' }}>AI-powered code review metrics</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <a
            href="/costs"
            style={{
              padding: '8px 16px',
              background: '#5319e7',
              color: 'white',
              borderRadius: 6,
              textDecoration: 'none',
              fontSize: 14,
            }}
          >
            Costs →
          </a>
          <a
            href="/queue"
            style={{
              padding: '8px 16px',
              background: '#0366d6',
              color: 'white',
              borderRadius: 6,
              textDecoration: 'none',
              fontSize: 14,
            }}
          >
            Review Queue →
          </a>
        </div>
      </div>

      {/* Summary Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 20, marginBottom: 30 }}>
        <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <div style={{ color: '#666', fontSize: 14 }}>Total Reviews</div>
          <div style={{ fontSize: 32, fontWeight: 'bold' }}>{totalReviews}</div>
        </div>
        <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <div style={{ color: '#666', fontSize: 14 }}>Total Cost</div>
          <div style={{ fontSize: 32, fontWeight: 'bold' }}>${totalCost.toFixed(2)}</div>
        </div>
        <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <div style={{ color: '#666', fontSize: 14 }}>Tokens Saved</div>
          <div style={{ fontSize: 32, fontWeight: 'bold' }}>{gatedCount}</div>
          <div style={{ color: '#666', fontSize: 12 }}>reviews gated</div>
        </div>
        <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <div style={{ color: '#666', fontSize: 14 }}>Avg Confidence</div>
          <div style={{ fontSize: 32, fontWeight: 'bold' }}>
            {dailyStats.length > 0
              ? (dailyStats.reduce((sum, d) => sum + (d.avg_confidence || 0), 0) / dailyStats.length * 100).toFixed(0)
              : 0}%
          </div>
        </div>
      </div>

      {/* Charts Row */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 20, marginBottom: 30 }}>
        {/* Reviews Over Time */}
        <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <h3 style={{ marginTop: 0 }}>Reviews Over Time</h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={dailyStats}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="review_date" tickFormatter={(v) => new Date(v).toLocaleDateString()} />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="total_reviews" stroke="#0088FE" name="Total" />
              <Line type="monotone" dataKey="llm_reviews" stroke="#00C49F" name="LLM" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Gate Effectiveness */}
        <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <h3 style={{ marginTop: 0 }}>Gate Effectiveness</h3>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie
                data={gateData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={80}
                label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
              >
                {gateData.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Cost Over Time */}
      <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)', marginBottom: 30 }}>
        <h3 style={{ marginTop: 0 }}>Daily Cost</h3>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={dailyStats}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="review_date" tickFormatter={(v) => new Date(v).toLocaleDateString()} />
            <YAxis tickFormatter={(v) => `$${v.toFixed(2)}`} />
            <Tooltip formatter={(v: number) => `$${v.toFixed(4)}`} />
            <Bar dataKey="total_cost" fill="#8884d8" name="Cost" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Recent Reviews Table */}
      <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
        <h3 style={{ marginTop: 0 }}>Recent Reviews</h3>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #eee' }}>
              <th style={{ textAlign: 'left', padding: 10 }}>PR</th>
              <th style={{ textAlign: 'left', padding: 10 }}>Author</th>
              <th style={{ textAlign: 'left', padding: 10 }}>Outcome</th>
              <th style={{ textAlign: 'right', padding: 10 }}>Confidence</th>
              <th style={{ textAlign: 'right', padding: 10 }}>Cost</th>
            </tr>
          </thead>
          <tbody>
            {recentReviews.map((review) => (
              <tr key={review.id} style={{ borderBottom: '1px solid #eee' }}>
                <td style={{ padding: 10 }}>
                  <a href={review.pr_url} target="_blank" rel="noopener noreferrer">
                    {review.repo_name}#{review.pr_number}
                  </a>
                </td>
                <td style={{ padding: 10 }}>{review.pr_author}</td>
                <td style={{ padding: 10 }}>
                  <span style={{
                    background: review.outcome === 'approved' ? '#d4edda' :
                               review.outcome === 'escalated' ? '#f8d7da' : '#fff3cd',
                    padding: '2px 8px',
                    borderRadius: 4,
                    fontSize: 12,
                  }}>
                    {review.outcome || 'gated'}
                  </span>
                </td>
                <td style={{ textAlign: 'right', padding: 10 }}>
                  {review.confidence_score ? `${(review.confidence_score * 100).toFixed(0)}%` : '-'}
                </td>
                <td style={{ textAlign: 'right', padding: 10 }}>
                  {review.cost_usd ? `$${review.cost_usd.toFixed(4)}` : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
