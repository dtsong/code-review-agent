'use client'

import { useEffect, useState } from 'react'
import { supabase, EvalRun, EvalIssueBreakdown } from '@/lib/supabase'
import {
  PrecisionRecallChart,
  CostEfficiencyChart,
  IssueCategoryChart,
  ConfidenceCalibrationChart,
} from '@/components/EvalChart'
import {
  QualityVsCostChart,
  ModelComparisonBar,
  ModelSummaryTable,
} from '@/components/ModelComparison'

type FilterModel = string | 'all'
type FilterSuite = string | 'all'

export default function EvalsPage() {
  const [evalRuns, setEvalRuns] = useState<EvalRun[]>([])
  const [issueBreakdown, setIssueBreakdown] = useState<EvalIssueBreakdown[]>([])
  const [loading, setLoading] = useState(true)
  const [filterModel, setFilterModel] = useState<FilterModel>('all')
  const [filterSuite, setFilterSuite] = useState<FilterSuite>('all')
  const [sortField, setSortField] = useState<keyof EvalRun>('created_at')
  const [sortDesc, setSortDesc] = useState(true)

  useEffect(() => {
    async function fetchData() {
      const { data: runs } = await supabase
        .from('eval_runs')
        .select('*')
        .order('created_at', { ascending: false })
        .limit(100)

      if (runs) setEvalRuns(runs)

      const { data: breakdown } = await supabase
        .from('eval_issue_breakdown')
        .select('*')

      if (breakdown) setIssueBreakdown(breakdown)

      setLoading(false)
    }

    fetchData()
  }, [])

  if (loading) {
    return <div style={{ padding: 40, textAlign: 'center' }}>Loading...</div>
  }

  const models = Array.from(new Set(evalRuns.map((r) => r.model_used)))
  const suites = Array.from(new Set(evalRuns.map((r) => r.eval_suite)))

  const filtered = evalRuns.filter((r) => {
    if (filterModel !== 'all' && r.model_used !== filterModel) return false
    if (filterSuite !== 'all' && r.eval_suite !== filterSuite) return false
    return true
  })

  const sorted = [...filtered].sort((a, b) => {
    const aVal = a[sortField]
    const bVal = b[sortField]
    if (typeof aVal === 'number' && typeof bVal === 'number') {
      return sortDesc ? bVal - aVal : aVal - bVal
    }
    return sortDesc
      ? String(bVal).localeCompare(String(aVal))
      : String(aVal).localeCompare(String(bVal))
  })

  const handleSort = (field: keyof EvalRun) => {
    if (sortField === field) {
      setSortDesc(!sortDesc)
    } else {
      setSortField(field)
      setSortDesc(true)
    }
  }

  const avgF1 = filtered.length > 0
    ? filtered.reduce((s, r) => s + r.f1_score, 0) / filtered.length
    : 0
  const avgPrecision = filtered.length > 0
    ? filtered.reduce((s, r) => s + r.precision, 0) / filtered.length
    : 0
  const avgRecall = filtered.length > 0
    ? filtered.reduce((s, r) => s + r.recall, 0) / filtered.length
    : 0
  const totalCost = filtered.reduce((s, r) => s + r.avg_cost_usd * r.total_cases, 0)

  return (
    <div style={{ padding: 20, maxWidth: 1400, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 30 }}>
        <div>
          <h1 style={{ margin: 0 }}>Eval Insights</h1>
          <p style={{ color: '#666', margin: '4px 0 0' }}>Evaluation performance, trends, and model comparison</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <a
            href="/"
            style={{
              padding: '8px 16px',
              background: '#24292e',
              color: 'white',
              borderRadius: 6,
              textDecoration: 'none',
              fontSize: 14,
            }}
          >
            Dashboard
          </a>
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
            Costs
          </a>
        </div>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>
        <div>
          <label style={{ fontSize: 13, color: '#666', display: 'block', marginBottom: 4 }}>Model</label>
          <select
            value={filterModel}
            onChange={(e) => setFilterModel(e.target.value)}
            style={{ padding: '6px 12px', borderRadius: 4, border: '1px solid #ccc', fontSize: 14 }}
          >
            <option value="all">All Models</option>
            {models.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>
        <div>
          <label style={{ fontSize: 13, color: '#666', display: 'block', marginBottom: 4 }}>Eval Suite</label>
          <select
            value={filterSuite}
            onChange={(e) => setFilterSuite(e.target.value)}
            style={{ padding: '6px 12px', borderRadius: 4, border: '1px solid #ccc', fontSize: 14 }}
          >
            <option value="all">All Suites</option>
            {suites.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Summary Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 16, marginBottom: 30 }}>
        <div style={{ background: 'white', padding: 16, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <div style={{ color: '#666', fontSize: 13 }}>Eval Runs</div>
          <div style={{ fontSize: 28, fontWeight: 'bold' }}>{filtered.length}</div>
        </div>
        <div style={{ background: 'white', padding: 16, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <div style={{ color: '#666', fontSize: 13 }}>Avg F1</div>
          <div style={{ fontSize: 28, fontWeight: 'bold' }}>{(avgF1 * 100).toFixed(1)}%</div>
        </div>
        <div style={{ background: 'white', padding: 16, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <div style={{ color: '#666', fontSize: 13 }}>Avg Precision</div>
          <div style={{ fontSize: 28, fontWeight: 'bold' }}>{(avgPrecision * 100).toFixed(1)}%</div>
        </div>
        <div style={{ background: 'white', padding: 16, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <div style={{ color: '#666', fontSize: 13 }}>Avg Recall</div>
          <div style={{ fontSize: 28, fontWeight: 'bold' }}>{(avgRecall * 100).toFixed(1)}%</div>
        </div>
        <div style={{ background: 'white', padding: 16, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <div style={{ color: '#666', fontSize: 13 }}>Total Eval Cost</div>
          <div style={{ fontSize: 28, fontWeight: 'bold' }}>${totalCost.toFixed(2)}</div>
        </div>
      </div>

      {/* Performance Trends */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 30 }}>
        <PrecisionRecallChart data={filtered} />
        <CostEfficiencyChart data={filtered} />
      </div>

      {/* Calibration and Categories */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 30 }}>
        <ConfidenceCalibrationChart data={filtered} />
        <IssueCategoryChart data={issueBreakdown} />
      </div>

      {/* Model Comparison */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 30 }}>
        <ModelComparisonBar data={filtered} />
        <QualityVsCostChart data={filtered} />
      </div>

      {/* Model Summary Table */}
      <div style={{ marginBottom: 30 }}>
        <ModelSummaryTable data={filtered} />
      </div>

      {/* Eval Run History Table */}
      <div style={{ background: 'white', padding: 20, borderRadius: 8, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
        <h3 style={{ marginTop: 0 }}>Eval Run History</h3>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #eee' }}>
                {[
                  { key: 'created_at', label: 'Date' },
                  { key: 'eval_suite', label: 'Suite' },
                  { key: 'model_used', label: 'Model' },
                  { key: 'f1_score', label: 'F1' },
                  { key: 'precision', label: 'Precision' },
                  { key: 'recall', label: 'Recall' },
                  { key: 'total_cases', label: 'Cases' },
                  { key: 'avg_cost_usd', label: 'Avg Cost' },
                ].map((col) => (
                  <th
                    key={col.key}
                    style={{
                      textAlign: col.key === 'created_at' || col.key === 'eval_suite' || col.key === 'model_used' ? 'left' : 'right',
                      padding: 10,
                      cursor: 'pointer',
                      userSelect: 'none',
                    }}
                    onClick={() => handleSort(col.key as keyof EvalRun)}
                  >
                    {col.label} {sortField === col.key ? (sortDesc ? '▼' : '▲') : ''}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.slice(0, 50).map((run) => (
                <tr key={run.id} style={{ borderBottom: '1px solid #eee' }}>
                  <td style={{ padding: 10 }}>
                    {new Date(run.created_at).toLocaleDateString()}
                  </td>
                  <td style={{ padding: 10 }}>{run.eval_suite}</td>
                  <td style={{ padding: 10, fontFamily: 'monospace', fontSize: 12 }}>{run.model_used}</td>
                  <td style={{ textAlign: 'right', padding: 10, fontWeight: 'bold' }}>
                    {(run.f1_score * 100).toFixed(1)}%
                  </td>
                  <td style={{ textAlign: 'right', padding: 10 }}>
                    {(run.precision * 100).toFixed(1)}%
                  </td>
                  <td style={{ textAlign: 'right', padding: 10 }}>
                    {(run.recall * 100).toFixed(1)}%
                  </td>
                  <td style={{ textAlign: 'right', padding: 10 }}>{run.total_cases}</td>
                  <td style={{ textAlign: 'right', padding: 10 }}>${run.avg_cost_usd.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
