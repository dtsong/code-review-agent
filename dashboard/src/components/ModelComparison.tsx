'use client'

import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  BarChart,
  Bar,
} from 'recharts'

import type { EvalRun } from '@/lib/supabase'

interface ModelStats {
  model: string
  avgF1: number
  avgCost: number
  avgLatency: number
  runs: number
}

function aggregateByModel(data: EvalRun[]): ModelStats[] {
  const grouped: Record<string, EvalRun[]> = {}
  for (const run of data) {
    const model = run.model_used
    if (!grouped[model]) grouped[model] = []
    grouped[model].push(run)
  }

  return Object.entries(grouped).map(([model, runs]) => ({
    model,
    avgF1: runs.reduce((s, r) => s + r.f1_score, 0) / runs.length,
    avgCost: runs.reduce((s, r) => s + r.avg_cost_usd, 0) / runs.length,
    avgLatency: runs.reduce((s, r) => s + r.total_duration_ms, 0) / runs.length / runs[0].total_cases,
    runs: runs.length,
  }))
}

export function QualityVsCostChart({ data }: { data: EvalRun[] }) {
  const models = aggregateByModel(data)
  const chartData = models.map((m) => ({
    model: m.model,
    f1: +(m.avgF1 * 100).toFixed(1),
    cost: +(m.avgCost * 1000).toFixed(3),
    runs: m.runs,
  }))

  return (
    <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
      <h3 style={{ marginTop: 0 }}>Quality vs Cost by Model</h3>
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis type="number" dataKey="cost" name="Cost" tickFormatter={(v) => `$${v}`} label={{ value: 'Avg Cost/Case (x1000)', position: 'bottom' }} />
          <YAxis type="number" dataKey="f1" name="F1" domain={[0, 100]} tickFormatter={(v) => `${v}%`} label={{ value: 'F1 %', angle: -90, position: 'left' }} />
          <Tooltip
            formatter={(value: number, name: string) =>
              name === 'Cost' ? `$${(value / 1000).toFixed(5)}` : `${value}%`
            }
            labelFormatter={() => ''}
            content={({ payload }) => {
              if (!payload || payload.length === 0) return null
              const d = payload[0].payload
              return (
                <div style={{ background: 'white', border: '1px solid #ccc', padding: 8, borderRadius: 4, fontSize: 13 }}>
                  <strong>{d.model}</strong><br />
                  F1: {d.f1}%<br />
                  Cost/Case: ${(d.cost / 1000).toFixed(5)}<br />
                  Runs: {d.runs}
                </div>
              )
            }}
          />
          <Scatter data={chartData} fill="#8884d8" />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}

export function ModelComparisonBar({ data }: { data: EvalRun[] }) {
  const models = aggregateByModel(data)
  const chartData = models.map((m) => ({
    model: m.model.replace('claude-', '').replace('anthropic.', ''),
    precision: +(
      (data.filter((r) => r.model_used === m.model).reduce((s, r) => s + r.precision, 0) /
        data.filter((r) => r.model_used === m.model).length) *
      100
    ).toFixed(1),
    recall: +(
      (data.filter((r) => r.model_used === m.model).reduce((s, r) => s + r.recall, 0) /
        data.filter((r) => r.model_used === m.model).length) *
      100
    ).toFixed(1),
    f1: +(m.avgF1 * 100).toFixed(1),
  }))

  return (
    <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
      <h3 style={{ marginTop: 0 }}>Model Performance Comparison</h3>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="model" />
          <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
          <Tooltip formatter={(v: number) => `${v}%`} />
          <Legend />
          <Bar dataKey="precision" fill="#0088FE" name="Precision" />
          <Bar dataKey="recall" fill="#00C49F" name="Recall" />
          <Bar dataKey="f1" fill="#FF8042" name="F1" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function ModelSummaryTable({ data }: { data: EvalRun[] }) {
  const models = aggregateByModel(data)

  return (
    <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
      <h3 style={{ marginTop: 0 }}>Model Summary</h3>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: '2px solid #eee' }}>
            <th style={{ textAlign: 'left', padding: 10 }}>Model</th>
            <th style={{ textAlign: 'right', padding: 10 }}>F1</th>
            <th style={{ textAlign: 'right', padding: 10 }}>Avg Cost</th>
            <th style={{ textAlign: 'right', padding: 10 }}>Avg Latency</th>
            <th style={{ textAlign: 'right', padding: 10 }}>Runs</th>
            <th style={{ textAlign: 'left', padding: 10 }}>Recommendation</th>
          </tr>
        </thead>
        <tbody>
          {models
            .sort((a, b) => b.avgF1 - a.avgF1)
            .map((m) => {
              const efficiency = m.avgF1 / (m.avgCost || 0.001)
              const bestEfficiency = Math.max(...models.map((x) => x.avgF1 / (x.avgCost || 0.001)))
              const recommendation =
                m.avgF1 === Math.max(...models.map((x) => x.avgF1))
                  ? 'Best quality'
                  : efficiency >= bestEfficiency * 0.9
                    ? 'Best value'
                    : 'Consider alternatives'

              return (
                <tr key={m.model} style={{ borderBottom: '1px solid #eee' }}>
                  <td style={{ padding: 10, fontFamily: 'monospace', fontSize: 13 }}>{m.model}</td>
                  <td style={{ textAlign: 'right', padding: 10, fontWeight: 'bold' }}>
                    {(m.avgF1 * 100).toFixed(1)}%
                  </td>
                  <td style={{ textAlign: 'right', padding: 10 }}>
                    ${m.avgCost.toFixed(4)}
                  </td>
                  <td style={{ textAlign: 'right', padding: 10 }}>
                    {(m.avgLatency / 1000).toFixed(1)}s
                  </td>
                  <td style={{ textAlign: 'right', padding: 10 }}>{m.runs}</td>
                  <td style={{ padding: 10 }}>
                    <span
                      style={{
                        background:
                          recommendation === 'Best quality'
                            ? '#d4edda'
                            : recommendation === 'Best value'
                              ? '#cce5ff'
                              : '#fff3cd',
                        padding: '2px 8px',
                        borderRadius: 4,
                        fontSize: 12,
                      }}
                    >
                      {recommendation}
                    </span>
                  </td>
                </tr>
              )
            })}
        </tbody>
      </table>
    </div>
  )
}
