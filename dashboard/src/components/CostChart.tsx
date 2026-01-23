'use client'

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line,
} from 'recharts'

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8', '#82ca9d']

interface DailyCost {
  date: string
  cost: number
  reviews: number
}

interface RepoCost {
  name: string
  cost: number
  reviews: number
}

interface ModelCost {
  model: string
  cost: number
  tokens: number
}

export function CostTrendChart({ data }: { data: DailyCost[] }) {
  return (
    <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
      <h3 style={{ marginTop: 0 }}>Cost Over Time</h3>
      <ResponsiveContainer width="100%" height={250}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="date"
            tickFormatter={(v) => new Date(v).toLocaleDateString()}
          />
          <YAxis tickFormatter={(v) => `$${v.toFixed(2)}`} />
          <Tooltip
            formatter={(v: number) => `$${v.toFixed(4)}`}
            labelFormatter={(v) => new Date(v).toLocaleDateString()}
          />
          <Line type="monotone" dataKey="cost" stroke="#8884d8" name="Daily Cost" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export function CostPerReviewChart({ data }: { data: DailyCost[] }) {
  const perReview = data
    .filter((d) => d.reviews > 0)
    .map((d) => ({
      date: d.date,
      costPerReview: d.cost / d.reviews,
    }))

  return (
    <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
      <h3 style={{ marginTop: 0 }}>Cost Per Review</h3>
      <ResponsiveContainer width="100%" height={250}>
        <LineChart data={perReview}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="date"
            tickFormatter={(v) => new Date(v).toLocaleDateString()}
          />
          <YAxis tickFormatter={(v) => `$${v.toFixed(3)}`} />
          <Tooltip
            formatter={(v: number) => `$${v.toFixed(4)}`}
            labelFormatter={(v) => new Date(v).toLocaleDateString()}
          />
          <Line type="monotone" dataKey="costPerReview" stroke="#00C49F" name="Cost/Review" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export function CostByRepoChart({ data }: { data: RepoCost[] }) {
  return (
    <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
      <h3 style={{ marginTop: 0 }}>Cost by Repository</h3>
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={data} layout="vertical">
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis type="number" tickFormatter={(v) => `$${v.toFixed(2)}`} />
          <YAxis type="category" dataKey="name" width={120} />
          <Tooltip formatter={(v: number) => `$${v.toFixed(4)}`} />
          <Bar dataKey="cost" fill="#0088FE" name="Total Cost" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function CostByModelChart({ data }: { data: ModelCost[] }) {
  return (
    <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
      <h3 style={{ marginTop: 0 }}>Cost by Model</h3>
      <ResponsiveContainer width="100%" height={250}>
        <PieChart>
          <Pie
            data={data}
            dataKey="cost"
            nameKey="model"
            cx="50%"
            cy="50%"
            outerRadius={80}
            label={({ model, percent }) =>
              `${model.split('-').slice(1, 2).join('')}: ${(percent * 100).toFixed(0)}%`
            }
          >
            {data.map((_, index) => (
              <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip formatter={(v: number) => `$${v.toFixed(4)}`} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}

export function OutliersTable({ reviews }: { reviews: { pr_title: string; pr_url: string; repo_name: string; cost_usd: number; model_used: string }[] }) {
  return (
    <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
      <h3 style={{ marginTop: 0 }}>Expensive Reviews (Outliers)</h3>
      {reviews.length === 0 ? (
        <p style={{ color: '#666' }}>No outliers detected.</p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #eee' }}>
              <th style={{ textAlign: 'left', padding: 8 }}>PR</th>
              <th style={{ textAlign: 'left', padding: 8 }}>Model</th>
              <th style={{ textAlign: 'right', padding: 8 }}>Cost</th>
            </tr>
          </thead>
          <tbody>
            {reviews.map((r, i) => (
              <tr key={i} style={{ borderBottom: '1px solid #eee' }}>
                <td style={{ padding: 8 }}>
                  <a href={r.pr_url} target="_blank" rel="noopener noreferrer" style={{ color: '#0366d6' }}>
                    {r.repo_name}: {r.pr_title}
                  </a>
                </td>
                <td style={{ padding: 8, fontSize: 13 }}>{r.model_used}</td>
                <td style={{ textAlign: 'right', padding: 8, fontWeight: 'bold' }}>
                  ${r.cost_usd.toFixed(4)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
