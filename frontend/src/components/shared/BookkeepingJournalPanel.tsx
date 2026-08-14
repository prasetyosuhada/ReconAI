import React from 'react'
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  Scale,
  ShieldAlert,
  Sparkles,
  XCircle,
} from 'lucide-react'
import type { JournalLineEditPayload } from '../../services/api'

export interface BookkeepingLine extends JournalLineEditPayload {
  id?: string
  line_number?: number
  confidence?: number
  confidence_score?: number
  account_type?: string
  is_sensitive?: boolean
}

interface SourceLineItem {
  description?: string
  name?: string
  item?: string
  amount?: number
  total?: number
  line_total?: number
}

interface BookkeepingJournalPanelProps {
  vendorName: string
  transactionDate?: string
  totalAmount: number
  currency?: string
  sourceLineItems?: SourceLineItem[]
  lines: BookkeepingLine[]
  confidenceScore: number
  rationale?: string
  riskFlags?: string[]
  isEditing?: boolean
  onLineChange?: (
    index: number,
    field: keyof JournalLineEditPayload,
    value: string | number
  ) => void
  onRemoveLine?: (index: number) => void
  onAddLine?: () => void
  emptyMessage?: string
}

const formatMoney = (value: number, currency = 'IDR') => {
  if (!value) return `${currency} -`
  return `${currency} ${Number(value).toLocaleString('id-ID')}`
}

const confidenceColor = (pct: number) => {
  if (pct >= 90) return 'text-emerald-400'
  if (pct >= 75) return 'text-amber-400'
  return 'text-rose-400'
}

const confidenceBg = (pct: number) => {
  if (pct >= 90) return 'bg-emerald-400'
  if (pct >= 75) return 'bg-amber-400'
  return 'bg-rose-400'
}

const accountTypeLabel = (type?: string) => {
  const map: Record<string, string> = {
    asset: 'Asset',
    liability: 'Liability',
    equity: 'Equity',
    revenue: 'Revenue',
    expense: 'Expense',
  }
  return map[type?.toLowerCase() || ''] || type || 'Account'
}

const roleLabel = (line: BookkeepingLine, index: number): string => {
  const desc = line.description?.toLowerCase() || ''
  if (desc.includes('expense') || desc.includes('cost') || desc.includes('supplies')) {
    return 'Expense Account'
  }
  if (desc.includes('vat') || desc.includes('tax') || desc.includes('ppn')) {
    return 'Tax Account'
  }
  if (desc.includes('bank') || desc.includes('cash') || desc.includes('payment')) {
    return 'Payment Account'
  }
  if (line.debit_amount > 0 && line.credit_amount === 0) {
    return index === 0 ? 'Expense Account' : 'Debit Account'
  }
  if (line.credit_amount > 0 && line.debit_amount === 0) return 'Payment Account'
  return `Account ${index + 1}`
}

export const BookkeepingJournalPanel: React.FC<BookkeepingJournalPanelProps> = ({
  vendorName,
  transactionDate,
  totalAmount,
  currency = 'IDR',
  sourceLineItems = [],
  lines,
  confidenceScore,
  rationale,
  riskFlags = [],
  isEditing = false,
  onLineChange,
  onRemoveLine,
  onAddLine,
  emptyMessage = 'No journal entry lines available.',
}) => {
  const totalDebits = lines.reduce((sum, line) => sum + (Number(line.debit_amount) || 0), 0)
  const totalCredits = lines.reduce((sum, line) => sum + (Number(line.credit_amount) || 0), 0)
  const balanceDiff = Math.abs(totalDebits - totalCredits)
  const isBalanced = balanceDiff < 0.01

  return (
    <>
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(200px,0.85fr)_minmax(340px,1.4fr)_minmax(240px,0.95fr)] border-b border-slate-800">
        <section className="border-b xl:border-b-0 xl:border-r border-slate-800 p-4 sm:p-5 bg-slate-950/40">
          <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-4">
            Transaction
          </p>

          <div className="space-y-4">
            <div>
              <p className="text-[10px] text-slate-600 uppercase tracking-wider font-semibold mb-0.5">
                Vendor
              </p>
              <p className="text-sm font-bold text-white leading-snug">{vendorName}</p>
            </div>

            <div>
              <p className="text-[10px] text-slate-600 uppercase tracking-wider font-semibold mb-0.5">
                Date
              </p>
              <p className="text-sm font-semibold text-slate-200">
                {transactionDate
                  ? new Date(transactionDate).toLocaleDateString('en-GB', {
                      day: '2-digit',
                      month: 'short',
                      year: 'numeric',
                    })
                  : '-'}
              </p>
            </div>

            <div>
              <p className="text-[10px] text-slate-600 uppercase tracking-wider font-semibold mb-0.5">
                Total
              </p>
              <p className="text-base font-bold text-emerald-300 font-mono">
                {formatMoney(totalAmount, currency)}
              </p>
            </div>

            {sourceLineItems.length > 0 && (
              <>
                <div className="border-t border-slate-800" />
                <div>
                  <p className="text-[10px] text-slate-600 uppercase tracking-wider font-semibold mb-2">
                    Line Items
                  </p>
                  <div className="space-y-2">
                    {sourceLineItems.map((lineItem, index) => {
                      const desc =
                        lineItem.description ||
                        lineItem.name ||
                        lineItem.item ||
                        `Item ${index + 1}`
                      const amount = lineItem.amount ?? lineItem.total ?? lineItem.line_total ?? 0
                      return (
                        <div
                          key={`${desc}-${index}`}
                          className="flex items-start justify-between gap-2 text-xs"
                        >
                          <span className="text-slate-300 leading-snug flex-1 min-w-0 truncate">
                            {desc}
                          </span>
                          <span className="font-mono text-slate-200 shrink-0 text-right">
                            {Number(amount).toLocaleString('id-ID')}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              </>
            )}
          </div>
        </section>

        <section className="border-b xl:border-b-0 xl:border-r border-slate-800 p-4 sm:p-5 bg-slate-900">
          <div className="flex items-center justify-between gap-3 mb-4">
            <p className="text-[10px] font-bold uppercase tracking-widest text-indigo-400 flex items-center gap-1.5">
              <BookOpen className="w-3.5 h-3.5" />
              AI Accounting Classification
            </p>
            <div
              className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                isBalanced
                  ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
                  : 'bg-rose-500/10 border-rose-500/20 text-rose-400'
              }`}
            >
              <Scale className="w-3 h-3" />
              {isBalanced ? 'Balanced' : 'Unbalanced'}
            </div>
          </div>

          {lines.length > 0 ? (
            <div className="space-y-3">
              {lines.map((line, index) => {
                const rawConf = line.confidence ?? line.confidence_score ?? confidenceScore / 100
                const pct = rawConf <= 1 ? Math.round(rawConf * 100) : Math.round(rawConf)
                return (
                  <div
                    key={`${line.account_code}-${index}`}
                    className="rounded-xl border border-slate-700/70 bg-slate-900/60 px-4 py-3"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-0.5">
                          {roleLabel(line, index)}
                        </p>
                        <p className="text-sm font-bold text-white leading-snug truncate">
                          {line.account_name || 'Unknown Account'}
                        </p>
                        <p className="text-xs text-slate-400 font-mono mt-0.5">
                          {line.account_code || '-'} -{' '}
                          <span className="capitalize">{accountTypeLabel(line.account_type)}</span>
                          {line.is_sensitive && (
                            <span className="ml-1.5 inline-flex items-center gap-0.5 text-amber-400">
                              <ShieldAlert className="w-3 h-3" /> Sensitive
                            </span>
                          )}
                        </p>
                      </div>
                      <span
                        className={`inline-flex items-center gap-1 font-bold text-xs ${confidenceColor(
                          pct
                        )}`}
                      >
                        <span
                          className={`inline-block w-1.5 h-1.5 rounded-full ${confidenceBg(pct)}`}
                        />
                        {pct}%
                      </span>
                    </div>
                    <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden mt-3">
                      <div
                        className={`h-full rounded-full ${confidenceBg(
                          pct
                        )} transition-all duration-500`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-slate-700 p-6 text-center">
              <BookOpen className="w-8 h-8 text-slate-700 mx-auto mb-2" />
              <p className="text-xs text-slate-500">{emptyMessage}</p>
            </div>
          )}

          {riskFlags.length > 0 && (
            <div className="mt-4 rounded-xl bg-amber-500/8 border border-amber-500/20 p-3 space-y-1.5">
              <p className="text-[10px] font-bold uppercase tracking-wider text-amber-400 mb-1.5 flex items-center gap-1">
                <AlertTriangle className="w-3.5 h-3.5" />
                Risk Flags
              </p>
              {riskFlags.map((flag) => (
                <p key={flag} className="text-xs text-amber-200">
                  {flag.replace(/_/g, ' ')}
                </p>
              ))}
            </div>
          )}
        </section>

        <section className="p-4 sm:p-5 bg-slate-950/55">
          <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-4 flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
            AI Reasoning
          </p>

          <div className="mb-5">
            <div className="flex items-end justify-between mb-2">
              <span className="text-xs text-slate-500 font-semibold">Overall Confidence</span>
              <span className={`text-xl font-bold ${confidenceColor(confidenceScore)}`}>
                {confidenceScore}%
              </span>
            </div>
            <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full ${confidenceBg(
                  confidenceScore
                )} transition-all duration-700`}
                style={{ width: `${confidenceScore}%` }}
              />
            </div>
            <p className="text-[10px] text-slate-600 mt-1.5">
              {confidenceScore >= 85
                ? 'High confidence - ready for final posting.'
                : confidenceScore >= 75
                  ? 'Moderate confidence - review recommended.'
                  : 'Low confidence - manual review required.'}
            </p>
          </div>

          <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-3 mb-4">
            <p className="text-[10px] text-slate-500 uppercase tracking-wider font-bold mb-2">
              AI Bookkeeping Rationale
            </p>
            <p className="text-xs text-slate-300 leading-relaxed">
              {rationale || 'No AI reasoning provided.'}
            </p>
          </div>

          <div
            className={`rounded-xl p-3 border text-xs flex items-start gap-2 ${
              isBalanced
                ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300'
                : 'bg-rose-500/10 border-rose-500/20 text-rose-300'
            }`}
          >
            {isBalanced ? (
              <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5 text-emerald-400" />
            ) : (
              <XCircle className="w-4 h-4 shrink-0 mt-0.5 text-rose-400" />
            )}
            <span>
              {isBalanced
                ? 'Double-entry is balanced. Total debits equal total credits.'
                : 'Journal entry is unbalanced. Manual correction required.'}
            </span>
          </div>
        </section>
      </div>

      <div className="p-4 sm:p-6 bg-slate-950/30">
        <div className="flex items-center justify-between gap-3 mb-4">
          <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 flex items-center gap-1.5">
            <BookOpen className="w-3.5 h-3.5 text-indigo-400" />
            Journal Entry
          </p>
          {onLineChange && (
            <span
              className={`px-2.5 py-1 rounded-full border text-[10px] font-bold ${
                isEditing
                  ? 'bg-indigo-500/10 border-indigo-500/20 text-indigo-300'
                  : 'bg-slate-800 border-slate-700 text-slate-400'
              }`}
            >
              {isEditing ? 'Editing enabled' : 'Read only'}
            </span>
          )}
        </div>

        <div className="overflow-x-auto rounded-xl border border-slate-800">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="bg-slate-950 border-b border-slate-800 text-slate-400 text-xs font-bold uppercase tracking-wider">
                <th className="py-3 px-4 w-36">Account</th>
                <th className="py-3 px-4">Description</th>
                <th className="py-3 px-4 text-right w-44">Debit</th>
                <th className="py-3 px-4 text-right w-44">Credit</th>
                {isEditing && <th className="py-3 px-4 w-12" />}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80">
              {lines.map((line, index) => (
                <tr
                  key={`${line.id || line.account_code}-${index}`}
                  className="hover:bg-slate-900/60"
                >
                  <td className="py-3 px-4 align-top">
                    {isEditing && onLineChange ? (
                      <input
                        type="text"
                        value={line.account_code}
                        onChange={(event) =>
                          onLineChange(index, 'account_code', event.target.value)
                        }
                        className="w-full px-2 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs font-mono text-slate-100 focus:outline-none focus:border-indigo-500"
                        placeholder="Code"
                      />
                    ) : (
                      <span className="font-mono text-xs text-slate-400 bg-slate-800/60 px-2 py-0.5 rounded">
                        {line.account_code || '-'}
                      </span>
                    )}
                  </td>
                  <td className="py-3 px-4 align-top">
                    {isEditing && onLineChange ? (
                      <input
                        type="text"
                        value={line.account_name || ''}
                        onChange={(event) =>
                          onLineChange(index, 'account_name', event.target.value)
                        }
                        className="w-full px-2 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-100 focus:outline-none focus:border-indigo-500"
                        placeholder="Account name"
                      />
                    ) : (
                      <div>
                        <p className="text-sm font-semibold text-slate-100">
                          {line.account_name || 'Unknown Account'}
                        </p>
                        {line.description && (
                          <p className="text-[11px] text-slate-500 truncate max-w-xs mt-0.5">
                            {line.description}
                          </p>
                        )}
                      </div>
                    )}
                  </td>
                  <td className="py-3 px-4 text-right align-top">
                    {isEditing && onLineChange ? (
                      <input
                        type="number"
                        step="any"
                        value={line.debit_amount || ''}
                        onChange={(event) =>
                          onLineChange(index, 'debit_amount', event.target.value)
                        }
                        className="w-full px-2 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs font-mono text-emerald-400 font-bold text-right focus:outline-none focus:border-indigo-500"
                      />
                    ) : line.debit_amount > 0 ? (
                      <span className="font-mono font-semibold text-slate-100 text-sm">
                        {formatMoney(line.debit_amount, currency)}
                      </span>
                    ) : (
                      <span className="text-slate-700">-</span>
                    )}
                  </td>
                  <td className="py-3 px-4 text-right align-top">
                    {isEditing && onLineChange ? (
                      <input
                        type="number"
                        step="any"
                        value={line.credit_amount || ''}
                        onChange={(event) =>
                          onLineChange(index, 'credit_amount', event.target.value)
                        }
                        className="w-full px-2 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs font-mono text-indigo-400 font-bold text-right focus:outline-none focus:border-indigo-500"
                      />
                    ) : line.credit_amount > 0 ? (
                      <span className="font-mono font-semibold text-slate-100 text-sm">
                        {formatMoney(line.credit_amount, currency)}
                      </span>
                    ) : (
                      <span className="text-slate-700">-</span>
                    )}
                  </td>
                  {isEditing && (
                    <td className="py-3 px-4 text-center align-top">
                      <button
                        type="button"
                        onClick={() => onRemoveLine?.(index)}
                        disabled={lines.length <= 2}
                        className="p-1.5 rounded-lg text-slate-600 hover:text-rose-400 hover:bg-rose-500/10 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                        title="Remove line"
                      >
                        X
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-slate-700 bg-slate-950/60 font-bold">
                <td
                  className="py-3 px-4 text-xs uppercase tracking-wider text-slate-400"
                  colSpan={2}
                >
                  Total
                </td>
                <td className="py-3 px-4 text-right">
                  <span
                    className={`font-mono text-sm font-bold ${
                      isBalanced ? 'text-emerald-400' : 'text-rose-400'
                    }`}
                  >
                    {formatMoney(totalDebits, currency)}
                  </span>
                </td>
                <td className="py-3 px-4 text-right">
                  <span
                    className={`font-mono text-sm font-bold ${
                      isBalanced ? 'text-emerald-400' : 'text-rose-400'
                    }`}
                  >
                    {formatMoney(totalCredits, currency)}
                  </span>
                </td>
                {isEditing && <td />}
              </tr>
            </tfoot>
          </table>
        </div>

        <div className="mt-3 flex items-center justify-between gap-3">
          {isBalanced ? (
            <span className="flex items-center gap-1.5 text-xs text-emerald-400 font-semibold">
              <CheckCircle2 className="w-4 h-4" />
              Balanced - Debit = Credit
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-xs text-rose-400 font-semibold">
              <AlertTriangle className="w-4 h-4" />
              Unbalanced - Diff: {formatMoney(balanceDiff, currency)}
            </span>
          )}

          {isEditing && onAddLine && (
            <button
              type="button"
              onClick={onAddLine}
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 text-xs font-semibold inline-flex items-center gap-1 transition-all"
            >
              + Add Line
            </button>
          )}
        </div>
      </div>
    </>
  )
}
