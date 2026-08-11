import React, { useEffect, useState } from 'react'
import { BookOpen, Info, Loader2, ShieldAlert, Sparkles, X } from 'lucide-react'
import type { JournalEntryResponse } from '../../services/api'
import { fetchJournalEntryDetail } from '../../services/api'

interface JournalDetailModalProps {
  entryId: string | null
  onClose: () => void
}

export const JournalDetailModal: React.FC<JournalDetailModalProps> = ({ entryId, onClose }) => {
  const [detail, setDetail] = useState<JournalEntryResponse | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!entryId) return

    const loadDetail = async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await fetchJournalEntryDetail(entryId)
        setDetail(res)
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to load journal detail')
      } finally {
        setLoading(false)
      }
    }

    loadDetail()
  }, [entryId])

  if (!entryId) return null

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-md flex items-center justify-center p-4 overflow-y-auto">
      <div className="relative max-w-4xl w-full bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col my-auto">
        {/* Header */}
        <div className="px-6 py-4 bg-slate-950/80 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
              <BookOpen className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-white">Journal Entry Details</h3>
              <p className="text-xs text-slate-400 font-mono">ID: {entryId}</p>
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

        {/* Modal Content */}
        <div className="p-6 space-y-5 max-h-[80vh] overflow-y-auto">
          {loading ? (
            <div className="py-12 text-center text-slate-400 space-y-2">
              <Loader2 className="w-8 h-8 animate-spin text-indigo-400 mx-auto" />
              <p className="text-xs">Fetching journal entry lines...</p>
            </div>
          ) : error ? (
            <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs">
              {error}
            </div>
          ) : detail ? (
            <>
              {/* Entry Meta Card */}
              <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
                <div>
                  <span className="text-slate-500 block text-[11px]">Entry Date</span>
                  <span className="font-bold text-slate-200 font-mono">{detail.entry_date}</span>
                </div>
                <div>
                  <span className="text-slate-500 block text-[11px]">Status</span>
                  <span className="font-semibold text-emerald-400 capitalize">{detail.status}</span>
                </div>
                <div>
                  <span className="text-slate-500 block text-[11px]">Agent Origin</span>
                  <span className="font-semibold text-indigo-300 flex items-center gap-1">
                    <Sparkles className="w-3 h-3 text-indigo-400" />
                    {detail.agent_name || 'Bookkeeping Agent'}
                  </span>
                </div>
                <div className="sm:col-span-3 border-t border-slate-800/80 pt-3">
                  <span className="text-slate-500 block text-[11px]">Description / Memo</span>
                  <p className="font-semibold text-slate-100 text-sm mt-0.5 font-sans">
                    {detail.description}
                  </p>
                </div>
              </div>

              {/* Rationale & Risk Flags */}
              {detail.rationale && (
                <div className="p-3.5 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-xs text-indigo-200 space-y-1">
                  <div className="flex items-center gap-1.5 font-bold text-indigo-300">
                    <Info className="w-4 h-4 text-indigo-400" /> AI Bookkeeping Rationale:
                  </div>
                  <p className="italic text-slate-300">"{detail.rationale}"</p>
                </div>
              )}

              {detail.risk_flags && detail.risk_flags.length > 0 && (
                <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs flex items-center gap-2">
                  <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0" />
                  <div className="flex flex-wrap gap-1">
                    {detail.risk_flags.map((flag) => (
                      <span
                        key={flag}
                        className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 font-mono text-[10px]"
                      >
                        {flag}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Journal Lines Table */}
              <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950">
                <table className="w-full text-left text-xs font-mono">
                  <thead className="bg-slate-900 text-slate-400 border-b border-slate-800 font-semibold uppercase text-[10px] font-sans">
                    <tr>
                      <th className="py-2.5 px-3">#</th>
                      <th className="py-2.5 px-3">Account Code</th>
                      <th className="py-2.5 px-3">Account Name</th>
                      <th className="py-2.5 px-3 text-right">Debit (IDR)</th>
                      <th className="py-2.5 px-3 text-right">Credit (IDR)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/80">
                    {detail.lines?.map((line) => (
                      <tr key={line.id} className="hover:bg-slate-900/60">
                        <td className="py-2.5 px-3 text-slate-500">{line.line_number}</td>
                        <td className="py-2.5 px-3 font-bold text-slate-200">
                          {line.account_code}
                        </td>
                        <td className="py-2.5 px-3 font-sans text-slate-300">
                          {line.account_name}
                        </td>
                        <td className="py-2.5 px-3 text-right font-bold text-emerald-400">
                          {line.debit_amount > 0 ? line.debit_amount.toLocaleString() : '-'}
                        </td>
                        <td className="py-2.5 px-3 text-right font-bold text-indigo-400">
                          {line.credit_amount > 0 ? line.credit_amount.toLocaleString() : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot className="bg-slate-900/90 font-bold border-t border-slate-800">
                    <tr>
                      <td colSpan={3} className="py-3 px-3 font-sans text-slate-300">
                        Total Balance Verification
                      </td>
                      <td className="py-3 px-3 text-right text-emerald-400 font-mono">
                        IDR {detail.total_debit.toLocaleString()}
                      </td>
                      <td className="py-3 px-3 text-right text-indigo-400 font-mono">
                        IDR {detail.total_credit.toLocaleString()}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  )
}
