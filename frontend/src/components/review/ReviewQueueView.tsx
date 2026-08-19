import React, { useEffect, useState, useCallback } from 'react'
import { ReviewQueueHeader } from './ReviewQueueHeader'
import { ReviewQueueList } from './ReviewQueueList'
import { ExtractionReviewModal } from './ExtractionReviewModal'
import { BookkeepingReviewModal } from './BookkeepingReviewModal'
import { ReconciliationReviewModal } from './ReconciliationReviewModal'
import type { ReviewItemResponse } from '../../services/api'
import { fetchReviewItems, notifyReviewQueueUpdated } from '../../services/api'

interface ReviewQueueViewProps {
  onInspectItem?: (item: ReviewItemResponse) => void
}

export const ReviewQueueView: React.FC<ReviewQueueViewProps> = ({ onInspectItem }) => {
  const [items, setItems] = useState<ReviewItemResponse[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [statusFilter, setStatusFilter] = useState<string>('pending')
  const [typeFilter, setTypeFilter] = useState<string>('')
  const [selectedItem, setSelectedItem] = useState<ReviewItemResponse | null>(null)

  const loadReviewItems = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetchReviewItems({
        status: statusFilter || undefined,
        review_type: typeFilter || undefined,
        limit: 50,
      })
      setItems(res.items)
    } catch (err: unknown) {
      console.error('Failed to load review queue items:', err)
    } finally {
      setLoading(false)
    }
  }, [statusFilter, typeFilter])

  useEffect(() => {
    loadReviewItems()

    const handleExternalUpdate = () => {
      loadReviewItems()
    }
    window.addEventListener('review-queue-updated', handleExternalUpdate)
    return () => {
      window.removeEventListener('review-queue-updated', handleExternalUpdate)
    }
  }, [loadReviewItems])

  const handleInspect = (item: ReviewItemResponse) => {
    setSelectedItem(item)
    if (onInspectItem) {
      onInspectItem(item)
    }
  }

  const pendingCount = items.filter((i) => i.status === 'pending').length
  const highPriorityCount = items.filter(
    (i) => i.priority === 'high' && i.status === 'pending'
  ).length
  const approvedCount = items.filter((i) => i.status === 'posted' || i.status === 'approved').length

  const isBookkeepingItem = selectedItem?.review_type === 'bookkeeping'
  const isReconciliationItem = selectedItem?.review_type === 'reconciliation'

  const handleResolved = () => {
    loadReviewItems()
    notifyReviewQueueUpdated()
  }

  return (
    <div className="space-y-6">
      {/* Header Statistics */}
      <ReviewQueueHeader
        pendingCount={pendingCount}
        highPriorityCount={highPriorityCount}
        approvedCount={approvedCount}
      />

      {/* Main Review Queue Dashboard */}
      <ReviewQueueList
        items={items}
        loading={loading}
        onRefresh={loadReviewItems}
        onInspectItem={handleInspect}
        statusFilter={statusFilter}
        onStatusFilterChange={setStatusFilter}
        typeFilter={typeFilter}
        onTypeFilterChange={setTypeFilter}
      />

      {/* Reconciliation Review Modal — for reconciliation type items */}
      {selectedItem && isReconciliationItem && (
        <ReconciliationReviewModal
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
          onResolved={handleResolved}
        />
      )}

      {/* Bookkeeping Review Modal — for bookkeeping type items */}
      {selectedItem && isBookkeepingItem && (
        <BookkeepingReviewModal
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
          onResolved={handleResolved}
        />
      )}

      {/* Extraction Review Modal — for extraction / other types */}
      {selectedItem && !isBookkeepingItem && !isReconciliationItem && (
        <ExtractionReviewModal
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
          onResolved={handleResolved}
        />
      )}
    </div>
  )
}

