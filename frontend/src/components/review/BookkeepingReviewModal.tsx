import React, { useEffect, useState } from 'react'
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  ShieldAlert,
  Sparkles,
  X,
} from 'lucide-react'
import type { JournalLineEditPayload, ReviewItemResponse } from '../../services/api'
import {
  approveReviewItem,
  editReviewItem,
  fetchReviewItemDetail,
  rejectReviewItem,
} from '../../services/api'
import { BookkeepingJournalPanel, type BookkeepingLine } from '../shared/BookkeepingJournalPanel'

interface BookkeepingReviewModalProps {
  item: ReviewItemResponse | null
  onClose: () => void
  onResolved: () => void
}

const getPayloadLines = (item: ReviewItemResponse | null): BookkeepingLine[] => {
  const payload = item?.original_payload || {}
  return item?.edited_payload?.lines || payload.lines || payload.journal_lines || []
}

export const BookkeepingReviewModal: React.FC<BookkeepingReviewModalProps> = ({
  item,
  onClose,
  onResolved,
}) => {
  const [detailItem, setDetailItem] = useState<ReviewItemResponse | null>(item)
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false)
  const [isEditing, setIsEditing] = useState(false)
  const [lines, setLines] = useState<JournalLineEditPayload[]>([])
  const [rejectionReason, setRejectionReason] = useState('')
  const [showRejectInput, setShowRejectInput] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  useEffect(() => {
    let ignore = false
    setDetailItem(item)
    setErrorMsg(null)
    setIsEditing(false)
    setShowRejectInput(false)
    setRejectionReason('')

    if (!item?.id) return

    setLoadingDetail(true)
    fetchReviewItemDetail(item.id)
      .then((res) => {
        if (!ignore) {
          setDetailItem(res)
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setErrorMsg(err instanceof Error ? err.message : 'Failed to load review detail')
        }
      })
      .finally(() => {
        if (!ignore) {
          setLoadingDetail(false)
        }
      })

    return () => {
      ignore = true
    }
  }, [item])

  const activeItem = detailItem || item
  const payload = activeItem?.original_payload || {}
  const currency: string = payload.currency || 'IDR'
  const vendorName: string = payload.vendor_name || payload.merchant_name || 'Unknown Vendor'
  const transactionDate: string =
    payload.transaction_date || payload.invoice_date || payload.entry_date || ''
  const totalAmount: number = Number(payload.total_amount || payload.amount || 0)
  const rawLineItems: Record<string, any>[] = Array.isArray(payload.line_items)
    ? payload.line_items
    : Array.isArray(payload.items)
      ? payload.items
      : []
  const rationale: string = payload.rationale || activeItem?.summary || 'No AI reasoning provided.'
  const riskFlags: string[] = Array.isArray(payload.risk_flags)
    ? payload.risk_flags
    : Array.isArray(activeItem?.risk_flags)
      ? (activeItem?.risk_flags ?? [])
      : []
  const confidenceScore: number = Math.round(
    Number(activeItem?.confidence_score ?? payload.confidence_score ?? 0) * 100
  )

  useEffect(() => {
    if (!activeItem) return

    const sourceLines = getPayloadLines(activeItem)
    setLines(
      sourceLines.length > 0
        ? sourceLines
        : [
            {
              account_code: '6100',
              account_name: 'Office Supplies Expense',
              debit_amount: totalAmount,
              credit_amount: 0,
              description: `Expense: ${vendorName}`,
            },
            {
              account_code: '1100',
              account_name: 'Bank',
              debit_amount: 0,
              credit_amount: totalAmount,
              description: `Payment to ${vendorName}`,
            },
          ]
    )
  }, [activeItem, totalAmount, vendorName])

  if (!activeItem) return null

  const totalDebits = lines.reduce((sum, line) => sum + (Number(line.debit_amount) || 0), 0)
  const totalCredits = lines.reduce((sum, line) => sum + (Number(line.credit_amount) || 0), 0)
  const balanceDiff = Math.abs(totalDebits - totalCredits)
  const isBalanced = balanceDiff < 0.01
  const statusText =
    activeItem.status === 'pending' ? 'Needs Review' : activeItem.status.replace(/_/g, ' ')

  const handleLineChange = (
    index: number,
    field: keyof JournalLineEditPayload,
    value: string | number
  ) => {
    setLines((prev) => {
      const updated = [...prev]
      updated[index] = {
        ...updated[index],
        [field]: field === 'debit_amount' || field === 'credit_amount' ? Number(value) || 0 : value,
      }
      return updated
    })
  }

  const handleApprove = async () => {
    setSubmitting(true)
    setErrorMsg(null)
    try {
      await approveReviewItem(
        activeItem.id,
        'Approved bookkeeping classification via Bookkeeping Review Modal'
      )
      onResolved()
      onClose()
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to approve')
    } finally {
      setSubmitting(false)
    }
  }

  const handleSaveEdit = async () => {
    if (!isBalanced) {
      setErrorMsg(
        `Journal is unbalanced! Debit (${totalDebits.toLocaleString('en-US')}) ≠ Credit (${totalCredits.toLocaleString('en-US')}).`
      )
      return
    }

    setSubmitting(true)
    setErrorMsg(null)
    try {
      await editReviewItem(
        activeItem.id,
        {
          lines,
          entry_date: payload.entry_date || transactionDate,
          description: payload.description || payload.entry_description || activeItem.title,
        },
        'Edited COA classification via Bookkeeping Review Modal'
      )
      onResolved()
      onClose()
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to save edits')
    } finally {
      setSubmitting(false)
    }
  }

  const handleReject = async () => {
    if (!rejectionReason.trim()) {
      setErrorMsg('Please provide a rejection reason.')
      return
    }

    setSubmitting(true)
    setErrorMsg(null)
    try {
      await rejectReviewItem(activeItem.id, rejectionReason)
      onResolved()
      onClose()
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to reject')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/85 backdrop-blur-md flex items-start justify-center p-3 sm:p-4 overflow-y-auto">
      <div className="relative w-full max-w-7xl bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl shadow-black/60 overflow-hidden flex flex-col my-4 sm:my-6">
        <div className="px-4 sm:px-6 py-4 bg-slate-950 border-b border-slate-800 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3 min-w-0">
            <div className="min-w-0">
              <p className="text-[10px] uppercase tracking-widest text-slate-500 font-bold">
                Review Queue
              </p>
              <h2 className="text-base sm:text-lg font-bold text-white truncate">
                Journal Entry Review
              </h2>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 sm:justify-end">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-xs font-bold bg-slate-800/80 text-slate-300 border-slate-700">
              <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
              AI Draft
            </span>
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-xs font-bold bg-amber-500/10 text-amber-300 border-amber-500/20 capitalize">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
              {statusText}
            </span>
            {riskFlags.length > 0 && (
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full border text-[11px] font-bold bg-rose-500/10 text-rose-300 border-rose-500/20">
                <ShieldAlert className="w-3.5 h-3.5" />
                {riskFlags.length} Flag{riskFlags.length > 1 ? 's' : ''}
              </span>
            )}
            <button
              type="button"
              id="bookkeeping-review-close-btn"
              onClick={onClose}
              className="p-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white transition-all shrink-0"
              title="Close bookkeeping review"
              aria-label="Close bookkeeping review and return to review queue"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="max-h-[80vh] overflow-y-auto">
          {loadingDetail ? (
            <div className="py-16 text-center text-slate-400 space-y-2">
              <Loader2 className="w-8 h-8 animate-spin text-indigo-400 mx-auto" />
              <p className="text-xs">Loading bookkeeping review detail...</p>
            </div>
          ) : (
            <BookkeepingJournalPanel
              vendorName={vendorName}
              transactionDate={transactionDate}
              totalAmount={totalAmount}
              currency={currency}
              sourceLineItems={rawLineItems}
              lines={lines}
              confidenceScore={confidenceScore}
              rationale={rationale}
              riskFlags={riskFlags}
              isEditing={isEditing}
              onLineChange={handleLineChange}
              onRemoveLine={(index) => setLines((prev) => prev.filter((_, i) => i !== index))}
              onAddLine={() =>
                setLines((prev) => [
                  ...prev,
                  {
                    account_code: '',
                    account_name: '',
                    debit_amount: 0,
                    credit_amount: 0,
                    description: '',
                  },
                ])
              }
            />
          )}
        </div>

        {errorMsg && (
          <div className="px-6 py-2.5 bg-rose-500/10 border-t border-rose-500/20 flex items-center gap-2 text-rose-300 text-xs">
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        <div className="px-4 sm:px-6 py-4 bg-slate-950 border-t border-slate-800 flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-4">
          <div className="flex items-start gap-2 text-xs text-amber-300 max-w-xl">
            <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400 mt-0.5" />
            <span>
              AI generated this draft below the confidence threshold. Review the account
              classification before posting.
            </span>
          </div>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
            {showRejectInput ? (
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  id="bookkeeping-rejection-reason-input"
                  placeholder="e.g. Wrong expense account, should be 5200 Advertising Expense..."
                  value={rejectionReason}
                  onChange={(event) => setRejectionReason(event.target.value)}
                  className="flex-1 sm:w-60 px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none focus:border-rose-500"
                />
                <button
                  type="button"
                  id="bookkeeping-confirm-reject-btn"
                  onClick={handleReject}
                  disabled={submitting}
                  className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-semibold text-xs transition-all flex items-center gap-1.5 whitespace-nowrap"
                >
                  {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  Reject
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowRejectInput(false)
                    setRejectionReason('')
                    setErrorMsg(null)
                  }}
                  className="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 text-xs transition-all"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                type="button"
                id="bookkeeping-reject-btn"
                onClick={() => setShowRejectInput(true)}
                className="px-4 py-2 rounded-xl bg-rose-600/10 hover:bg-rose-600/20 border border-rose-500/20 text-rose-300 font-semibold text-xs transition-all"
              >
                Reject
              </button>
            )}

            <button
              type="button"
              id="bookkeeping-edit-btn"
              onClick={() => {
                setIsEditing((value) => !value)
                setErrorMsg(null)
              }}
              className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 font-semibold text-xs transition-all"
            >
              {isEditing ? 'Cancel Edit' : 'Edit'}
            </button>

            <button
              type="button"
              id="bookkeeping-confirm-post-btn"
              onClick={isEditing ? handleSaveEdit : handleApprove}
              disabled={submitting || (isEditing && !isBalanced)}
              className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-sm transition-all shadow-lg shadow-emerald-600/20 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <CheckCircle2 className="w-4 h-4" />
              )}
              {isEditing ? 'Save & Post' : 'Confirm & Post'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
