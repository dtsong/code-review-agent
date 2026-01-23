'use client'

import { useEffect, useState } from 'react'
import { supabase, EscalatedReview } from '@/lib/supabase'
import ReviewQueue from '@/components/ReviewQueue'

export default function QueuePage() {
  const [reviews, setReviews] = useState<EscalatedReview[]>([])
  const [loading, setLoading] = useState(true)

  async function fetchEscalated() {
    const { data } = await supabase
      .from('review_events')
      .select('*')
      .eq('escalated_to_human', true)
      .eq('outcome', 'escalated')
      .order('created_at', { ascending: false })
      .limit(50)

    if (data) {
      setReviews(data)
    }
    setLoading(false)
  }

  useEffect(() => {
    fetchEscalated()
  }, [])

  async function handleAction(id: string, action: 'approve' | 'override' | 'dismiss') {
    const outcomeMap = {
      approve: 'approved',
      override: 'overridden',
      dismiss: 'dismissed',
    }

    await supabase
      .from('review_events')
      .update({ outcome: outcomeMap[action] })
      .eq('id', id)

    // Remove from local state
    setReviews((prev) => prev.filter((r) => r.id !== id))
  }

  if (loading) {
    return <div style={{ padding: 40, textAlign: 'center' }}>Loading...</div>
  }

  return (
    <div style={{ padding: 20, maxWidth: 900, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div>
          <h1 style={{ margin: 0 }}>Review Queue</h1>
          <p style={{ color: '#666', margin: '4px 0 0' }}>
            Escalated reviews pending human action
          </p>
        </div>
        <a href="/" style={{ color: '#0366d6', textDecoration: 'none' }}>
          ← Dashboard
        </a>
      </div>

      <div style={{
        background: '#e8f4fd',
        padding: 12,
        borderRadius: 6,
        marginBottom: 20,
        fontSize: 14,
      }}>
        {reviews.length} review(s) pending action
      </div>

      <ReviewQueue reviews={reviews} onAction={handleAction} />
    </div>
  )
}
