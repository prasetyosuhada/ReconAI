import React, { useEffect, useState } from 'react'
import { ReviewQueueHeader } from './ReviewQueueHeader'
import { ReviewQueueList } from './ReviewQueueList'
import { ReviewDetailModal } from './ReviewDetailModal'
import type { ReviewItemResponse } from '../../services/api'
import { fetchReviewItems } from '../../services/api'

interface ReviewQueueViewProps {
  onInspectItem?: (item: ReviewItemResponse) => void
}

export const ReviewQueueView: React.FC<ReviewQueueViewProps> = ({ onInspectItem }) => {
  const [items, setItems] = useState<ReviewItemResponse[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [statusFilter, setStatusFilter] = useState<string>('pending')
  const [typeFilter, setTypeFilter] = useState<string>('')
  const [selectedItem, setSelectedItem] = useState<ReviewItemResponse | null>(null)

  const loadReviewItems = async () => {
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
  }

  useEffect(() => {
    loadReviewItems()
  }, [statusFilter, typeFilter])

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
  const approvedCount = items.filter((i) => i.status === 'posted').length

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

      {/* Review Detail Modal */}
      {selectedItem && (
        <ReviewDetailModal
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
          onResolved={() => loadReviewItems()}
        />
      )}
    </div>
  )
}
