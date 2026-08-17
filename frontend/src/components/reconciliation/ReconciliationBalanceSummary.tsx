import React from 'react'
import {
  AlertTriangle,
  ArrowRightLeft,
  CheckCircle2,
  PieChart,
  Scale,
  TrendingUp,
} from 'lucide-react'
import type { BankTransactionResponse, ReconciliationMatchResponse } from '../../services/api'

interface ReconciliationBalanceSummaryProps {
  transactions: BankTransactionResponse[]
  matches: ReconciliationMatchResponse[]
  totalCount: number
  matchedCount: number
  proposedCount: number
  unmatchedCount: number
  loading?: boolean
}

function formatIDR(value: number): string {
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}

export const ReconciliationBalanceSummary: React.FC<ReconciliationBalanceSummaryProps> = ({
  transactions,
  matches,
  totalCount,
  matchedCount,
  proposedCount,
  unmatchedCount,
  loading = false,
}) => {
  // Calculate Bank Statement Volume / Balance
  const bankStatementBalance = transactions.reduce(
    (acc, t) => acc + Math.abs(Number(t.amount) || 0),
    0
  )

  // Calculate Reconciled GL Volume (from accepted/matched entries)
  const glBalance = matches
    .filter((m) => m.status === 'accepted' || m.status === 'matched')
    .reduce((acc, m) => {
      const tx = transactions.find((t) => t.id === m.bank_transaction_id)
      return acc + (tx ? Math.abs(Number(tx.amount) || 0) : 0)
    }, 0)

  const difference = Math.abs(bankStatementBalance - glBalance)
  const isReconciled =
    totalCount > 0 &&
    unmatchedCount === 0 &&
    proposedCount === 0 &&
    matchedCount === totalCount &&
    difference < 1

  const progressPercentage =
    totalCount > 0 ? Math.min(100, Math.max(0, (matchedCount / totalCount) * 100)) : 0

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      {/* 1. Reconciliation Balance Summary (2 cols on large screen) */}
      <div className="lg:col-span-2 p-5 rounded-2xl bg-gradient-to-br from-slate-900 via-slate-900 to-slate-950 border border-slate-800 shadow-xl relative overflow-hidden flex flex-col justify-between">
        <div className="flex items-center justify-between border-b border-slate-800/80 pb-3 mb-4">
          <div className="flex items-center gap-2 text-slate-300 font-bold text-xs uppercase tracking-wider">
            <Scale className="w-4 h-4 text-emerald-400" />
            <span>Reconciliation Balance</span>
          </div>
          <div>
            {totalCount === 0 ? (
              <span className="px-2.5 py-1 rounded-full text-[11px] font-semibold bg-slate-800 text-slate-400 border border-slate-700">
                No Statement Loaded
              </span>
            ) : isReconciled ? (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-950/80 text-emerald-300 border border-emerald-500/30">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                Reconciled
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-950/80 text-amber-300 border border-amber-500/30">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                Review Required
              </span>
            )}
          </div>
        </div>

        {/* 3-Part Metric Comparison */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 py-1">
          {/* Bank Statement Balance */}
          <div className="p-3.5 rounded-xl bg-slate-800/40 border border-slate-700/50">
            <div className="text-[11px] text-slate-400 font-medium mb-1 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-cyan-400" />
              Bank Statement Balance
            </div>
            <div className="text-lg sm:text-xl font-bold text-white tracking-tight">
              {loading ? '...' : formatIDR(bankStatementBalance)}
            </div>
            <div className="text-[10px] text-slate-500 mt-1">
              {totalCount} transaction{totalCount !== 1 ? 's' : ''} total
            </div>
          </div>

          {/* GL Balance */}
          <div className="p-3.5 rounded-xl bg-slate-800/40 border border-slate-700/50">
            <div className="text-[11px] text-slate-400 font-medium mb-1 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-indigo-400" />
              General Ledger Balance
            </div>
            <div className="text-lg sm:text-xl font-bold text-white tracking-tight">
              {loading ? '...' : formatIDR(glBalance)}
            </div>
            <div className="text-[10px] text-slate-500 mt-1">
              {matchedCount} matched item{matchedCount !== 1 ? 's' : ''}
            </div>
          </div>

          {/* Difference */}
          <div
            className={`p-3.5 rounded-xl border transition-all ${
              difference < 1
                ? 'bg-emerald-950/20 border-emerald-500/30 text-emerald-400'
                : 'bg-amber-950/20 border-amber-500/30 text-amber-400'
            }`}
          >
            <div className="text-[11px] font-medium mb-1 flex items-center gap-1.5 opacity-90">
              <ArrowRightLeft className="w-3.5 h-3.5" />
              Difference
            </div>
            <div className="text-lg sm:text-xl font-bold tracking-tight">
              {loading ? '...' : formatIDR(difference)}
            </div>
            <div className="text-[10px] mt-1 font-medium opacity-80">
              {difference < 1
                ? '✓ Balances agree (Rp0)'
                : `⚠ ${unmatchedCount + proposedCount} open item(s) pending`}
            </div>
          </div>
        </div>
      </div>

      {/* 2. Reconciliation Progress (1 col on large screen) */}
      <div className="p-5 rounded-2xl bg-gradient-to-br from-slate-900 via-slate-900 to-slate-950 border border-slate-800 shadow-xl flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-3 mb-4">
            <div className="flex items-center gap-2 text-slate-300 font-bold text-xs uppercase tracking-wider">
              <PieChart className="w-4 h-4 text-emerald-400" />
              <span>Reconciliation Progress</span>
            </div>
            <span className="text-xs font-semibold text-slate-400">
              {matchedCount}/{totalCount} Reconciled
            </span>
          </div>

          {/* Percentage & Bar */}
          <div className="space-y-3 mt-2">
            <div className="flex items-baseline justify-between">
              <span className="text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-teal-300 tracking-tight">
                {progressPercentage.toFixed(1)}%
              </span>
              <span className="text-xs text-slate-400 font-medium">
                {totalCount - matchedCount} remaining
              </span>
            </div>

            {/* Progress Track */}
            <div className="w-full h-3.5 rounded-full bg-slate-800/90 border border-slate-700/60 p-0.5 overflow-hidden shadow-inner">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  progressPercentage >= 100
                    ? 'bg-gradient-to-r from-emerald-500 to-teal-400 shadow-sm shadow-emerald-500/50'
                    : progressPercentage > 0
                      ? 'bg-gradient-to-r from-emerald-600 via-teal-500 to-cyan-400'
                      : 'bg-transparent'
                }`}
                style={{ width: `${progressPercentage}%` }}
              />
            </div>
          </div>
        </div>

        {/* Footnote status */}
        <div className="mt-4 pt-3 border-t border-slate-800/80 text-[11px] text-slate-400 flex items-center justify-between">
          {isReconciled ? (
            <span className="text-emerald-400 font-medium flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5" /> All transactions reconciled
            </span>
          ) : totalCount === 0 ? (
            <span className="text-slate-500">No active statement to reconcile</span>
          ) : (
            <span className="text-slate-400 flex items-center gap-1.5">
              <TrendingUp className="w-3.5 h-3.5 text-cyan-400" />
              <span>
                {matchedCount} of {totalCount} transactions reconciled
              </span>
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
