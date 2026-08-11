import React, { useEffect, useState } from 'react'
import {
  AlertCircle,
  AlertTriangle,
  Check,
  CheckCircle2,
  FileText,
  Info,
  Loader2,
  Plus,
  ShieldAlert,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react'
import type { JournalLineEditPayload, ReviewItemResponse } from '../../services/api'
import { approveReviewItem, editReviewItem, rejectReviewItem } from '../../services/api'

interface ReviewDetailModalProps {
  item: ReviewItemResponse | null
  onClose: () => void
  onResolved: () => void
}

export const ReviewDetailModal: React.FC<ReviewDetailModalProps> = ({
  item,
  onClose,
  onResolved,
}) => {
  if (!item) return null

  // Extraction payload states
  const originalPayload = item.original_payload || {}
  const extractedVendor = originalPayload.vendor_name || originalPayload.merchant_name || 'N/A'
  const extractedDate = originalPayload.invoice_date || originalPayload.transaction_date || ''
  const extractedTotal = originalPayload.total_amount || originalPayload.amount || 0
  const extractedTax = originalPayload.tax_amount || 0
  const extractedCurrency = originalPayload.currency || 'IDR'

  // Editable Journal Entry States
  const defaultLines: JournalLineEditPayload[] = item.edited_payload?.lines ||
    originalPayload.lines ||
    originalPayload.journal_lines || [
      {
        account_code: '5100',
        account_name: 'Office Supplies Expense',
        debit_amount: Number(extractedTotal) || 0,
        credit_amount: 0,
        description: `Expense: ${extractedVendor}`,
      },
      {
        account_code: '1010',
        account_name: 'Bank Account',
        debit_amount: 0,
        credit_amount: Number(extractedTotal) || 0,
        description: `Payment to ${extractedVendor}`,
      },
    ]

  const [entryDate, setEntryDate] = useState<string>(
    item.edited_payload?.entry_date || extractedDate || new Date().toISOString().split('T')[0]
  )
  const [description, setDescription] = useState<string>(
    item.edited_payload?.description || item.title || `Journal for ${extractedVendor}`
  )
  const [lines, setLines] = useState<JournalLineEditPayload[]>(defaultLines)
  const [rejectionReason, setRejectionReason] = useState<string>('')
  const [showRejectInput, setShowRejectInput] = useState<boolean>(false)

  const [submitting, setSubmitting] = useState<boolean>(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // Balance calculation
  const totalDebits = lines.reduce((acc, l) => acc + (Number(l.debit_amount) || 0), 0)
  const totalCredits = lines.reduce((acc, l) => acc + (Number(l.credit_amount) || 0), 0)
  const balanceDiff = Math.abs(totalDebits - totalCredits)
  const isBalanced = balanceDiff < 0.01

  useEffect(() => {
    setErrorMsg(null)
  }, [lines, entryDate, description])

  const handleLineChange = (
    index: number,
    field: keyof JournalLineEditPayload,
    value: string | number
  ) => {
    const updated = [...lines]
    updated[index] = {
      ...updated[index],
      [field]: field === 'debit_amount' || field === 'credit_amount' ? Number(value) || 0 : value,
    }
    setLines(updated)
  }

  const handleAddLine = () => {
    setLines([
      ...lines,
      {
        account_code: '5200',
        account_name: 'General Expense',
        debit_amount: 0,
        credit_amount: 0,
        description: '',
      },
    ])
  }

  const handleRemoveLine = (index: number) => {
    if (lines.length <= 2) {
      alert('A valid journal entry must contain at least 2 lines (Double-Entry).')
      return
    }
    setLines(lines.filter((_, i) => i !== index))
  }

  const handleApproveAsIs = async () => {
    setSubmitting(true)
    setErrorMsg(null)
    try {
      await approveReviewItem(item.id, 'Approved as-is via Review Detail Modal')
      onResolved()
      onClose()
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to approve item')
    } finally {
      setSubmitting(false)
    }
  }

  const handleSaveAndApprove = async () => {
    if (!isBalanced) {
      setErrorMsg(
        `Double-entry unbalanced! Debits (${totalDebits.toLocaleString()}) must equal Credits (${totalCredits.toLocaleString()}).`
      )
      return
    }

    setSubmitting(true)
    setErrorMsg(null)

    const editedPayload = {
      entry_date: entryDate,
      description,
      lines,
    }

    try {
      await editReviewItem(item.id, editedPayload, 'Edited and approved via Review Detail Modal')
      onResolved()
      onClose()
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to save edited entry')
    } finally {
      setSubmitting(false)
    }
  }

  const handleReject = async () => {
    if (!rejectionReason.trim()) {
      alert('Please provide a reason for rejecting this item.')
      return
    }

    setSubmitting(true)
    setErrorMsg(null)
    try {
      await rejectReviewItem(item.id, rejectionReason)
      onResolved()
      onClose()
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to reject item')
    } finally {
      setSubmitting(false)
    }
  }

  const confPercent = Math.round((item.confidence_score || 0) * 100)

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-md flex items-center justify-center p-4 overflow-y-auto">
      <div className="relative max-w-6xl w-full max-h-[92vh] bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col my-auto">
        {/* Header */}
        <div className="px-6 py-4 bg-slate-950/80 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-lg font-bold text-white">{item.title}</h3>
                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20 uppercase tracking-wider">
                  {item.priority} Priority
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Review ID: <span className="font-mono text-slate-300">{item.id}</span>
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition-all"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Scrollable Body */}
        <div className="flex-1 overflow-y-auto p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column: Extraction & Rationale (5 cols) */}
          <div className="lg:col-span-5 space-y-4">
            {/* Extracted Metadata Card */}
            <div className="p-5 rounded-xl bg-slate-950/60 border border-slate-800 space-y-3">
              <h4 className="text-xs font-bold text-indigo-300 uppercase tracking-wider flex items-center gap-1.5">
                <FileText className="w-4 h-4 text-indigo-400" />
                AI Extraction Summary
              </h4>

              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <span className="text-slate-500 block text-[11px]">Vendor Name</span>
                  <span className="font-semibold text-slate-200">{extractedVendor}</span>
                </div>
                <div>
                  <span className="text-slate-500 block text-[11px]">Invoice Date</span>
                  <span className="font-semibold text-slate-200">{extractedDate || 'N/A'}</span>
                </div>
                <div>
                  <span className="text-slate-500 block text-[11px]">Total Amount</span>
                  <span className="font-bold text-emerald-400">
                    {Number(extractedTotal).toLocaleString()} {extractedCurrency}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500 block text-[11px]">Tax Amount</span>
                  <span className="font-semibold text-slate-300">
                    {Number(extractedTax).toLocaleString()} {extractedCurrency}
                  </span>
                </div>
              </div>
            </div>

            {/* Confidence Score & AI Rationale Card */}
            <div className="p-5 rounded-xl bg-slate-950/60 border border-slate-800 space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-indigo-300 uppercase tracking-wider flex items-center gap-1.5">
                  <Info className="w-4 h-4 text-indigo-400" />
                  Agent Confidence & Rationale
                </h4>
                <span className="font-bold text-xs text-amber-400">{confPercent}% Match</span>
              </div>

              {/* Progress bar */}
              <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${
                    confPercent >= 85
                      ? 'bg-emerald-400'
                      : confPercent >= 70
                        ? 'bg-amber-400'
                        : 'bg-rose-400'
                  }`}
                  style={{ width: `${confPercent}%` }}
                />
              </div>

              <p className="text-xs text-slate-300 bg-slate-900/90 p-3 rounded-lg border border-slate-800/80 leading-relaxed italic">
                "{item.summary}"
              </p>

              {item.suggested_action && (
                <div className="text-xs text-indigo-300 bg-indigo-500/10 p-2.5 rounded-lg border border-indigo-500/20 flex items-start gap-2">
                  <Sparkles className="w-4 h-4 shrink-0 text-indigo-400 mt-0.5" />
                  <span>
                    <strong>Suggested Action:</strong> {item.suggested_action}
                  </span>
                </div>
              )}
            </div>

            {/* Risk Flags Notice */}
            {item.risk_flags && item.risk_flags.length > 0 && (
              <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 space-y-2">
                <h4 className="text-xs font-bold text-amber-300 uppercase tracking-wider flex items-center gap-1.5">
                  <ShieldAlert className="w-4 h-4 text-amber-400" />
                  Triggered Guardrail Flags
                </h4>
                <div className="flex flex-wrap gap-1.5">
                  {item.risk_flags.map((flag) => (
                    <span
                      key={flag}
                      className="px-2.5 py-1 rounded bg-amber-500/20 text-amber-200 text-xs font-medium border border-amber-500/30"
                    >
                      ⚠️ {flag}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Right Column: Editable Journal Entry Form (7 cols) */}
          <div className="lg:col-span-7 space-y-4">
            <div className="p-5 rounded-xl bg-slate-950/60 border border-slate-800 space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-indigo-300 uppercase tracking-wider flex items-center gap-1.5">
                  <FileText className="w-4 h-4 text-indigo-400" />
                  Editable Journal Entry Payload
                </h4>
                <span className="text-[11px] text-slate-400">Deterministic Double-Entry</span>
              </div>

              {/* Form Controls: Date & Description */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-[11px] font-semibold text-slate-400 mb-1">
                    Entry Date
                  </label>
                  <input
                    type="date"
                    value={entryDate}
                    onChange={(e) => setEntryDate(e.target.value)}
                    className="w-full px-3 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-100 focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div className="sm:col-span-2">
                  <label className="block text-[11px] font-semibold text-slate-400 mb-1">
                    Journal Description / Memo
                  </label>
                  <input
                    type="text"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    className="w-full px-3 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-100 focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              {/* Lines Table */}
              <div className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-900/60">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950 text-slate-400 border-b border-slate-800 font-semibold uppercase text-[10px]">
                    <tr>
                      <th className="py-2.5 px-3">Account Code</th>
                      <th className="py-2.5 px-3">Account Name</th>
                      <th className="py-2.5 px-3 text-right">Debit (IDR)</th>
                      <th className="py-2.5 px-3 text-right">Credit (IDR)</th>
                      <th className="py-2.5 px-3 text-center">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/80">
                    {lines.map((line, idx) => (
                      <tr key={idx} className="hover:bg-slate-900">
                        <td className="py-2 px-3 w-28">
                          <input
                            type="text"
                            value={line.account_code}
                            onChange={(e) => handleLineChange(idx, 'account_code', e.target.value)}
                            className="w-full px-2 py-1 bg-slate-950 border border-slate-700 rounded text-xs text-slate-100 font-mono focus:border-indigo-500"
                          />
                        </td>
                        <td className="py-2 px-3">
                          <input
                            type="text"
                            value={line.account_name || ''}
                            onChange={(e) => handleLineChange(idx, 'account_name', e.target.value)}
                            className="w-full px-2 py-1 bg-slate-950 border border-slate-700 rounded text-xs text-slate-100 focus:border-indigo-500"
                          />
                        </td>
                        <td className="py-2 px-3 w-32">
                          <input
                            type="number"
                            step="any"
                            value={line.debit_amount || ''}
                            onChange={(e) => handleLineChange(idx, 'debit_amount', e.target.value)}
                            className="w-full px-2 py-1 bg-slate-950 border border-slate-700 rounded text-xs text-emerald-400 font-bold text-right focus:border-indigo-500"
                          />
                        </td>
                        <td className="py-2 px-3 w-32">
                          <input
                            type="number"
                            step="any"
                            value={line.credit_amount || ''}
                            onChange={(e) => handleLineChange(idx, 'credit_amount', e.target.value)}
                            className="w-full px-2 py-1 bg-slate-950 border border-slate-700 rounded text-xs text-indigo-400 font-bold text-right focus:border-indigo-500"
                          />
                        </td>
                        <td className="py-2 px-3 text-center w-12">
                          <button
                            type="button"
                            onClick={() => handleRemoveLine(idx)}
                            className="p-1 rounded text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
                            title="Delete line"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Add Line & Balance Summary */}
              <div className="flex items-center justify-between pt-1">
                <button
                  type="button"
                  onClick={handleAddLine}
                  className="px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-300 text-xs font-semibold flex items-center gap-1 transition-all"
                >
                  <Plus className="w-3.5 h-3.5" /> Add Line Item
                </button>

                <div className="flex items-center gap-4 text-xs font-mono">
                  <div>
                    <span className="text-slate-500">Debits: </span>
                    <span className="font-bold text-emerald-400">
                      {totalDebits.toLocaleString()}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500">Credits: </span>
                    <span className="font-bold text-indigo-400">
                      {totalCredits.toLocaleString()}
                    </span>
                  </div>

                  {isBalanced ? (
                    <span className="px-2.5 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[11px] font-sans font-bold flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3" /> BALANCED
                    </span>
                  ) : (
                    <span className="px-2.5 py-0.5 rounded-full bg-rose-500/10 border border-rose-500/20 text-rose-400 text-[11px] font-sans font-bold flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3" /> Δ {balanceDiff.toLocaleString()}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Error Banner inside Modal */}
        {errorMsg && (
          <div className="px-6 py-2.5 bg-rose-500/10 border-t border-rose-500/20 text-rose-300 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* Footer Action Bar */}
        <div className="px-6 py-4 bg-slate-950/90 border-t border-slate-800 flex flex-col sm:flex-row items-center justify-between gap-4">
          {showRejectInput ? (
            <div className="flex items-center gap-2 w-full sm:w-auto flex-1">
              <input
                type="text"
                placeholder="Reason for rejection..."
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                className="flex-1 px-3 py-1.5 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none focus:border-rose-500"
              />
              <button
                type="button"
                onClick={handleReject}
                disabled={submitting}
                className="px-4 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-semibold text-xs transition-all flex items-center gap-1"
              >
                {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                Confirm Reject
              </button>
              <button
                type="button"
                onClick={() => setShowRejectInput(false)}
                className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 text-xs"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setShowRejectInput(true)}
              className="px-4 py-2 rounded-xl bg-rose-600/10 hover:bg-rose-600/20 border border-rose-500/20 text-rose-300 font-semibold text-xs transition-all"
            >
              Reject Item
            </button>
          )}

          <div className="flex items-center gap-3 w-full sm:w-auto justify-end">
            <button
              type="button"
              onClick={handleApproveAsIs}
              disabled={submitting}
              className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 font-semibold text-xs transition-all flex items-center gap-1.5 disabled:opacity-50"
            >
              {submitting ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Check className="w-3.5 h-3.5 text-emerald-400" />
              )}
              Approve As-Is (AI Suggestion)
            </button>

            <button
              type="button"
              onClick={handleSaveAndApprove}
              disabled={submitting || !isBalanced}
              className="px-5 py-2 rounded-xl bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600 text-white font-semibold text-xs transition-all shadow-lg shadow-indigo-600/30 flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <CheckCircle2 className="w-3.5 h-3.5" />
              )}
              Save Edits & Post to Ledger
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
