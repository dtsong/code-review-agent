'use client'

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  BarChart,
  Bar,
} from 'recharts'

import type { EvalRun, EvalIssueBreakdown } from '@/lib/supabase'

export function PrecisionRecallChart({ data }: { data: EvalRun[] }) {
  const chartData = data.map((run) => ({
    date: new Date(run.created_at).toLocaleDateString(),
    precision: +(run.precision * 100).toFixed(1),
    recall: +(run.recall * 100).toFixed(1),
    f1: +(run.f1_score * 100).toFixed(1),
    model: run.model_used,
  }))

  return (
    <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
      <h3 style={{ marginTop: 0 }}>Precision / Recall / F1 Over Time</h3>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" />
          <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
          <Tooltip formatter={(v: number) => `${v}%`} />
          <Legend />
          <Line type="monotone" dataKey="precision" stroke="#0088FE" name="Precision" strokeWidth={2} />
          <Line type="monotone" dataKey="recall" stroke="#00C49F" name="Recall" strokeWidth={2} />
          <Line type="monotone" dataKey="f1" stroke="#FF8042" name="F1" strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export function CostEfficiencyChart({ data }: { data: EvalRun[] }) {
  const chartData = data.map((run) => ({
    date: new Date(run.created_at).toLocaleDateString(),
    costPerCase: +(run.avg_cost_usd * 1000).toFixed(2),
    f1: +(run.f1_score * 100).toFixed(1),
    model: run.model_used,
  }))

  return (
    <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
      <h3 style={{ marginTop: 0 }}>Cost Efficiency (Cost per Case vs F1)</h3>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" />
          <YAxis yAxisId="cost" orientation="left" tickFormatter={(v) => `$${v}`} />
          <YAxis yAxisId="f1" orientation="right" domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
          <Tooltip />
          <Legend />
          <Line yAxisId="cost" type="monotone" dataKey="costPerCase" stroke="#8884d8" name="Cost/Case (x1000)" strokeWidth={2} />
          <Line yAxisId="f1" type="monotone" dataKey="f1" stroke="#FF8042" name="F1 %" strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export function IssueCategoryChart({ data }: { data: EvalIssueBreakdown[] }) {
  const chartData = data.map((item) => ({
    category: item.category,
    precision: +(item.precision * 100).toFixed(1),
    recall: +(item.recall * 100).toFixed(1),
    tp: item.true_positives,
    fp: item.false_positives,
    fn: item.false_negatives,
  }))

  return (
    <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
      <h3 style={{ marginTop: 0 }}>Performance by Issue Category</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={chartData} layout="vertical">
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis type="number" domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
          <YAxis type="category" dataKey="category" width={120} />
          <Tooltip formatter={(v: number) => `${v}%`} />
          <Legend />
          <Bar dataKey="precision" fill="#0088FE" name="Precision" />
          <Bar dataKey="recall" fill="#00C49F" name="Recall" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function ConfidenceCalibrationChart({ data }: { data: EvalRun[] }) {
  const chartData = data.map((run) => ({
    date: new Date(run.created_at).toLocaleDateString(),
    avgConfidence: +(run.avg_confidence * 100).toFixed(1),
    accuracy: +(run.precision * 100).toFixed(1),
  }))

  return (
    <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
      <h3 style={{ marginTop: 0 }}>Confidence Calibration</h3>
      <p style={{ color: '#666', fontSize: 13, margin: '0 0 10px' }}>
        Ideally confidence should track accuracy closely.
      </p>
      <ResponsiveContainer width="100%" height={250}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" />
          <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
          <Tooltip formatter={(v: number) => `${v}%`} />
          <Legend />
          <Line type="monotone" dataKey="avgConfidence" stroke="#FFBB28" name="Avg Confidence" strokeWidth={2} />
          <Line type="monotone" dataKey="accuracy" stroke="#0088FE" name="Accuracy (Precision)" strokeWidth={2} strokeDasharray="5 5" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
