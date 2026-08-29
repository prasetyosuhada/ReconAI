import React, { useState } from 'react'
import { Download, History, Lock, PartyPopper, Sparkles, Unlock } from 'lucide-react'
import type {
  BankStatementImportResponse,
  BankTransactionResponse,
  ReconciliationMatchResponse,
} from '../../services/api'

interface ReconciliationCompletionBannerProps {
  isComplete: boolean
  statementPeriod: string
  activeImport?: BankStatementImportResponse
  transactions: BankTransactionResponse[]
  matches: ReconciliationMatchResponse[]
  onOpenAuditTrail: () => void
}

export const ReconciliationCompletionBanner: React.FC<ReconciliationCompletionBannerProps> = ({
  isComplete,
  statementPeriod,
  activeImport,
  transactions,
  matches,
  onOpenAuditTrail,
}) => {
  const [isLocked, setIsLocked] = useState<boolean>(false)

  if (!isComplete) return null

  const handleDownloadReport = () => {
    // Generate and download CSV report
    const headers = [
      'Transaction Date',
      'Description',
      'Reference',
      'Amount',
      'Currency',
      'Status',
      'Match Type',
    ]
    const rows = transactions.map((t) => {
      const match = matches.find((m) => m.bank_transaction_id === t.id)
      return [
        t.transaction_date,
        `"${t.description.replace(/"/g, '""')}"`,
        t.reference_number || '',
        t.amount,
        t.currency,
        match?.status || t.status,
        match?.match_rule_type || match?.match_type || 'EXACT',
      ].join(',')
    })
    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows].join('\n')
    const encodedUri = encodeURI(csvContent)
    const link = document.createElement('a')
    link.setAttribute('href', encodedUri)
    link.setAttribute(
      'download',
      `Reconciliation_Report_${activeImport?.original_filename || 'Statement'}.csv`
    )
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  return (
    <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-emerald-950/80 via-slate-900 to-teal-950/80 border border-emerald-500/40 p-6 shadow-2xl backdrop-blur-md animate-in fade-in zoom-in-95 duration-300">
      {/* Background ambient lighting */}
      <div className="absolute -top-12 -right-12 w-48 h-48 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute -bottom-12 -left-12 w-48 h-48 bg-teal-500/10 rounded-full blur-3xl pointer-events-none" />

      <div className="relative flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="flex items-start gap-4">
          <div className="p-3.5 rounded-2xl bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 shrink-0 shadow-lg shadow-emerald-500/10">
            <PartyPopper className="w-7 h-7" />
          </div>
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <h3 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
                Reconciliation Complete
                <Sparkles className="w-4 h-4 text-emerald-400" />
              </h3>
              <span className="px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-[11px] font-bold font-mono">
                100% Balanced
              </span>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed max-w-xl">
              Statement period{' '}
              <span className="font-semibold text-emerald-300 font-mono">{statementPeriod}</span> is
              fully reconciled with a difference of{' '}
              <span className="font-bold text-emerald-400 font-mono">Rp0</span>. All bank mutations
              have verified ledger entries.
            </p>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center gap-2.5 shrink-0">
          <button
            type="button"
            onClick={() => setIsLocked(!isLocked)}
            className={`px-3.5 py-2 rounded-xl border text-xs font-semibold transition-all flex items-center gap-1.5 cursor-pointer shadow-md ${
              isLocked
                ? 'bg-amber-950/70 border-amber-500/40 text-amber-300 shadow-amber-900/20'
                : 'bg-slate-800/80 hover:bg-slate-800 border-slate-700 text-slate-200 hover:border-slate-600'
            }`}
          >
            {isLocked ? (
              <>
                <Lock className="w-3.5 h-3.5 text-amber-400" /> Period Locked
              </>
            ) : (
              <>
                <Unlock className="w-3.5 h-3.5 text-slate-400" /> Lock Statement Period
              </>
            )}
          </button>

          <button
            type="button"
            onClick={handleDownloadReport}
            className="px-3.5 py-2 rounded-xl bg-slate-800/80 hover:bg-slate-800 border border-slate-700 text-slate-200 hover:border-slate-600 text-xs font-semibold transition-all flex items-center gap-1.5 cursor-pointer shadow-md"
          >
            <Download className="w-3.5 h-3.5 text-emerald-400" /> Download Report
          </button>

          <button
            type="button"
            onClick={onOpenAuditTrail}
            className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold transition-all flex items-center gap-1.5 shadow-lg shadow-emerald-600/20 cursor-pointer"
          >
            <History className="w-3.5 h-3.5" /> View Audit Trail
          </button>
        </div>
      </div>
    </div>
  )
}
