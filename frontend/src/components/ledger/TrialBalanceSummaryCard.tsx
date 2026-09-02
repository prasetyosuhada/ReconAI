import React, { useState } from 'react'
import {
  AlertTriangle,
  BookOpen,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react'
import type { TrialBalanceResponse } from '../../services/api'

interface TrialBalanceSummaryCardProps {
  trialBalance: TrialBalanceResponse | null
  loading: boolean
  onRefresh: () => void
}

export const TrialBalanceSummaryCard: React.FC<TrialBalanceSummaryCardProps> = ({
  trialBalance,
  loading,
  onRefresh,
}) => {
  const [isExpanded, setIsExpanded] = useState(false)

  const isBalanced = trialBalance?.status === 'balanced'
  const totalDebits = trialBalance?.total_debits || 0
  const totalCredits = trialBalance?.total_credits || 0
  const difference = trialBalance?.difference || 0

  return (
    <div className="p-6 rounded-2xl bg-slate-800/40 border border-slate-700/50 shadow-xl backdrop-blur-sm space-y-4">
      {/* Top Bar: Title & Balance Status */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
            <BookOpen className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              Trial Balance Integrity Report
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Deterministic verification of double-entry ledger balance as of{' '}
              <span className="font-mono text-slate-300">
                {trialBalance?.as_of_date || new Date().toISOString().split('T')[0]}
              </span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 w-full sm:w-auto justify-between sm:justify-end">
          {isBalanced ? (
            <div className="px-3.5 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-bold flex items-center gap-1.5 shadow-sm shadow-emerald-500/10">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              BALANCED
            </div>
          ) : (
            <div className="px-3.5 py-1.5 rounded-full bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs font-bold flex items-center gap-1.5 shadow-sm shadow-rose-500/10">
              <AlertTriangle className="w-4 h-4 text-rose-400" />
              UNBALANCED (Δ {difference.toLocaleString()} IDR)
            </div>
          )}

          <button
            type="button"
            onClick={onRefresh}
            disabled={loading}
            className="p-2 rounded-xl bg-slate-900/80 hover:bg-slate-800 border border-slate-700/60 text-slate-300 hover:text-white transition-all disabled:opacity-50"
            title="Recalculate trial balance"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2">
        <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-1">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
            Total Ledger Debits
          </span>
          <div className="text-xl font-bold text-emerald-400 font-mono">
            IDR {totalDebits.toLocaleString()}
          </div>
        </div>

        <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-1">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
            Total Ledger Credits
          </span>
          <div className="text-xl font-bold text-indigo-400 font-mono">
            IDR {totalCredits.toLocaleString()}
          </div>
        </div>

        <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-1">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
            Net Imbalance Difference
          </span>
          <div
            className={`text-xl font-bold font-mono ${
              difference === 0 ? 'text-slate-400' : 'text-rose-400'
            }`}
          >
            IDR {difference.toLocaleString()}
          </div>
        </div>
      </div>

      {/* Toggle Account Breakdown Table */}
      {trialBalance?.accounts && trialBalance.accounts.length > 0 && (
        <div className="pt-2">
          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-xs font-semibold text-indigo-400 hover:text-indigo-300 flex items-center gap-1 transition-colors"
          >
            {isExpanded ? (
              <>
                <ChevronUp className="w-4 h-4" /> Hide Account Balances Breakdown (
                {trialBalance.accounts.length} COA)
              </>
            ) : (
              <>
                <ChevronDown className="w-4 h-4" /> View Account Balances Breakdown (
                {trialBalance.accounts.length} COA)
              </>
            )}
          </button>

          {isExpanded && (
            <div className="mt-3 overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/60">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-900 text-slate-400 border-b border-slate-800 font-semibold uppercase text-[10px]">
                  <tr>
                    <th className="py-2.5 px-4">Code</th>
                    <th className="py-2.5 px-4">Account Name</th>
                    <th className="py-2.5 px-4">Type</th>
                    <th className="py-2.5 px-4 text-right">Debit Balance</th>
                    <th className="py-2.5 px-4 text-right">Credit Balance</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/80 font-mono">
                  {trialBalance.accounts.map((ac) => (
                    <tr key={ac.account_code} className="hover:bg-slate-900/60 transition-colors">
                      <td className="py-2.5 px-4 font-bold text-slate-200">{ac.account_code}</td>
                      <td className="py-2.5 px-4 font-sans text-slate-300">{ac.account_name}</td>
                      <td className="py-2.5 px-4 font-sans capitalize text-slate-400">
                        <span className="px-2 py-0.5 rounded bg-slate-800 text-[11px] border border-slate-700/60">
                          {ac.account_type}
                        </span>
                      </td>
                      <td className="py-2.5 px-4 text-right font-bold text-emerald-400">
                        {ac.debit_balance > 0 ? ac.debit_balance.toLocaleString() : '-'}
                      </td>
                      <td className="py-2.5 px-4 text-right font-bold text-indigo-400">
                        {ac.credit_balance > 0 ? ac.credit_balance.toLocaleString() : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
