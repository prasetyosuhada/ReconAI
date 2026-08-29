import React, { useRef, useState } from 'react'
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeftRight,
  Building2,
  Calendar,
  CheckCircle2,
  ChevronDown,
  Clock,
  FileSpreadsheet,
  Loader2,
  Sparkles,
} from 'lucide-react'
import type { BankStatementImportResponse, BankTransactionResponse } from '../../services/api'
import { runReconciliationWorkflow, uploadBankStatementCSV } from '../../services/api'

interface ReconciliationHeaderProps {
  totalCount: number
  matchedCount: number
  proposedCount: number
  unmatchedCount: number
  activeImportId: string | null
  imports: BankStatementImportResponse[]
  transactions?: BankTransactionResponse[]
  onSelectImport: (importId: string) => void
  onImportSuccess: (importId: string, importData: BankStatementImportResponse) => void
  onRunSuccess: () => void
  onTriggerStreamRun?: (importId: string) => void
  isStreaming?: boolean
}

export const ReconciliationHeader: React.FC<ReconciliationHeaderProps> = ({
  totalCount,
  matchedCount,
  proposedCount,
  unmatchedCount,
  activeImportId,
  imports,
  transactions = [],
  onSelectImport,
  onImportSuccess,
  onRunSuccess,
  onTriggerStreamRun,
  isStreaming = false,
}) => {
  const [uploading, setUploading] = useState(false)
  const [runningEngine, setRunningEngine] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const activeImport = imports.find((i) => i.id === activeImportId) ?? null

  // Button is only active when a fresh import exists that hasn't been processed yet
  const canRunRecon = !!activeImportId && !!activeImport && activeImport.status === 'imported'

  const reconEngineDisabledReason = !activeImportId
    ? 'Upload a Bank Statement CSV first'
    : activeImport && activeImport.status === 'matching_in_progress'
      ? 'Reconciliation engine is running…'
      : activeImport && activeImport.status !== 'imported'
        ? 'Already run — import a new statement to run again'
        : null

  const handleCSVSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return
    const file = e.target.files[0]
    // Reset input so re-uploading the same file still triggers onChange
    e.target.value = ''

    setUploading(true)
    setErrorMsg(null)
    try {
      const res = await uploadBankStatementCSV(file)
      onImportSuccess(res.id, res)
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

    if (onTriggerStreamRun) {
      onTriggerStreamRun(activeImportId)
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

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })

  // Derived Statement Period from transactions
  const statementPeriod = (() => {
    if (transactions.length === 0) {
      return activeImport ? formatDate(activeImport.imported_at) : 'No period data'
    }
    const validDates = transactions
      .map((t) => t.transaction_date)
      .filter(Boolean)
      .sort()

    if (validDates.length === 0) return 'No period data'

    const formatShort = (dateStr: string) =>
      new Date(dateStr).toLocaleDateString('en-US', {
        month: 'short',
        day: '2-digit',
        year: 'numeric',
      })

    const start = formatShort(validDates[0])
    const end = formatShort(validDates[validDates.length - 1])
    return start === end ? start : `${start} – ${end}`
  })()

  // Derived Bank Account from active import metadata / filename
  const bankAccountDisplay = (() => {
    if (!activeImport) return 'BCA •••• 1234'
    const fn = activeImport.original_filename.toLowerCase()
    if (fn.includes('mandiri')) return 'Mandiri •••• 5678'
    if (fn.includes('bni')) return 'BNI •••• 9012'
    if (fn.includes('bri')) return 'BRI •••• 3456'
    return 'BCA •••• 1234'
  })()

  // Derived Reconciliation Status
  const reconStatus = (() => {
    if (totalCount === 0) {
      return {
        label: 'No Statement Data',
        badgeClass: 'text-slate-400 bg-slate-800/80 border-slate-700/60',
        Icon: Clock,
      }
    }
    if (unmatchedCount === 0 && proposedCount === 0 && matchedCount > 0) {
      return {
        label: 'Reconciled',
        badgeClass: 'text-emerald-400 bg-emerald-950/60 border-emerald-500/30',
        Icon: CheckCircle2,
      }
    }
    if (proposedCount > 0) {
      return {
        label: 'Review Required',
        badgeClass: 'text-amber-400 bg-amber-950/60 border-amber-500/30',
        Icon: AlertTriangle,
      }
    }
    if (matchedCount > 0 && unmatchedCount > 0) {
      return {
        label: 'Partially Reconciled',
        badgeClass: 'text-cyan-400 bg-cyan-950/60 border-cyan-500/30',
        Icon: Clock,
      }
    }
    return {
      label: 'Unreconciled',
      badgeClass: 'text-slate-300 bg-slate-800/80 border-slate-700/60',
      Icon: AlertCircle,
    }
  })()

  const StatusIcon = reconStatus.Icon

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
            deterministic exact matching &amp; AI semantic scoring.
          </p>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
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
            className="px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 font-semibold text-xs transition-all flex items-center gap-2 disabled:opacity-50 cursor-pointer"
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
            disabled={runningEngine || isStreaming || !canRunRecon}
            title={reconEngineDisabledReason ?? undefined}
            className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-emerald-600 to-emerald-700 hover:from-emerald-500 hover:to-emerald-600 text-white font-semibold text-xs transition-all shadow-lg shadow-emerald-600/30 flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
          >
            {runningEngine || isStreaming ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Sparkles className="w-4 h-4" />
            )}
            {isStreaming ? 'Streaming Recon...' : 'Run Recon Engine'}
          </button>
        </div>
      </div>

      {errorMsg && (
        <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Reconciliation Context Bar */}
      <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 shadow-md backdrop-blur-sm grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 items-center">
        {/* Bank Account */}
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 shrink-0">
            <Building2 className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <div className="text-[10px] uppercase font-bold tracking-wider text-slate-400">
              Bank Account
            </div>
            <div
              className="text-xs font-semibold text-slate-100 truncate"
              title={bankAccountDisplay}
            >
              {bankAccountDisplay}
            </div>
          </div>
        </div>

        {/* Statement Period */}
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-400 shrink-0">
            <Calendar className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <div className="text-[10px] uppercase font-bold tracking-wider text-slate-400">
              Statement Period
            </div>
            <div className="text-xs font-semibold text-slate-100 truncate" title={statementPeriod}>
              {statementPeriod}
            </div>
          </div>
        </div>

        {/* Reconciliation Status */}
        <div className="flex items-center gap-3">
          <div className={`p-2.5 rounded-lg border shrink-0 ${reconStatus.badgeClass}`}>
            <StatusIcon className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <div className="text-[10px] uppercase font-bold tracking-wider text-slate-400">
              Reconciliation Status
            </div>
            <div className="mt-0.5">
              <span
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold border ${reconStatus.badgeClass}`}
              >
                {reconStatus.label}
              </span>
            </div>
          </div>
        </div>

        {/* Batch Dropdown / Selector */}
        <div className="flex flex-col justify-center">
          <div className="text-[10px] uppercase font-bold tracking-wider text-slate-400 mb-1">
            Active Batch
          </div>
          <div className="relative">
            <button
              type="button"
              onClick={() => setDropdownOpen((v) => !v)}
              className="w-full flex items-center justify-between gap-2 px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700 hover:border-emerald-500/40 text-slate-200 text-xs font-medium transition-all text-left cursor-pointer"
            >
              <span className="truncate">
                {activeImport ? activeImport.original_filename : 'Select a bank statement…'}
              </span>
              <ChevronDown
                className={`w-3.5 h-3.5 text-slate-400 shrink-0 transition-transform ${dropdownOpen ? 'rotate-180' : ''}`}
              />
            </button>

            {dropdownOpen && imports.length > 0 && (
              <div className="absolute top-full mt-1.5 right-0 z-50 w-full min-w-[280px] rounded-xl bg-slate-900 border border-slate-700 shadow-2xl overflow-hidden">
                <div className="max-h-60 overflow-y-auto divide-y divide-slate-800">
                  {imports.map((imp) => (
                    <button
                      key={imp.id}
                      type="button"
                      onClick={() => {
                        onSelectImport(imp.id)
                        setDropdownOpen(false)
                      }}
                      className={`w-full px-3 py-2 flex items-center gap-2.5 text-left text-xs hover:bg-slate-800 transition-colors cursor-pointer ${
                        imp.id === activeImportId
                          ? 'bg-emerald-950/40 text-emerald-300'
                          : 'text-slate-200'
                      }`}
                    >
                      <FileSpreadsheet
                        className={`w-3.5 h-3.5 shrink-0 ${imp.id === activeImportId ? 'text-emerald-400' : 'text-slate-500'}`}
                      />
                      <div className="flex-1 min-w-0">
                        <div className="truncate font-medium">{imp.original_filename}</div>
                        <div className="text-slate-500 text-[10px]">
                          {formatDate(imp.imported_at)} · {imp.row_count} rows
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Accounting-Oriented Summary Cards Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Transactions */}
        <div className="p-4 rounded-xl bg-slate-800/40 border border-slate-700/50 space-y-1 hover:border-slate-600/60 transition-colors">
          <span className="text-[11px] text-slate-400 font-bold uppercase tracking-wider">
            Total Transactions
          </span>
          <div className="text-2xl font-extrabold text-white">{totalCount}</div>
          <div className="text-[10px] text-slate-500 font-medium">Bank statement lines</div>
        </div>

        {/* Matched */}
        <div className="p-4 rounded-xl bg-slate-800/40 border border-slate-700/50 space-y-1 hover:border-emerald-500/30 transition-colors">
          <span className="text-[11px] text-emerald-400 font-bold uppercase tracking-wider flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5" /> Matched
          </span>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-extrabold text-emerald-400">{matchedCount}</span>
            {totalCount > 0 && (
              <span className="text-xs font-semibold text-emerald-500/80">
                {((matchedCount / totalCount) * 100).toFixed(1)}%
              </span>
            )}
          </div>
          <div className="text-[10px] text-slate-500 font-medium">Reconciled with GL</div>
        </div>

        {/* Needs Review */}
        <div className="p-4 rounded-xl bg-slate-800/40 border border-slate-700/50 space-y-1 hover:border-amber-500/30 transition-colors">
          <span className="text-[11px] text-amber-400 font-bold uppercase tracking-wider flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5" /> Needs Review
          </span>
          <div className="text-2xl font-extrabold text-amber-400">{proposedCount}</div>
          <div className="text-[10px] text-slate-500 font-medium">AI suggested candidates</div>
        </div>

        {/* Unmatched */}
        <div className="p-4 rounded-xl bg-slate-800/40 border border-slate-700/50 space-y-1 hover:border-slate-600/60 transition-colors">
          <span className="text-[11px] text-slate-400 font-bold uppercase tracking-wider">
            Unmatched
          </span>
          <div className="text-2xl font-extrabold text-slate-300">{unmatchedCount}</div>
          <div className="text-[10px] text-slate-500 font-medium">Open / bank-only items</div>
        </div>
      </div>
    </div>
  )
}
