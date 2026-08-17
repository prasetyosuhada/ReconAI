import React from 'react'
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  BookOpen,
  Building2,
  CheckCircle2,
  FileSpreadsheet,
  HelpCircle,
  Info,
  Loader2,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import type {
  BankTransactionResponse,
  JournalEntryResponse,
  ReconciliationMatchResponse,
} from '../../services/api'
import type { ReconFilterType } from './ReconciliationFiltersToolbar'

interface Reconciliation2ColumnViewProps {
  transactions: BankTransactionResponse[]
  matches: ReconciliationMatchResponse[]
  glOnlyEntries?: JournalEntryResponse[]
  activeFilter: ReconFilterType
  loading: boolean
  selectedTxId: string | null
  selectedGLEntryId?: string | null
  onSelectTx: (txId: string) => void
  onSelectGLEntry?: (glId: string) => void
}

function formatCardDate(isoOrDate: string): string {
  try {
    const d = new Date(isoOrDate)
    if (isNaN(d.getTime())) return isoOrDate
    return d.toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' })
  } catch {
    return isoOrDate
  }
}

function formatCardAmount(amount: number, currency: string = 'IDR'): string {
  const isNegative = amount < 0
  const absFormatted = new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: currency || 'IDR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Math.abs(amount))
  return isNegative ? `- ${absFormatted}` : `+ ${absFormatted}`
}

export const Reconciliation2ColumnView: React.FC<Reconciliation2ColumnViewProps> = ({
  transactions,
  matches,
  glOnlyEntries = [],
  activeFilter,
  loading,
  selectedTxId,
  selectedGLEntryId,
  onSelectTx,
  onSelectGLEntry,
}) => {
  const isGLOnlyTab = activeFilter === 'gl_only'

  const selectedTx = transactions.find((t) => t.id === selectedTxId) || transactions[0]
  const selectedMatch = matches.find(
    (m) => m.bank_transaction_id === (selectedTx ? selectedTx.id : '')
  )
  const selectedGL = glOnlyEntries.find((g) => g.id === selectedGLEntryId) || glOnlyEntries[0]

  const getStatusBadge = (status: string) => {
    switch (status.toLowerCase()) {
      case 'matched':
      case 'accepted':
        return (
          <span className="px-2 py-0.5 rounded-full bg-emerald-950/70 border border-emerald-500/30 text-emerald-400 text-[10px] font-bold tracking-wider flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3" /> MATCHED
          </span>
        )
      case 'proposed':
        return (
          <span className="px-2 py-0.5 rounded-full bg-amber-950/70 border border-amber-500/30 text-amber-400 text-[10px] font-bold tracking-wider flex items-center gap-1">
            <AlertTriangle className="w-3 h-3" /> REVIEW REQUIRED
          </span>
        )
      default:
        return (
          <span className="px-2 py-0.5 rounded-full bg-slate-800/90 border border-slate-700 text-slate-300 text-[10px] font-bold tracking-wider flex items-center gap-1">
            <AlertCircle className="w-3 h-3 text-cyan-400" /> BANK ONLY
          </span>
        )
    }
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      {/* Left Column: Transactions List (5 cols) */}
      <div className="lg:col-span-5 p-5 rounded-2xl bg-slate-900/90 border border-slate-800 shadow-xl backdrop-blur-sm space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            {isGLOnlyTab ? (
              <>
                <Building2 className="w-4 h-4 text-indigo-400" />
                <span>General Ledger (GL Only) Entries</span>
              </>
            ) : (
              <>
                <FileSpreadsheet className="w-4 h-4 text-emerald-400" />
                <span>Bank Statement Transactions</span>
              </>
            )}
          </h3>
          <span className="text-[11px] font-medium text-slate-400 px-2 py-0.5 rounded-full bg-slate-800">
            {isGLOnlyTab ? glOnlyEntries.length : transactions.length} Records
          </span>
        </div>

        {/* Loading State */}
        {loading && (isGLOnlyTab ? glOnlyEntries.length === 0 : transactions.length === 0) ? (
          <div className="py-12 text-center text-slate-400 space-y-2">
            <Loader2 className="w-6 h-6 animate-spin text-emerald-400 mx-auto" />
            <p className="text-xs">Fetching reconciliation records...</p>
          </div>
        ) : isGLOnlyTab ? (
          /* GL Only List */
          glOnlyEntries.length === 0 ? (
            <div className="py-12 text-center text-slate-400 space-y-2 bg-slate-950/40 rounded-xl border border-slate-800">
              <Building2 className="w-8 h-8 text-slate-600 mx-auto" />
              <p className="text-xs font-semibold text-slate-300">No GL-Only Transactions</p>
              <p className="text-[11px] text-slate-500">
                All posted general ledger entries have corresponding bank matches.
              </p>
            </div>
          ) : (
            <div className="space-y-2.5 max-h-[600px] overflow-y-auto pr-1">
              {glOnlyEntries.map((ge) => {
                const isSelected = selectedGL?.id === ge.id
                return (
                  <div
                    key={ge.id}
                    onClick={() => onSelectGLEntry?.(ge.id)}
                    className={`p-4 rounded-xl border cursor-pointer transition-all duration-150 space-y-2.5 ${
                      isSelected
                        ? 'bg-slate-900 border-indigo-500/60 shadow-lg shadow-indigo-500/10 ring-1 ring-indigo-500/20'
                        : 'bg-slate-950/40 border-slate-800/80 hover:bg-slate-900/60 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-slate-400 font-mono">
                        {formatCardDate(ge.entry_date)}
                      </span>
                      <span className="px-2 py-0.5 rounded-full bg-indigo-950/70 border border-indigo-500/30 text-indigo-400 text-[10px] font-bold tracking-wider flex items-center gap-1">
                        <Building2 className="w-3 h-3" /> GL ONLY
                      </span>
                    </div>

                    <div>
                      <h4 className="text-xs font-bold text-slate-100 line-clamp-1">
                        {ge.description}
                      </h4>
                      <p className="text-[10px] font-mono text-indigo-400 mt-0.5">
                        #JE-{ge.id.substring(0, 8)}
                      </p>
                    </div>

                    <div className="flex items-center justify-between pt-2 border-t border-slate-800/70">
                      <span className="text-[10px] text-slate-500 font-medium uppercase">
                        Posted GL
                      </span>
                      <span className="text-xs font-bold font-mono text-indigo-300">
                        {formatCardAmount(ge.total_debit || 0)}
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          )
        ) : /* Bank Transactions List */
        transactions.length === 0 ? (
          <div className="py-12 text-center text-slate-400 space-y-2 bg-slate-950/40 rounded-xl border border-slate-800">
            <FileSpreadsheet className="w-8 h-8 text-slate-600 mx-auto" />
            <p className="text-xs font-semibold text-slate-300">No Transactions Found</p>
            <p className="text-[11px] text-slate-500">
              No bank statement items match the active filter or search criteria.
            </p>
          </div>
        ) : (
          <div className="space-y-2.5 max-h-[600px] overflow-y-auto pr-1">
            {transactions.map((tx) => {
              const isSelected = selectedTx?.id === tx.id
              const matchForTx = matches.find((m) => m.bank_transaction_id === tx.id)
              const statusStr = matchForTx ? matchForTx.status : tx.status

              return (
                <div
                  key={tx.id}
                  onClick={() => onSelectTx(tx.id)}
                  className={`p-4 rounded-xl border cursor-pointer transition-all duration-150 space-y-2.5 ${
                    isSelected
                      ? 'bg-slate-900 border-emerald-500/60 shadow-lg shadow-emerald-500/10 ring-1 ring-emerald-500/20'
                      : 'bg-slate-950/40 border-slate-800/80 hover:bg-slate-900/60 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-400 font-mono">
                      {formatCardDate(tx.transaction_date)}
                    </span>
                    {getStatusBadge(statusStr)}
                  </div>

                  <div>
                    <h4 className="text-xs font-bold text-slate-100 line-clamp-1">
                      {tx.description}
                    </h4>
                    {tx.reference_number && (
                      <p className="text-[10px] font-mono text-slate-400 mt-0.5">
                        Ref: {tx.reference_number}
                      </p>
                    )}
                  </div>

                  <div className="flex items-center justify-between pt-2 border-t border-slate-800/70">
                    <span className="text-[10px] text-slate-500 font-medium uppercase">
                      {tx.currency}
                    </span>
                    <span
                      className={`text-xs font-bold font-mono ${
                        tx.amount < 0 ? 'text-rose-400' : 'text-emerald-400'
                      }`}
                    >
                      {formatCardAmount(tx.amount, tx.currency)}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Right Column: Comparative Ledger Matching Panel (7 cols) */}
      <div className="lg:col-span-7 p-5 rounded-2xl bg-slate-900/90 border border-slate-800 shadow-xl backdrop-blur-sm space-y-5">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-indigo-400" />
            <span>Reconciliation Analysis</span>
          </h3>
          <span className="text-[11px] text-slate-400">Two-Sided Matching Workspace</span>
        </div>

        {/* GL Only View in Analysis Panel */}
        {isGLOnlyTab && selectedGL ? (
          <div className="space-y-4">
            <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-wider block">
                  General Ledger Entry Detail
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-950/80 text-indigo-300 border border-indigo-500/30">
                  GL ONLY
                </span>
              </div>
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                <div>
                  <p className="font-bold text-slate-100 text-sm">{selectedGL.description}</p>
                  <p className="text-slate-400 text-[11px] font-mono mt-0.5">
                    Date: {formatCardDate(selectedGL.entry_date)} • ID: #JE-{selectedGL.id.substring(0, 8)}
                  </p>
                </div>
                <div className="text-right font-mono text-sm font-bold text-indigo-400">
                  {formatCardAmount(selectedGL.total_debit || 0)}
                </div>
              </div>
            </div>

            <div className="p-6 rounded-xl bg-slate-950/40 border border-slate-800 text-center space-y-3">
              <HelpCircle className="w-10 h-10 text-indigo-400/60 mx-auto" />
              <div>
                <p className="text-sm font-bold text-slate-200">
                  No Corresponding Bank Mutation Found
                </p>
                <p className="text-xs text-slate-400 max-w-md mx-auto mt-1 leading-relaxed">
                  This journal entry is posted in the General Ledger, but does not appear in the
                  imported bank statement. This may represent an outstanding check, pending deposit,
                  or timing difference.
                </p>
              </div>
            </div>
          </div>
        ) : selectedTx ? (
          <div className="space-y-4">
            {/* Section A: Selected Bank Transaction Card */}
            <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider block">
                  Selected Bank Statement Line
                </span>
                <span className="text-[11px] font-mono text-slate-500">
                  ID: #{selectedTx.id.substring(0, 8)}
                </span>
              </div>
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                <div>
                  <p className="font-bold text-slate-100 text-sm">{selectedTx.description}</p>
                  <p className="text-slate-400 text-[11px] font-mono mt-0.5">
                    Date: {formatCardDate(selectedTx.transaction_date)}{' '}
                    {selectedTx.reference_number && `• Ref: ${selectedTx.reference_number}`}
                  </p>
                </div>
                <div className="text-right font-mono text-sm font-bold text-emerald-400">
                  {formatCardAmount(selectedTx.amount, selectedTx.currency)}
                </div>
              </div>
            </div>

            {/* Section B: Reconciliation Analysis & Candidate GL */}
            {(() => {
              if (!selectedMatch || !selectedMatch.journal_entry) {
                // State: No GL Match Found (Bank Only)
                return (
                  <div className="p-6 rounded-xl bg-slate-950/40 border border-slate-800 text-center space-y-3">
                    <HelpCircle className="w-10 h-10 text-slate-600 mx-auto" />
                    <div>
                      <p className="text-sm font-bold text-slate-300 uppercase tracking-wider">
                        No GL Match Found
                      </p>
                      <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1 leading-relaxed">
                        No posted General Ledger transaction matched this bank mutation amount or
                        date. Run the Recon Engine or create a journal entry.
                      </p>
                    </div>
                  </div>
                )
              }

              const score = Math.round((selectedMatch.confidence_score ?? 1) * 100)
              const isExact =
                (selectedMatch.match_type === 'exact' ||
                  selectedMatch.match_rule_type === 'EXACT_MATCH' ||
                  score >= 95) &&
                selectedMatch.status !== 'proposed'

              if (isExact) {
                // State: EXACT MATCH
                return (
                  <div className="p-5 rounded-xl bg-emerald-950/20 border border-emerald-500/30 space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                        <h4 className="text-xs font-bold text-emerald-300 uppercase tracking-wider">
                          Matched GL Transaction
                        </h4>
                      </div>
                      <span className="px-2.5 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-mono">
                        ✓ EXACT MATCH (100%)
                      </span>
                    </div>

                    {/* Match Comparison Grid */}
                    <div className="grid grid-cols-2 gap-3 text-xs bg-slate-900/80 p-3.5 rounded-lg border border-slate-800">
                      <div>
                        <span className="text-slate-500 block text-[11px]">Ledger Entry ID</span>
                        <span className="font-semibold text-slate-200 font-mono">
                          #JE-{selectedMatch.journal_entry.id.substring(0, 8)}
                        </span>
                      </div>
                      <div>
                        <span className="text-slate-500 block text-[11px]">Ledger Entry Date</span>
                        <span className="font-semibold text-slate-200 font-mono">
                          {formatCardDate(selectedMatch.journal_entry.entry_date)}
                        </span>
                      </div>
                      <div className="col-span-2 border-t border-slate-800 pt-2">
                        <span className="text-slate-500 block text-[11px]">
                          Journal Description
                        </span>
                        <span className="font-semibold text-slate-100">
                          {selectedMatch.journal_entry.description}
                        </span>
                      </div>
                    </div>

                    {/* Verification Confirmation */}
                    <div className="flex items-center justify-between pt-2">
                      <div className="flex items-center gap-1.5 text-xs text-emerald-400 font-semibold">
                        <ShieldCheck className="w-4 h-4" />
                        Amounts &amp; Dates Verified Deterministically
                      </div>

                      <button
                        type="button"
                        className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs transition-all shadow-md shadow-emerald-600/20 flex items-center gap-1.5 cursor-pointer"
                      >
                        <CheckCircle2 className="w-4 h-4" /> Accept Reconciliation
                      </button>
                    </div>
                  </div>
                )
              }

              // State: POSSIBLE GL CANDIDATE / AI SUGGESTED (Review Required / Low Confidence)
              const isLowConfidence = score < 50
              const hasSignalScores =
                selectedMatch.amount_score != null ||
                selectedMatch.vendor_score != null ||
                selectedMatch.date_score != null

              return (
                <div className="p-5 rounded-xl bg-amber-950/20 border border-amber-500/30 space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-amber-400" />
                      <h4 className="text-xs font-bold text-amber-300 uppercase tracking-wider">
                        Possible GL Candidate
                      </h4>
                    </div>
                    <span
                      className={`px-2.5 py-0.5 rounded text-[10px] font-bold border font-mono ${
                        isLowConfidence
                          ? 'bg-rose-500/20 text-rose-300 border-rose-500/30'
                          : 'bg-amber-500/20 text-amber-300 border-amber-500/30'
                      }`}
                    >
                      {isLowConfidence ? `⚠ Low Confidence (${score}%)` : `Confidence: ${score}%`}
                    </span>
                  </div>

                  {/* Visual Confidence Gauge */}
                  <div className="space-y-1.5 bg-slate-900/60 p-3 rounded-lg border border-slate-800">
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="text-slate-400 font-medium">AI Match Confidence</span>
                      <span
                        className={`font-bold font-mono ${
                          isLowConfidence ? 'text-rose-400' : 'text-amber-400'
                        }`}
                      >
                        {score}%
                      </span>
                    </div>
                    <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-300 ${
                          isLowConfidence
                            ? 'bg-gradient-to-r from-rose-500 to-amber-500'
                            : 'bg-gradient-to-r from-amber-500 to-yellow-400'
                        }`}
                        style={{ width: `${Math.max(5, score)}%` }}
                      />
                    </div>
                  </div>

                  {/* Candidate GL Details */}
                  <div className="grid grid-cols-2 gap-3 text-xs bg-slate-900/80 p-3.5 rounded-lg border border-slate-800">
                    <div>
                      <span className="text-slate-500 block text-[11px]">Candidate Journal ID</span>
                      <span className="font-semibold text-slate-200 font-mono">
                        #JE-{selectedMatch.journal_entry.id.substring(0, 8)}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[11px]">Ledger Entry Date</span>
                      <span className="font-semibold text-slate-200 font-mono">
                        {formatCardDate(selectedMatch.journal_entry.entry_date)}
                      </span>
                    </div>
                    <div className="col-span-2 border-t border-slate-800 pt-2">
                      <span className="text-slate-500 block text-[11px]">
                        Journal Description
                      </span>
                      <span className="font-semibold text-slate-100">
                        {selectedMatch.journal_entry.description}
                      </span>
                    </div>
                  </div>

                  {/* Match Signals (shown only if available from backend) */}
                  {hasSignalScores && (
                    <div className="space-y-2 bg-slate-900/80 p-3 rounded-lg border border-slate-800">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                        Match Signals
                      </span>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px]">
                        {selectedMatch.amount_score != null && (
                          <div
                            className={`flex items-center gap-1.5 ${
                              selectedMatch.amount_score >= 0.9 ? 'text-emerald-400' : 'text-rose-400'
                            }`}
                          >
                            {selectedMatch.amount_score >= 0.9 ? '✓' : '✕'}{' '}
                            <span>Similar amount</span>
                          </div>
                        )}
                        {selectedMatch.vendor_score != null && (
                          <div
                            className={`flex items-center gap-1.5 ${
                              selectedMatch.vendor_score >= 0.7 ? 'text-emerald-400' : 'text-amber-400'
                            }`}
                          >
                            {selectedMatch.vendor_score >= 0.7 ? '✓' : '⚠'}{' '}
                            <span>Vendor/Memo</span>
                          </div>
                        )}
                        {selectedMatch.date_score != null && (
                          <div
                            className={`flex items-center gap-1.5 ${
                              selectedMatch.date_score >= 0.8 ? 'text-emerald-400' : 'text-amber-400'
                            }`}
                          >
                            {selectedMatch.date_score >= 0.8 ? '✓' : '⚠'}{' '}
                            <span>Date alignment</span>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* AI Rationale / Explanation */}
                  {(selectedMatch.rationale || selectedMatch.match_explanation) && (
                    <div className="text-xs text-slate-300 bg-slate-900/90 p-3 rounded-lg border border-slate-800 italic flex items-start gap-2">
                      <Info className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                      <span>"{selectedMatch.rationale || selectedMatch.match_explanation}"</span>
                    </div>
                  )}

                  {/* Actions Bar for Possible Match */}
                  <div className="flex items-center justify-between pt-2 border-t border-slate-800/80">
                    <span className="text-[11px] text-amber-400 font-medium">
                      Human confirmation required
                    </span>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold transition-colors cursor-pointer"
                      >
                        Mark Unmatched
                      </button>
                      <button
                        type="button"
                        className="px-3.5 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold transition-colors shadow-md shadow-amber-600/20 flex items-center gap-1.5 cursor-pointer"
                      >
                        <CheckCircle2 className="w-3.5 h-3.5" /> Confirm Match
                      </button>
                    </div>
                  </div>
                </div>
              )
            })()}
          </div>
        ) : (
          <div className="py-20 text-center text-slate-400 space-y-2 bg-slate-950/40 rounded-xl border border-slate-800">
            <ArrowRight className="w-8 h-8 text-slate-600 mx-auto" />
            <p className="text-xs font-semibold text-slate-300">Select a Bank Transaction</p>
            <p className="text-[11px] text-slate-500">
              Click any transaction on the left list to view matching ledger details.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

