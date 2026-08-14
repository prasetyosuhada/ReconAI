import React, { useEffect, useState } from 'react'
import { ArrowLeft, BookOpen, CheckCircle2, Loader2, Send, Sparkles } from 'lucide-react'
import type { DocumentExtractionResponse, JournalEntryResponse } from '../../services/api'
import {
  fetchJournalEntryDetail,
  fetchLatestDocumentExtraction,
  postJournalEntry,
} from '../../services/api'
import { BookkeepingJournalPanel } from '../shared/BookkeepingJournalPanel'

interface JournalDetailModalProps {
  entryId: string | null
  onClose: () => void
  onPosted?: () => void
}

const statusTone = (status: string) => {
  switch (status) {
    case 'posted':
      return 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20'
    case 'review_required':
    case 'bookkeeping_review_required':
      return 'bg-rose-500/10 text-rose-300 border-rose-500/20'
    default:
      return 'bg-amber-500/10 text-amber-300 border-amber-500/20'
  }
}

export const JournalDetailModal: React.FC<JournalDetailModalProps> = ({
  entryId,
  onClose,
  onPosted,
}) => {
  const [detail, setDetail] = useState<JournalEntryResponse | null>(null)
  const [extraction, setExtraction] = useState<DocumentExtractionResponse | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [posting, setPosting] = useState<boolean>(false)
  const [postError, setPostError] = useState<string | null>(null)
  const [postSuccess, setPostSuccess] = useState<boolean>(false)

  useEffect(() => {
    if (!entryId) return

    const loadDetail = async () => {
      setLoading(true)
      setError(null)
      setPostError(null)
      setPostSuccess(false)
      try {
        const res = await fetchJournalEntryDetail(entryId)
        setDetail(res)
        if (res.document_id) {
          const latestExtraction = await fetchLatestDocumentExtraction(res.document_id).catch(
            () => null
          )
          setExtraction(latestExtraction)
        } else {
          setExtraction(null)
        }
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to load journal detail')
      } finally {
        setLoading(false)
      }
    }

    loadDetail()
  }, [entryId])

  if (!entryId) return null

  const lines =
    detail?.lines?.map((line) => ({
      id: line.id,
      line_number: line.line_number,
      account_code: line.account_code,
      account_name: line.account_name,
      debit_amount: line.debit_amount,
      credit_amount: line.credit_amount,
      description: line.description,
    })) ?? []
  const computedTotalDebit = lines.reduce((sum, line) => sum + (line.debit_amount ?? 0), 0)
  const computedTotalCredit = lines.reduce((sum, line) => sum + (line.credit_amount ?? 0), 0)
  const isBalanced = Math.abs(computedTotalDebit - computedTotalCredit) < 0.01
  const canPost = detail?.status === 'draft' || detail?.status === 'ready_to_post'
  const rawLineItems = Array.isArray(extraction?.line_items)
    ? extraction.line_items
    : Array.isArray((extraction?.line_items as Record<string, any> | undefined)?.items)
      ? (extraction?.line_items as Record<string, any>).items
      : []

  const handlePost = async () => {
    if (!entryId) return
    setPosting(true)
    setPostError(null)
    try {
      await postJournalEntry(entryId)
      setPostSuccess(true)
      const updated = await fetchJournalEntryDetail(entryId)
      setDetail(updated)
      onPosted?.()
    } catch (err: unknown) {
      setPostError(err instanceof Error ? err.message : 'Failed to post journal entry')
    } finally {
      setPosting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/85 backdrop-blur-md flex items-start justify-center p-3 sm:p-4 overflow-y-auto">
      <div className="relative w-full max-w-7xl bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl shadow-black/60 overflow-hidden flex flex-col my-4 sm:my-6">
        <div className="px-4 sm:px-6 py-4 bg-slate-950 border-b border-slate-800 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              onClick={onClose}
              className="p-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white transition-all shrink-0"
              title="Back to general ledger"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div className="min-w-0">
              <p className="text-[10px] uppercase tracking-widest text-slate-500 font-bold">
                General Ledger
              </p>
              <h2 className="text-base sm:text-lg font-bold text-white truncate">
                Journal Entry Details
              </h2>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 sm:justify-end">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-xs font-bold bg-indigo-500/10 text-indigo-300 border-indigo-500/20">
              <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
              Ready Workflow
            </span>
            {detail && (
              <span
                className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-xs font-bold capitalize ${statusTone(
                  detail.status
                )}`}
              >
                <BookOpen className="w-3.5 h-3.5" />
                {detail.status.replace(/_/g, ' ')}
              </span>
            )}
          </div>
        </div>

        <div className="max-h-[80vh] overflow-y-auto">
          {loading ? (
            <div className="py-16 text-center text-slate-400 space-y-2">
              <Loader2 className="w-8 h-8 animate-spin text-indigo-400 mx-auto" />
              <p className="text-xs">Fetching journal entry lines...</p>
            </div>
          ) : error ? (
            <div className="m-6 p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs">
              {error}
            </div>
          ) : detail ? (
            <BookkeepingJournalPanel
              vendorName={extraction?.vendor_name || detail.description || 'Journal Entry'}
              transactionDate={extraction?.transaction_date || detail.entry_date}
              totalAmount={
                extraction?.total_amount || Math.max(computedTotalDebit, computedTotalCredit)
              }
              currency={extraction?.currency || 'IDR'}
              sourceLineItems={rawLineItems}
              lines={lines}
              confidenceScore={Math.round(
                Number(detail.confidence_score ?? 0) * 100
              )}
              rationale={detail.rationale || undefined}
              riskFlags={detail.risk_flags || []}
            />
          ) : null}
        </div>

        {postError && (
          <div className="px-6 py-2.5 bg-rose-500/10 border-t border-rose-500/20 text-rose-300 text-xs">
            {postError}
          </div>
        )}

        {postSuccess && (
          <div className="px-6 py-2.5 bg-emerald-500/10 border-t border-emerald-500/20 text-emerald-300 text-xs flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            Journal entry successfully posted to the general ledger.
          </div>
        )}

        {detail && (
          <div className="px-4 sm:px-6 py-4 bg-slate-950 border-t border-slate-800 flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-4">
            <p className="text-xs text-slate-400 max-w-xl">
              High-confidence bookkeeping uses the same review surface as manual review, with
              posting as the final action.
            </p>

            {canPost && !postSuccess && (
              <button
                type="button"
                id="journal-post-btn"
                onClick={handlePost}
                disabled={posting || !isBalanced}
                title={!isBalanced ? 'Cannot post: journal entry is unbalanced' : undefined}
                className="shrink-0 px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-sm transition-all shadow-lg shadow-emerald-600/20 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {posting ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
                {posting ? 'Posting...' : 'Post to Ledger'}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
