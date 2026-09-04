import React, { useEffect, useState, useCallback } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { ReviewQueueHeader } from './ReviewQueueHeader'
import { ReviewQueueList } from './ReviewQueueList'
import { ExtractionReviewModal } from './ExtractionReviewModal'
import { BookkeepingReviewModal } from './BookkeepingReviewModal'
import { ReconciliationReviewModal } from './ReconciliationReviewModal'
import type { ReviewItemResponse } from '../../services/api'
import {
  fetchReviewItemDetail,
  fetchReviewItems,
  notifyReviewQueueUpdated,
} from '../../services/api'

interface ReviewQueueViewProps {
  onInspectItem?: (item: ReviewItemResponse) => void
}

export const ReviewQueueView: React.FC<ReviewQueueViewProps> = ({ onInspectItem }) => {
  const { reviewItemId } = useParams<{ reviewItemId: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const [items, setItems] = useState<ReviewItemResponse[]>([])
  const [total, setTotal] = useState<number>(0)
  const [loading, setLoading] = useState<boolean>(true)
  const [statusFilter, setStatusFilter] = useState<string>('pending')
  const [typeFilter, setTypeFilter] = useState<string>('')
  const [searchTerm, setSearchTerm] = useState<string>('')
  const [page, setPage] = useState<number>(1)
  const [pageSize, setPageSize] = useState<number>(10)
  const [selectedItem, setSelectedItem] = useState<ReviewItemResponse | null>(null)
  const [detailLoading, setDetailLoading] = useState<boolean>(false)
  const [detailError, setDetailError] = useState<string | null>(null)

  // Header statistics state
  const [pendingCount, setPendingCount] = useState<number>(0)
  const [highPriorityCount, setHighPriorityCount] = useState<number>(0)
  const [approvedCount, setApprovedCount] = useState<number>(0)

  const loadReviewItems = useCallback(async () => {
    setLoading(true)
    try {
      const [res, pendingRes, highRes, approvedRes] = await Promise.all([
        fetchReviewItems({
          status: statusFilter || undefined,
          review_type: typeFilter || undefined,
          search: searchTerm.trim() || undefined,
          limit: pageSize,
          offset: (page - 1) * pageSize,
        }),
        fetchReviewItems({ status: 'pending', limit: 1 }),
        fetchReviewItems({ status: 'pending', priority: 'high', limit: 1 }),
        fetchReviewItems({ resolved_today: true, limit: 1 }),
      ])
      setItems(res.items)
      setTotal(res.total)
      setPendingCount(pendingRes.total)
      setHighPriorityCount(highRes.total)
      setApprovedCount(approvedRes.total)
    } catch (err: unknown) {
      console.error('Failed to load review queue items:', err)
    } finally {
      setLoading(false)
    }
  }, [statusFilter, typeFilter, searchTerm, page, pageSize])

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

  useEffect(() => {
    if (!reviewItemId) {
      setSelectedItem(null)
      setDetailLoading(false)
      setDetailError(null)
      return
    }

    let cancelled = false
    setDetailLoading(true)
    setSelectedItem(null)
    fetchReviewItemDetail(reviewItemId)
      .then((item) => {
        if (!cancelled) {
          setSelectedItem(item)
          setDetailError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setSelectedItem(null)
          setDetailError(err instanceof Error ? err.message : 'Failed to load review item')
        }
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [reviewItemId])

  const handleInspect = (item: ReviewItemResponse) => {
    setDetailError(null)
    if (reviewItemId !== item.id) {
      setSelectedItem(null)
      setDetailLoading(true)
      navigate(`/review/${item.id}`, { state: { fromReviewQueue: true } })
    } else {
      setSelectedItem(item)
      setDetailLoading(false)
    }
    if (onInspectItem) {
      onInspectItem(item)
    }
  }

  const handleCloseDetail = () => {
    if (location.state?.fromReviewQueue) {
      navigate(-1)
    } else {
      navigate('/review', { replace: true })
    }
  }

  const handleStatusFilterChange = (newStatus: string) => {
    setStatusFilter(newStatus)
    setPage(1)
  }

  const handleTypeFilterChange = (newType: string) => {
    setTypeFilter(newType)
    setPage(1)
  }

  const handleSearchChange = (newSearch: string) => {
    setSearchTerm(newSearch)
    setPage(1)
  }

  const isBookkeepingItem = selectedItem?.review_type === 'bookkeeping'
  const isReconciliationItem = selectedItem?.review_type === 'reconciliation'

  const handleResolved = () => {
    loadReviewItems()
    notifyReviewQueueUpdated()
  }

  return (
    <div className="space-y-6">
      {detailError && (
        <div className="rounded-xl border border-red-500/30 bg-red-950/30 p-4 text-sm text-red-300">
          {detailError}{' '}
          <button
            type="button"
            onClick={() => navigate('/review', { replace: true })}
            className="font-semibold text-red-200 underline underline-offset-2"
          >
            Back to Review Queue
          </button>
        </div>
      )}
      {/* Header Statistics */}
      <ReviewQueueHeader
        pendingCount={pendingCount}
        highPriorityCount={highPriorityCount}
        approvedCount={approvedCount}
      />

      {/* Main Review Queue Dashboard */}
      <ReviewQueueList
        items={items}
        total={total}
        loading={loading}
        onRefresh={loadReviewItems}
        onInspectItem={handleInspect}
        statusFilter={statusFilter}
        onStatusFilterChange={handleStatusFilterChange}
        typeFilter={typeFilter}
        onTypeFilterChange={handleTypeFilterChange}
        searchTerm={searchTerm}
        onSearchChange={handleSearchChange}
        page={page}
        pageSize={pageSize}
        onPageChange={setPage}
        onPageSizeChange={(newSize) => {
          setPageSize(newSize)
          setPage(1)
        }}
      />

      {detailLoading && (
        <div className="fixed inset-0 z-50 bg-slate-950/85 backdrop-blur-md flex items-center justify-center p-4">
          <div className="rounded-2xl border border-slate-700/80 bg-slate-900 px-8 py-10 text-center shadow-2xl">
            <Loader2 className="mx-auto mb-3 h-8 w-8 animate-spin text-indigo-400" />
            <p className="text-sm font-semibold text-slate-200">Loading review detail...</p>
          </div>
        </div>
      )}

      {/* Reconciliation Review Modal — for reconciliation type items */}
      {selectedItem && isReconciliationItem && (
        <ReconciliationReviewModal
          item={selectedItem}
          onClose={handleCloseDetail}
          onResolved={handleResolved}
        />
      )}

      {/* Bookkeeping Review Modal — for bookkeeping type items */}
      {selectedItem && isBookkeepingItem && (
        <BookkeepingReviewModal
          item={selectedItem}
          onClose={handleCloseDetail}
          onResolved={handleResolved}
        />
      )}

      {/* Extraction Review Modal — for extraction / other types */}
      {selectedItem && !isBookkeepingItem && !isReconciliationItem && (
        <ExtractionReviewModal
          item={selectedItem}
          onClose={handleCloseDetail}
          onResolved={handleResolved}
        />
      )}
    </div>
  )
}
