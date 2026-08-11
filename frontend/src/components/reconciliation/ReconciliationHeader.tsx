import React, { useRef, useState } from 'react'
import {
  AlertCircle,
  ArrowLeftRight,
  CheckCircle2,
  Clock,
  FileSpreadsheet,
  Loader2,
  Sparkles,
} from 'lucide-react'
import { runReconciliationWorkflow, uploadBankStatementCSV } from '../../services/api'

interface ReconciliationHeaderProps {
  totalCount: number
  matchedCount: number
  proposedCount: number
  unmatchedCount: number
  activeImportId: string | null
  onImportSuccess: (importId: string) => void
  onRunSuccess: () => void
}

export const ReconciliationHeader: React.FC<ReconciliationHeaderProps> = ({
  totalCount,
  matchedCount,
  proposedCount,
  unmatchedCount,
  activeImportId,
  onImportSuccess,
  onRunSuccess,
}) => {
  const [uploading, setUploading] = useState(false)
  const [runningEngine, setRunningEngine] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleCSVSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return
    const file = e.target.files[0]

    setUploading(true)
    setErrorMsg(null)
    try {
      const res = await uploadBankStatementCSV(file)
      onImportSuccess(res.id)
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to import CSV')
    } finally {
      setUploading(false)
    }
  }

  const handleRunReconciliation = async () => {
    if (!activeImportId) {
      alert('Please upload or select a Bank Statement CSV first.')
      return
    }

    setRunningEngine(true)
    setErrorMsg(null)
    try {
      await runReconciliationWorkflow(activeImportId)
      onRunSuccess()
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to run reconciliation engine')
    } finally {
      setRunningEngine(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* Top Banner & Main Actions */}
      <div className="p-6 rounded-2xl bg-gradient-to-r from-emerald-950/40 via-slate-900 to-slate-900 border border-emerald-500/20 shadow-xl backdrop-blur-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-semibold uppercase tracking-wider mb-2">
            <ArrowLeftRight className="w-3.5 h-3.5" /> Bank Mutation Reconciliation
          </div>
          <h2 className="text-2xl font-extrabold text-white">
            Automated Bank Statement Matching Engine
          </h2>
          <p className="text-slate-400 text-xs mt-1 max-w-xl">
            Match imported bank statement CSV mutations against posted General Ledger entries using
            deterministic exact matching & AI semantic scoring.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={handleCSVSelect}
            disabled={uploading}
          />

          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 font-semibold text-xs transition-all flex items-center gap-2 disabled:opacity-50"
          >
            {uploading ? (
              <Loader2 className="w-4 h-4 animate-spin text-emerald-400" />
            ) : (
              <FileSpreadsheet className="w-4 h-4 text-emerald-400" />
            )}
            Import Bank Statement CSV
          </button>

          <button
            type="button"
            onClick={handleRunReconciliation}
            disabled={runningEngine || !activeImportId}
            className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-emerald-600 to-emerald-700 hover:from-emerald-500 hover:to-emerald-600 text-white font-semibold text-xs transition-all shadow-lg shadow-emerald-600/30 flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {runningEngine ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Sparkles className="w-4 h-4" />
            )}
            Run Recon Engine
          </button>
        </div>
      </div>

      {errorMsg && (
        <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Summary Counts Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl bg-slate-800/40 border border-slate-700/50 space-y-1">
          <span className="text-[11px] text-slate-400 font-semibold uppercase">
            Total Bank Mutations
          </span>
          <div className="text-2xl font-bold text-white">{totalCount}</div>
        </div>

        <div className="p-4 rounded-xl bg-slate-800/40 border border-slate-700/50 space-y-1">
          <span className="text-[11px] text-emerald-400 font-semibold uppercase flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5" /> Exact Matched
          </span>
          <div className="text-2xl font-bold text-emerald-400">{matchedCount}</div>
        </div>

        <div className="p-4 rounded-xl bg-slate-800/40 border border-slate-700/50 space-y-1">
          <span className="text-[11px] text-amber-400 font-semibold uppercase flex items-center gap-1">
            <Clock className="w-3.5 h-3.5" /> Possible Match (Review)
          </span>
          <div className="text-2xl font-bold text-amber-400">{proposedCount}</div>
        </div>

        <div className="p-4 rounded-xl bg-slate-800/40 border border-slate-700/50 space-y-1">
          <span className="text-[11px] text-slate-400 font-semibold uppercase">
            Unmatched Open Items
          </span>
          <div className="text-2xl font-bold text-slate-300">{unmatchedCount}</div>
        </div>
      </div>
    </div>
  )
}
