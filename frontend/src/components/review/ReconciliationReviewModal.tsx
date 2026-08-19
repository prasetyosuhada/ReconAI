import React, { useEffect, useState } from 'react'
import {
  AlertCircle,
  BookOpen,
  Building2,
  Calendar,
  CheckCircle2,
  Info,
  Loader2,
  PlusCircle,
  Sparkles,
  X,
} from 'lucide-react'
import type {
  AdjustmentSuggestionResponse,
  JournalEntryResponse,
  ReviewItemResponse,
} from '../../services/api'
import {
  approveReviewItem,
  createAdjustmentJournalEntry,
  fetchJournalEntryDetail,
  fetchReviewItemDetail,
  rejectReviewItem,
  suggestAdjustmentJournal,
} from '../../services/api'

interface ReconciliationReviewModalProps {
  item: ReviewItemResponse | null
  onClose: () => void
  onResolved: () => void
}

function formatCurrency(amount: number, _currency: string = 'IDR'): string {
  const formatted = new Intl.NumberFormat('id-ID', {
    style: 'decimal',
    maximumFractionDigits: 0,
  }).format(Math.abs(amount))
  const sign = amount < 0 ? '-' : '+'
  return `${sign} Rp ${formatted}`
}

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return 'N/A'
  try {
    const d = new Date(dateStr)
    return d.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return dateStr
  }
}

export const ReconciliationReviewModal: React.FC<ReconciliationReviewModalProps> = ({
  item,
  onClose,
  onResolved,
}) => {
  const [detailItem, setDetailItem] = useState<ReviewItemResponse | null>(item)
  const [_loadingDetail, setLoadingDetail] = useState<boolean>(false)
  const [candidateJE, setCandidateJE] = useState<JournalEntryResponse | null>(null)
  const [loadingCandidate, setLoadingCandidate] = useState<boolean>(false)

  // AI Adjustment suggestion state (for unmatched bank tx)
  const [suggestion, setSuggestion] = useState<AdjustmentSuggestionResponse | null>(null)
  const [suggestionLoading, setSuggestionLoading] = useState<boolean>(false)
  const [suggestionError, setSuggestionError] = useState<string | null>(null)

  // Submitting states
  const [submitting, setSubmitting] = useState<boolean>(false)
  const [resolutionNote, setResolutionNote] = useState<string>('')
  const [showRejectInput, setShowRejectInput] = useState<boolean>(false)
  const [rejectionReason, setRejectionReason] = useState<string>('')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  const activeItem = detailItem || item
  const payload: Record<string, any> = activeItem?.original_payload || {}

  // Parse bank transaction attributes from payload
  const bankTx = payload.bank_transaction || payload
  const bankTxId = activeItem?.source_id || bankTx.id || payload.tx_id || ''
  const txDescription = bankTx.description || payload.vendor_name || activeItem?.title || 'Bank Mutation'
  const txDate = bankTx.transaction_date || payload.transaction_date || ''
  const txAmount = Number(bankTx.amount ?? payload.total_amount ?? 0)
  const txCurrency = bankTx.currency || payload.currency || 'IDR'
  const txRef = bankTx.reference_number || payload.reference_number || 'N/A'

  // Candidate Match metadata (if fuzzy match)
  const proposedJEId =
    payload.proposed_journal_entry_id ||
    payload.journal_entry_id ||
    payload.proposed_je_id ||
    null
  const isFuzzyMatch = Boolean(proposedJEId)

  const confidenceScore = Math.round(
    Number(activeItem?.confidence_score ?? payload.confidence_score ?? 0.8) * 100
  )
  const rationale =
    payload.rationale || activeItem?.summary || 'Reconciliation review required by rule engine.'

  // Load detailed review item and candidate GL entry
  useEffect(() => {
    let ignore = false
    setDetailItem(item)
    setErrorMsg(null)
    setSuccessMsg(null)
    setShowRejectInput(false)
    setRejectionReason('')
    setCandidateJE(null)

    if (!item?.id) return

    setLoadingDetail(true)
    fetchReviewItemDetail(item.id)
      .then((res) => {
        if (!ignore) {
          setDetailItem(res)
          const p = res.original_payload || {}
          const jeId =
            p.proposed_journal_entry_id || p.journal_entry_id || p.proposed_je_id
          if (jeId) {
            setLoadingCandidate(true)
            fetchJournalEntryDetail(jeId)
              .then((je) => {
                if (!ignore) setCandidateJE(je)
              })
              .catch((err) => {
                console.error('Failed to load candidate journal entry:', err)
              })
              .finally(() => {
                if (!ignore) setLoadingCandidate(false)
              })
          }
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setErrorMsg(err instanceof Error ? err.message : 'Failed to load review detail')
        }
      })
      .finally(() => {
        if (!ignore) setLoadingDetail(false)
      })

    return () => {
      ignore = true
    }
  }, [item?.id])

  // Load Bookkeeping suggestion if this is an unmatched bank transaction (no candidate JE)
  useEffect(() => {
    if (isFuzzyMatch || !bankTxId) return

    setSuggestionLoading(true)
    setSuggestionError(null)

    suggestAdjustmentJournal(String(bankTxId))
      .then((res) => {
        setSuggestion(res)
      })
      .catch((err: Error) => {
        if (err.message.includes('Run Recon Engine')) {
          setSuggestionError('Run Recon Engine to generate precomputed COA suggestions.')
        } else {
          setSuggestionError(err.message)
        }
      })
      .finally(() => {
        setSuggestionLoading(false)
      })
  }, [bankTxId, isFuzzyMatch])

  // Handle Approve / Accept Match
  const handleAcceptMatch = async () => {
    if (!activeItem?.id) return
    setSubmitting(true)
    setErrorMsg(null)
    try {
      await approveReviewItem(
        activeItem.id,
        resolutionNote.trim() || 'Approved by reviewer in Review Queue.'
      )
      setSuccessMsg('✓ Match confirmed! Bank transaction and General Ledger entry reconciled.')
      setTimeout(() => {
        onResolved()
        onClose()
      }, 1000)
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to approve review item')
      setSubmitting(false)
    }
  }

  // Handle Reject Match / Leave Unmatched
  const handleRejectMatch = async () => {
    if (!activeItem?.id) return
    if (!rejectionReason.trim()) {
      setErrorMsg('Please specify a reason for rejecting this match.')
      return
    }
    setSubmitting(true)
    setErrorMsg(null)
    try {
      await rejectReviewItem(activeItem.id, rejectionReason.trim())
      setSuccessMsg('✓ Match rejected. Bank mutation remains unmatched in review list.')
      setTimeout(() => {
        onResolved()
        onClose()
      }, 1000)
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to reject review item')
      setSubmitting(false)
    }
  }

  // Handle Create & Post Adjusting Entry for Unmatched Bank Transaction
  const handleCreateAdjustmentEntry = async () => {
    if (!bankTxId) return
    setSubmitting(true)
    setErrorMsg(null)
    try {
      const res = await createAdjustmentJournalEntry({
        bank_transaction_id: String(bankTxId),
        lines: suggestion?.suggested_lines,
        description: txDescription,
      })
      // Also approve the review item
      if (activeItem?.id) {
        await approveReviewItem(
          activeItem.id,
          `Created adjusting entry #JE-${res.journal_entry_id.substring(0, 8)}.`
        )
      }
      setSuccessMsg(
        `✓ Adjusting Journal Entry #JE-${res.journal_entry_id.substring(0, 8)} created & posted to General Ledger!`
      )
      setTimeout(() => {
        onResolved()
        onClose()
      }, 1200)
    } catch (err: unknown) {
      setErrorMsg(
        err instanceof Error ? err.message : 'Failed to create and post adjusting journal entry.'
      )
      setSubmitting(false)
    }
  }


  if (!item) return null

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 overflow-y-auto">
      <div className="bg-slate-900 border border-slate-700/80 w-full max-w-4xl rounded-2xl shadow-2xl overflow-hidden flex flex-col my-auto max-h-[92vh]">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-gradient-to-r from-indigo-950/40 via-purple-950/20 to-slate-900 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
              <Building2 className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-white tracking-wide">
                  Bank Mutation Reconciliation Review
                </h3>
                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 uppercase tracking-wider">
                  {isFuzzyMatch ? 'Fuzzy Match Candidate' : 'Unmatched Mutation'}
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30 font-mono">
                  {confidenceScore}% Confidence
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">{activeItem?.title}</p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1">
          {/* Notifications / Alerts */}
          {errorMsg && (
            <div className="p-3 rounded-xl bg-red-950/40 border border-red-500/40 flex items-center gap-2 text-xs text-red-300">
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          {successMsg && (
            <div className="p-3 rounded-xl bg-emerald-950/40 border border-emerald-500/40 flex items-center gap-2 text-xs text-emerald-300 animate-pulse">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
              <span>{successMsg}</span>
            </div>
          )}

          {/* AI Rationale & Risk Banner */}
          <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-2">
            <div className="flex items-center gap-2 text-xs font-bold text-indigo-300 uppercase tracking-wider">
              <Sparkles className="w-4 h-4 text-indigo-400" />
              <span>AI Reconciliation Reasoning</span>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed font-sans">{rationale}</p>
          </div>

          {/* Comparison Cards: Bank Statement vs General Ledger */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Left Card: Bank Statement Mutation */}
            <div className="p-4 rounded-xl bg-slate-950/70 border border-slate-800 space-y-3">
              <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                  <Building2 className="w-3.5 h-3.5 text-blue-400" /> Bank Statement Mutation
                </span>
                <span className="text-[10px] font-mono text-slate-500">
                  Ref: {txRef}
                </span>
              </div>

              <div className="space-y-2">
                <div>
                  <span className="text-[10px] text-slate-500 block">Description / Memo</span>
                  <span className="text-xs font-semibold text-white">{txDescription}</span>
                </div>

                <div className="grid grid-cols-2 gap-2 pt-1">
                  <div>
                    <span className="text-[10px] text-slate-500 block">Transaction Date</span>
                    <span className="text-xs font-mono font-medium text-slate-300 flex items-center gap-1">
                      <Calendar className="w-3 h-3 text-slate-500" />
                      {formatDate(txDate)}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 block">Amount</span>
                    <span
                      className={`text-xs font-mono font-bold ${
                        txAmount < 0 ? 'text-rose-400' : 'text-emerald-400'
                      }`}
                    >
                      {formatCurrency(txAmount, txCurrency)}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Right Card: Candidate GL Entry OR AI Suggested COA */}
            {isFuzzyMatch ? (
              <div className="p-4 rounded-xl bg-slate-950/70 border border-indigo-900/40 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="text-[11px] font-bold text-indigo-300 uppercase tracking-wider flex items-center gap-1.5">
                    <BookOpen className="w-3.5 h-3.5 text-indigo-400" /> Proposed GL Journal Entry
                  </span>
                  {candidateJE && (
                    <span className="text-[10px] font-mono text-indigo-400">
                      #JE-{candidateJE.id.substring(0, 8)}
                    </span>
                  )}
                </div>

                {loadingCandidate ? (
                  <div className="py-6 flex items-center justify-center gap-2 text-xs text-slate-400">
                    <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
                    <span>Loading candidate ledger entry...</span>
                  </div>
                ) : candidateJE ? (
                  <div className="space-y-2">
                    <div>
                      <span className="text-[10px] text-slate-500 block">GL Description</span>
                      <span className="text-xs font-semibold text-white">
                        {candidateJE.description}
                      </span>
                    </div>

                    <div className="grid grid-cols-2 gap-2 pt-1">
                      <div>
                        <span className="text-[10px] text-slate-500 block">Entry Date</span>
                        <span className="text-xs font-mono font-medium text-slate-300 flex items-center gap-1">
                          <Calendar className="w-3 h-3 text-slate-500" />
                          {formatDate(candidateJE.entry_date)}
                        </span>
                      </div>
                      <div>
                        <span className="text-[10px] text-slate-500 block">Total GL Amount</span>
                        <span className="text-xs font-mono font-bold text-emerald-400">
                          {formatCurrency(candidateJE.total_debit || 0)}
                        </span>
                      </div>
                    </div>

                    {/* Double-entry lines breakdown */}
                    {candidateJE.lines && candidateJE.lines.length > 0 && (
                      <div className="pt-2 border-t border-slate-800/80 space-y-1">
                        <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">
                          Journal Lines
                        </span>
                        {candidateJE.lines.map((line, idx) => (
                          <div
                            key={idx}
                            className="flex items-center justify-between text-[11px] text-slate-300 font-mono"
                          >
                            <span>
                              [{line.debit_amount > 0 ? 'DR' : 'CR'}] {line.account_code} •{' '}
                              {line.account_name}
                            </span>
                            <span className="font-semibold text-slate-200">
                              {formatCurrency(
                                line.debit_amount > 0 ? line.debit_amount : line.credit_amount
                              )}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="py-4 text-xs text-slate-400">
                    Candidate Entry #{proposedJEId?.substring(0, 8)}
                  </div>
                )}
              </div>
            ) : (
              /* Unmatched: AI Adjustment Suggestion Card */
              <div className="p-4 rounded-xl bg-purple-950/20 border border-purple-500/30 space-y-3">
                <div className="flex items-center justify-between border-b border-purple-500/20 pb-2">
                  <span className="text-[11px] font-bold text-purple-300 uppercase tracking-wider flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-purple-400" /> AI Suggested Journal Entry
                  </span>
                  {suggestion && (
                    <span className="text-[10px] font-mono text-purple-300">
                      {Math.round(suggestion.confidence_score * 100)}% Conf
                    </span>
                  )}
                </div>

                {suggestionLoading ? (
                  <div className="py-6 flex items-center justify-center gap-2 text-xs text-purple-300">
                    <Loader2 className="w-4 h-4 animate-spin text-purple-400" />
                    <span>Loading Bookkeeping COA suggestion...</span>
                  </div>
                ) : suggestionError ? (
                  <div className="p-3 rounded-lg bg-blue-950/30 border border-blue-500/30 text-xs text-blue-300 flex items-center gap-2">
                    <Info className="w-4 h-4 text-blue-400 shrink-0" />
                    <span>{suggestionError}</span>
                  </div>
                ) : suggestion?.suggested_lines && suggestion.suggested_lines.length > 0 ? (
                  <div className="space-y-2">
                    <p className="text-xs text-purple-200/90 font-sans italic">
                      "{suggestion.rationale}"
                    </p>

                    <div className="pt-2 border-t border-purple-500/20 space-y-1">
                      <span className="text-[10px] text-purple-300 font-bold uppercase tracking-wider block">
                        Proposed Double-Entry Lines
                      </span>
                      {suggestion.suggested_lines.map((line, idx) => (
                        <div
                          key={idx}
                          className="flex items-center justify-between text-[11px] text-slate-200 font-mono bg-purple-950/40 px-2 py-1 rounded"
                        >
                          <span>
                            [{line.debit_amount > 0 ? 'DR' : 'CR'}] {line.account_code} •{' '}
                            {line.account_name}
                          </span>
                          <span className="font-semibold text-emerald-400">
                            {formatCurrency(
                              line.debit_amount > 0 ? line.debit_amount : line.credit_amount,
                              suggestion.currency
                            )}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2 text-xs text-slate-300">
                    <p>No candidate match found in posted ledger.</p>
                    <p className="text-[11px] text-slate-400">
                      You can create an adjusting journal entry to classify this mutation directly
                      to General Ledger.
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Rejection input box */}
          {showRejectInput && (
            <div className="p-4 rounded-xl bg-red-950/30 border border-red-500/30 space-y-2">
              <label className="text-xs font-semibold text-red-300 block">
                Reason for Rejecting this Reconciliation Item:
              </label>
              <textarea
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                placeholder="e.g. Transaction amount does not correspond to this vendor / Needs bank inquiry..."
                rows={2}
                className="w-full p-2.5 rounded-lg bg-slate-950 border border-red-500/40 text-xs text-slate-200 focus:outline-none focus:border-red-500"
              />
            </div>
          )}

          {/* Optional Resolution Note */}
          {!showRejectInput && (
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-400 block">
                Resolution Note (Optional):
              </label>
              <input
                type="text"
                value={resolutionNote}
                onChange={(e) => setResolutionNote(e.target.value)}
                placeholder="e.g. Verified against bank mutation description..."
                className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
              />
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="px-6 py-4 border-t border-slate-800 bg-slate-950/80 flex items-center justify-between shrink-0">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold text-xs transition-colors cursor-pointer disabled:opacity-50"
          >
            Cancel
          </button>

          <div className="flex items-center gap-3">
            {showRejectInput ? (
              <>
                <button
                  type="button"
                  onClick={() => setShowRejectInput(false)}
                  disabled={submitting}
                  className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold text-xs transition-colors cursor-pointer"
                >
                  Back
                </button>
                <button
                  type="button"
                  onClick={handleRejectMatch}
                  disabled={submitting}
                  className="px-4 py-2 rounded-xl bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white font-semibold text-xs transition-colors shadow-md shadow-red-600/20 flex items-center gap-1.5 cursor-pointer"
                >
                  {submitting ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <X className="w-4 h-4" />
                  )}
                  Confirm Rejection
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  onClick={() => setShowRejectInput(true)}
                  disabled={submitting}
                  className="px-4 py-2 rounded-xl bg-red-950/60 hover:bg-red-900/80 border border-red-500/40 text-red-300 font-semibold text-xs transition-colors cursor-pointer disabled:opacity-50 flex items-center gap-1.5"
                >
                  <X className="w-4 h-4 text-red-400" />
                  Reject Match
                </button>

                {isFuzzyMatch ? (
                  <button
                    type="button"
                    onClick={handleAcceptMatch}
                    disabled={submitting}
                    className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-semibold text-xs transition-colors shadow-md shadow-emerald-600/20 flex items-center gap-1.5 cursor-pointer"
                  >
                    {submitting ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <CheckCircle2 className="w-4 h-4" />
                    )}
                    Accept &amp; Reconcile Match
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={handleCreateAdjustmentEntry}
                    disabled={submitting}
                    className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-semibold text-xs transition-colors shadow-md shadow-purple-600/20 flex items-center gap-1.5 cursor-pointer"
                  >
                    {submitting ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <PlusCircle className="w-4 h-4" />
                    )}
                    Create &amp; Post Adjusting Entry
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
