import React from 'react'
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Clock,
  FileSpreadsheet,
  HelpCircle,
  Info,
  Loader2,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import type { BankTransactionResponse, ReconciliationMatchResponse } from '../../services/api'

interface Reconciliation2ColumnViewProps {
  transactions: BankTransactionResponse[]
  matches: ReconciliationMatchResponse[]
  loading: boolean
  selectedTxId: string | null
  onSelectTx: (txId: string) => void
}

export const Reconciliation2ColumnView: React.FC<Reconciliation2ColumnViewProps> = ({
  transactions,
  matches,
  loading,
  selectedTxId,
  onSelectTx,
}) => {
  const selectedTx = transactions.find((t) => t.id === selectedTxId) || transactions[0]
  const selectedMatch = matches.find(
    (m) => m.bank_transaction_id === (selectedTx ? selectedTx.id : '')
  )

  const getStatusBadge = (status: string) => {
    switch (status.toLowerCase()) {
      case 'matched':
      case 'accepted':
        return (
          <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[10px] font-bold uppercase tracking-wider flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3" /> Matched
          </span>
        )
      case 'proposed':
        return (
          <span className="px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-400 text-[10px] font-bold uppercase tracking-wider flex items-center gap-1">
            <Clock className="w-3 h-3" /> Review Match
          </span>
        )
      default:
        return (
          <span className="px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-400 text-[10px] font-bold uppercase tracking-wider">
            Unmatched
          </span>
        )
    }
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      {/* Left Column: Bank Statement Transactions List (5 cols) */}
      <div className="lg:col-span-5 p-5 rounded-2xl bg-slate-800/40 border border-slate-700/50 shadow-xl backdrop-blur-sm space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <FileSpreadsheet className="w-4 h-4 text-emerald-400" />
            Bank Transactions Mutasi
          </h3>
          <span className="text-[11px] text-slate-400">{transactions.length} Records</span>
        </div>

        {loading && transactions.length === 0 ? (
          <div className="py-12 text-center text-slate-400 space-y-2">
            <Loader2 className="w-6 h-6 animate-spin text-emerald-400 mx-auto" />
            <p className="text-xs">Fetching bank statement items...</p>
          </div>
        ) : transactions.length === 0 ? (
          <div className="py-12 text-center text-slate-400 space-y-2 bg-slate-900/40 rounded-xl border border-slate-800">
            <FileSpreadsheet className="w-8 h-8 text-slate-600 mx-auto" />
            <p className="text-xs font-semibold text-slate-300">No Bank Transactions</p>
            <p className="text-[11px] text-slate-500">
              Import a CSV statement to populate this list.
            </p>
          </div>
        ) : (
          <div className="space-y-2 max-h-[600px] overflow-y-auto pr-1">
            {transactions.map((tx) => {
              const isSelected = selectedTx?.id === tx.id
              const matchForTx = matches.find((m) => m.bank_transaction_id === tx.id)
              const statusStr = matchForTx ? matchForTx.status : tx.status

              return (
                <div
                  key={tx.id}
                  onClick={() => onSelectTx(tx.id)}
                  className={`p-3.5 rounded-xl border cursor-pointer transition-all duration-150 space-y-2 ${
                    isSelected
                      ? 'bg-slate-900 border-indigo-500/60 shadow-md shadow-indigo-500/10 scale-[1.01]'
                      : 'bg-slate-950/40 border-slate-800/80 hover:bg-slate-900/60'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-mono text-slate-400 font-semibold">
                      {tx.transaction_date}
                    </span>
                    {getStatusBadge(statusStr)}
                  </div>

                  <div>
                    <h4 className="text-xs font-semibold text-slate-200 line-clamp-1">
                      {tx.description}
                    </h4>
                    {tx.reference_number && (
                      <p className="text-[10px] font-mono text-slate-500 mt-0.5">
                        Ref: {tx.reference_number}
                      </p>
                    )}
                  </div>

                  <div className="flex items-center justify-between pt-1 border-t border-slate-800/60">
                    <span className="text-[11px] text-slate-500 font-mono">{tx.currency}</span>
                    <span
                      className={`text-xs font-bold font-mono ${
                        tx.amount < 0 ? 'text-rose-400' : 'text-emerald-400'
                      }`}
                    >
                      {tx.amount > 0
                        ? `+${tx.amount.toLocaleString()}`
                        : tx.amount.toLocaleString()}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Right Column: Comparative Ledger Matching Panel (7 cols) */}
      <div className="lg:col-span-7 p-5 rounded-2xl bg-slate-800/40 border border-slate-700/50 shadow-xl backdrop-blur-sm space-y-5">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-indigo-400" />
            General Ledger Match Candidate
          </h3>
          <span className="text-[11px] text-slate-400">Reconciliation Analysis</span>
        </div>

        {selectedTx ? (
          <div className="space-y-4">
            {/* Selected Bank Transaction Card */}
            <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-2">
              <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider block">
                Selected Bank Statement Line
              </span>
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                <div>
                  <p className="font-bold text-slate-100">{selectedTx.description}</p>
                  <p className="text-slate-400 text-[11px] font-mono mt-0.5">
                    Date: {selectedTx.transaction_date}{' '}
                    {selectedTx.reference_number && `• Ref: ${selectedTx.reference_number}`}
                  </p>
                </div>
                <div className="text-right font-mono text-sm font-bold text-emerald-400">
                  {selectedTx.amount.toLocaleString()} {selectedTx.currency}
                </div>
              </div>
            </div>

            {/* Match Candidate Details */}
            {selectedMatch && selectedMatch.journal_entry ? (
              <div className="p-5 rounded-xl bg-indigo-950/20 border border-indigo-500/30 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-indigo-400" />
                    <h4 className="text-xs font-bold text-indigo-200">
                      Matched Journal Entry [{selectedMatch.journal_entry.id.substring(0, 8)}...]
                    </h4>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-mono">
                    Score: {Math.round((selectedMatch.confidence_score || 1) * 100)}%
                  </span>
                </div>

                {/* Match Comparison Grid */}
                <div className="grid grid-cols-2 gap-3 text-xs bg-slate-900/80 p-3 rounded-lg border border-slate-800">
                  <div>
                    <span className="text-slate-500 block text-[11px]">Ledger Entry Date</span>
                    <span className="font-semibold text-slate-200 font-mono">
                      {selectedMatch.journal_entry.entry_date}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[11px]">Matching Rule</span>
                    <span className="font-semibold text-indigo-300 uppercase text-[10px]">
                      {selectedMatch.match_rule_type || 'EXACT_MATCH'}
                    </span>
                  </div>
                  <div className="col-span-2 border-t border-slate-800 pt-2">
                    <span className="text-slate-500 block text-[11px]">Journal Description</span>
                    <span className="font-semibold text-slate-100">
                      {selectedMatch.journal_entry.description}
                    </span>
                  </div>
                </div>

                {/* Explanation text */}
                {selectedMatch.match_explanation && (
                  <div className="text-xs text-slate-300 bg-slate-900/90 p-3 rounded-lg border border-slate-800 italic flex items-start gap-2">
                    <Info className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
                    <span>"{selectedMatch.match_explanation}"</span>
                  </div>
                )}

                {/* Match Verification Confirmation */}
                <div className="flex items-center justify-between pt-2">
                  <div className="flex items-center gap-1.5 text-xs text-emerald-400 font-semibold">
                    <ShieldCheck className="w-4 h-4" />
                    Amounts & Dates Verified Deterministically
                  </div>

                  <button
                    type="button"
                    className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs transition-all shadow-md shadow-emerald-600/20 flex items-center gap-1.5"
                  >
                    <CheckCircle2 className="w-4 h-4" /> Accept Reconciliation
                  </button>
                </div>
              </div>
            ) : (
              <div className="p-8 text-center text-slate-400 space-y-3 bg-slate-950/40 rounded-xl border border-slate-800">
                <HelpCircle className="w-10 h-10 text-slate-600 mx-auto" />
                <div>
                  <p className="text-sm font-semibold text-slate-300">No Match Candidate Found</p>
                  <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1">
                    No posted journal entry matched this bank mutation exact amount or date. Run the
                    Recon Engine or check review queue.
                  </p>
                </div>
              </div>
            )}
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
