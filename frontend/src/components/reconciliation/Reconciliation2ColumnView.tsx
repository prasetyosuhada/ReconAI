import React, { useEffect, useRef, useState } from 'react'
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  BookOpen,
  Building2,
  CheckCircle2,
  Clock,
  Eye,
  FileSpreadsheet,
  HelpCircle,
  Info,
  Loader2,
  Plus,
  PlusCircle,
  RotateCcw,
  Search,
  ShieldCheck,
  Sparkles,
  Trash2,
  Undo2,
  X,
} from 'lucide-react'
import type {
  AdjustmentSuggestionResponse,
  BankTransactionResponse,
  ChartOfAccountResponse,
  JournalEntryResponse,
  ReconciliationMatchResponse,
  SuggestedJournalLine,
} from '../../services/api'
import {
  createAdjustmentJournalEntry,
  fetchChartOfAccounts,
  manualMatchReconciliation,
  suggestAdjustmentJournal,
} from '../../services/api'
import type { ReconFilterType } from './ReconciliationFiltersToolbar'

interface Reconciliation2ColumnViewProps {
  transactions: BankTransactionResponse[]
  matches: ReconciliationMatchResponse[]
  glOnlyEntries?: JournalEntryResponse[]
  postedJournalEntries?: JournalEntryResponse[]
  chartOfAccounts?: ChartOfAccountResponse[]
  activeFilter: ReconFilterType
  loading: boolean
  actionLoading?: boolean
  selectedTxId: string | null
  selectedGLEntryId?: string | null
  onSelectTx: (txId: string) => void
  onSelectGLEntry?: (glId: string) => void
  onAcceptMatch?: (matchId: string) => void | Promise<void>
  onRejectMatch?: (matchId: string) => void | Promise<void>
  onRefresh?: () => void
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
  postedJournalEntries = [],
  chartOfAccounts = [],
  activeFilter,
  loading,
  actionLoading = false,
  selectedTxId,
  selectedGLEntryId,
  onSelectTx,
  onSelectGLEntry,
  onAcceptMatch,
  onRejectMatch,
  onRefresh,
}) => {
  const isGLOnlyTab = activeFilter === 'gl_only'

  const selectedTx = transactions.find((t) => t.id === selectedTxId) || transactions[0]
  const selectedMatch = matches.find(
    (m) => m.bank_transaction_id === (selectedTx ? selectedTx.id : '')
  )
  const selectedGL = glOnlyEntries.find((g) => g.id === selectedGLEntryId) || glOnlyEntries[0]

  // Interactive UI Modal States
  const [showFindMatchModal, setShowFindMatchModal] = useState<boolean>(false)
  const [showCreateJEModal, setShowCreateJEModal] = useState<boolean>(false)
  const [showInvestigateModal, setShowInvestigateModal] = useState<boolean>(false)
  const [findMatchSearch, setFindMatchSearch] = useState<string>('')
  const [outstandingTxIds, setOutstandingTxIds] = useState<Set<string>>(new Set())
  const [outstandingGLIds, setOutstandingGLIds] = useState<Set<string>>(new Set())
  const [customToast, setCustomToast] = useState<string | null>(null)

  // AI Adjustment Suggestion from BookkeepingAgent (real LLM call)
  const [suggestion, setSuggestion] = useState<AdjustmentSuggestionResponse | null>(null)
  const [suggestionLoading, setSuggestionLoading] = useState<boolean>(false)
  const [suggestionError, setSuggestionError] = useState<string | null>(null)
  const [isPostingJE, setIsPostingJE] = useState<boolean>(false)
  const lastFetchedTxId = useRef<string | null>(null)

  // Editable form state for Create Adjusting Journal Entry Modal
  const [entryDate, setEntryDate] = useState<string>('')
  const [entryDescription, setEntryDescription] = useState<string>('')
  const [journalLines, setJournalLines] = useState<SuggestedJournalLine[]>([])
  const [dbCOA, setDbCOA] = useState<ChartOfAccountResponse[]>(chartOfAccounts || [])

  // Keep dbCOA in sync with prop from DB, or fetch directly from DB table `chart_of_accounts`
  useEffect(() => {
    if (chartOfAccounts && chartOfAccounts.length > 0) {
      setDbCOA(chartOfAccounts)
    } else {
      fetchChartOfAccounts()
        .then((res) => {
          if (res.items && res.items.length > 0) {
            setDbCOA(res.items)
          }
        })
        .catch((err) => {
          console.error('Failed to fetch COA from database:', err)
        })
    }
  }, [chartOfAccounts])

  const showToast = (msg: string) => {
    setCustomToast(msg)
    setTimeout(() => setCustomToast(null), 3000)
  }

  // Open modal with prefilled lines (from AI suggestion if available, otherwise balanced default 2 lines from DB COA)
  const openCreateAdjustmentModal = () => {
    if (!selectedTx) return

    setEntryDate(selectedTx.transaction_date || new Date().toISOString().split('T')[0])
    setEntryDescription(selectedTx.description || 'Adjusting Journal Entry')

    if (suggestion?.suggested_lines && suggestion.suggested_lines.length >= 2) {
      setJournalLines(
        suggestion.suggested_lines.map((l) => ({
          account_code: l.account_code,
          account_name: l.account_name,
          description: l.description || selectedTx.description,
          debit_amount: l.debit_amount || 0,
          credit_amount: l.credit_amount || 0,
        }))
      )
    } else {
      const rawAmt = Math.abs(selectedTx.amount)
      const bankAcct =
        dbCOA.find((c) => c.account_code === '1010') ||
        dbCOA.find((c) => c.account_type === 'asset') || {
          account_code: '1010',
          account_name: 'Bank Account',
        }
      const expenseAcct =
        dbCOA.find((c) => c.account_code === '5900') ||
        dbCOA.find((c) => c.account_type === 'expense') || {
          account_code: '5900',
          account_name: 'Miscellaneous Expense',
        }
      const revenueAcct =
        dbCOA.find((c) => c.account_code === '4000') ||
        dbCOA.find((c) => c.account_type === 'revenue') || {
          account_code: '4000',
          account_name: 'Sales Revenue',
        }

      if (selectedTx.amount < 0) {
        // Outflow: Debit Expense, Credit Bank
        setJournalLines([
          {
            account_code: expenseAcct.account_code,
            account_name: expenseAcct.account_name,
            description: selectedTx.description,
            debit_amount: rawAmt,
            credit_amount: 0,
          },
          {
            account_code: bankAcct.account_code,
            account_name: bankAcct.account_name,
            description: 'Bank Outflow',
            debit_amount: 0,
            credit_amount: rawAmt,
          },
        ])
      } else {
        // Inflow: Debit Bank, Credit Revenue
        setJournalLines([
          {
            account_code: bankAcct.account_code,
            account_name: bankAcct.account_name,
            description: 'Bank Inflow',
            debit_amount: rawAmt,
            credit_amount: 0,
          },
          {
            account_code: revenueAcct.account_code,
            account_name: revenueAcct.account_name,
            description: selectedTx.description,
            debit_amount: 0,
            credit_amount: rawAmt,
          },
        ])
      }
    }

    setShowCreateJEModal(true)
  }

  const resetToAISuggestion = () => {
    if (!suggestion?.suggested_lines || suggestion.suggested_lines.length < 2) return
    setJournalLines(
      suggestion.suggested_lines.map((l) => ({
        account_code: l.account_code,
        account_name: l.account_name,
        description: l.description || selectedTx?.description || '',
        debit_amount: l.debit_amount || 0,
        credit_amount: l.credit_amount || 0,
      }))
    )
    if (selectedTx?.description) {
      setEntryDescription(selectedTx.description)
    }
  }

  const handleLineAccountChange = (index: number, newAccountCode: string) => {
    const foundCoa = dbCOA.find((c: ChartOfAccountResponse) => c.account_code === newAccountCode)
    const newName = foundCoa ? foundCoa.account_name : 'Custom Account'
    setJournalLines((prev) =>
      prev.map((line, idx) =>
        idx === index
          ? { ...line, account_code: newAccountCode, account_name: newName }
          : line
      )
    )
  }

  const handleLineFieldChange = (
    index: number,
    field: 'description' | 'debit_amount' | 'credit_amount',
    val: string | number
  ) => {
    setJournalLines((prev) =>
      prev.map((line, idx) => {
        if (idx !== index) return line
        if (field === 'debit_amount') {
          const num = typeof val === 'number' ? val : parseFloat(val) || 0
          return { ...line, debit_amount: num, credit_amount: num > 0 ? 0 : line.credit_amount }
        }
        if (field === 'credit_amount') {
          const num = typeof val === 'number' ? val : parseFloat(val) || 0
          return { ...line, credit_amount: num, debit_amount: num > 0 ? 0 : line.debit_amount }
        }
        return { ...line, description: String(val) }
      })
    )
  }

  const handleAddLine = () => {
    const defaultExpense =
      dbCOA.find((c) => c.account_type === 'expense') ||
      dbCOA[0] || {
        account_code: '5900',
        account_name: 'Miscellaneous Expense',
      }
    setJournalLines((prev) => [
      ...prev,
      {
        account_code: defaultExpense.account_code,
        account_name: defaultExpense.account_name,
        description: '',
        debit_amount: 0,
        credit_amount: 0,
      },
    ])
  }

  const handleRemoveLine = (index: number) => {
    if (journalLines.length <= 2) return
    setJournalLines((prev) => prev.filter((_, idx) => idx !== index))
  }

  // Real-time double-entry calculations
  const totalDebit = journalLines.reduce((sum, l) => sum + (Number(l.debit_amount) || 0), 0)
  const totalCredit = journalLines.reduce((sum, l) => sum + (Number(l.credit_amount) || 0), 0)
  const imbalance = Math.abs(totalDebit - totalCredit)
  const isBalanced = imbalance < 0.01 && totalDebit > 0

  const handleSaveAndPostJournalEntry = async () => {
    if (!selectedTx || !isBalanced) return
    setIsPostingJE(true)
    try {
      const res = await createAdjustmentJournalEntry({
        bank_transaction_id: selectedTx.id,
        entry_date: entryDate || selectedTx.transaction_date,
        description: entryDescription || selectedTx.description,
        lines: journalLines,
      })
      showToast(
        `✓ Adjusting Journal Entry #JE-${res.journal_entry_id.substring(0, 8)} posted to General Ledger!`
      )
      setShowCreateJEModal(false)
      onRefresh?.()
    } catch (err) {
      console.error('Failed to create adjusting journal entry:', err)
      showToast(err instanceof Error ? `Error: ${err.message}` : 'Failed to post journal entry.')
    } finally {
      setIsPostingJE(false)
    }
  }

  const handleUnmatch = async (matchId: string) => {
    if (!onRejectMatch) return
    try {
      await onRejectMatch(matchId)
      showToast('✓ Transaction unmatched. BookkeepingAgent classified COA suggestion for Bank Only tab.')
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : 'Failed to unmatch transaction.')
    }
  }

  // Toggle Outstanding state for Bank mutations or GL entries
  const toggleOutstandingTx = (txId: string) => {
    setOutstandingTxIds((prev) => {
      const next = new Set(prev)
      if (next.has(txId)) {
        next.delete(txId)
        showToast('Marked transaction as active.')
      } else {
        next.add(txId)
        showToast('Marked transaction as Outstanding / Timing Difference.')
      }
      return next
    })
  }

  const toggleOutstandingGL = (glId: string) => {
    setOutstandingGLIds((prev) => {
      const next = new Set(prev)
      if (next.has(glId)) {
        next.delete(glId)
        showToast('Marked GL entry as active.')
      } else {
        next.add(glId)
        showToast('Marked GL entry as Outstanding Check / Deposit in Transit.')
      }
      return next
    })
  }

  // Auto-fetch pre-computed BookkeepingAgent suggestion (stored in DB during Run Recon Engine)
  // For matched transactions, no suggestion needed.
  // For unmatched Bank Only: reads from DB instantly (no LLM call on demand).
  useEffect(() => {
    const isBankOnly =
      Boolean(selectedTx) &&
      (!selectedMatch ||
        !selectedMatch.journal_entry ||
        selectedMatch.status === 'rejected' ||
        selectedMatch.status === 'unmatched')

    if (!isBankOnly) {
      setSuggestion(null)
      setSuggestionError(null)
      lastFetchedTxId.current = null
      return
    }

    const fetchKey = `${selectedTx.id}-${selectedMatch?.status || 'none'}`
    if (lastFetchedTxId.current === fetchKey) return

    lastFetchedTxId.current = fetchKey
    setSuggestion(null)
    setSuggestionError(null)
    setSuggestionLoading(true)

    suggestAdjustmentJournal(selectedTx.id)
      .then((res) => {
        setSuggestion(res)
      })
      .catch((err: Error) => {
        setSuggestionError(err.message)
      })
      .finally(() => setSuggestionLoading(false))
  }, [selectedTx?.id, selectedMatch?.id, selectedMatch?.status])


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
    <div className="relative">
      {/* Interactive Toast Notification */}
      {customToast && (
        <div className="fixed bottom-6 right-6 z-50 px-4 py-3 rounded-xl bg-slate-900 border border-emerald-500/50 shadow-2xl text-xs font-semibold text-emerald-300 flex items-center gap-2 animate-in fade-in slide-in-from-bottom-3 duration-200">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>{customToast}</span>
        </div>
      )}

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
                  const isOutstanding = outstandingGLIds.has(ge.id)
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
                        <div className="flex items-center gap-1.5">
                          {isOutstanding && (
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-amber-950/80 text-amber-300 border border-amber-500/30">
                              OUTSTANDING
                            </span>
                          )}
                          <span className="px-2 py-0.5 rounded-full bg-indigo-950/70 border border-indigo-500/30 text-indigo-400 text-[10px] font-bold tracking-wider flex items-center gap-1">
                            <Building2 className="w-3 h-3" /> GL ONLY
                          </span>
                        </div>
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
                const isOutstanding = outstandingTxIds.has(tx.id)

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
                      <div className="flex items-center gap-1.5">
                        {isOutstanding && (
                          <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-amber-950/80 text-amber-300 border border-amber-500/30">
                            OUTSTANDING
                          </span>
                        )}
                        {getStatusBadge(statusStr)}
                      </div>
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
              <span>Reconciliation Analysis &amp; Resolution</span>
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
                      Date: {formatCardDate(selectedGL.entry_date)} • ID: #JE-
                      {selectedGL.id.substring(0, 8)}
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
                    imported bank statement. This may represent an outstanding check, pending
                    deposit, or timing difference.
                  </p>
                </div>
              </div>

              {/* Contextual Actions for GL Only */}
              <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-3">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                  GL Item Resolution Actions
                </span>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setShowFindMatchModal(true)}
                    className="px-3.5 py-2 rounded-xl bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-500/30 text-xs font-semibold transition-colors flex items-center gap-1.5 cursor-pointer"
                  >
                    <Search className="w-3.5 h-3.5" /> Find Bank Transaction
                  </button>
                  <button
                    type="button"
                    onClick={() => toggleOutstandingGL(selectedGL.id)}
                    className={`px-3.5 py-2 rounded-xl border text-xs font-semibold transition-colors flex items-center gap-1.5 cursor-pointer ${
                      outstandingGLIds.has(selectedGL.id)
                        ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                        : 'bg-slate-800 hover:bg-slate-700 text-slate-300 border-slate-700'
                    }`}
                  >
                    <Clock className="w-3.5 h-3.5" />
                    {outstandingGLIds.has(selectedGL.id)
                      ? 'Marked Outstanding'
                      : 'Mark as Outstanding'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowInvestigateModal(true)}
                    className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold transition-colors flex items-center gap-1.5 cursor-pointer"
                  >
                    <Eye className="w-3.5 h-3.5" /> Investigate Ledger
                  </button>
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
                const isRejectedOrUnmatched =
                  !selectedMatch ||
                  !selectedMatch.journal_entry ||
                  selectedMatch.status === 'rejected' ||
                  selectedMatch.status === 'unmatched'

                if (isRejectedOrUnmatched) {
                  // State: No GL Match Found (Bank Only)
                  return (
                    <div className="space-y-4">
                      <div className="p-6 rounded-xl bg-slate-950/40 border border-slate-800 text-center space-y-3">
                        <HelpCircle className="w-10 h-10 text-slate-600 mx-auto" />
                        <div>
                          <p className="text-sm font-bold text-slate-300 uppercase tracking-wider">
                            No GL Match Found
                          </p>
                          <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1 leading-relaxed">
                            No posted General Ledger transaction matched this bank mutation amount
                            or date.
                          </p>
                        </div>
                      </div>

                      {/* AI COA Suggestion Widget – BookkeepingAgent LLM Output */}
                      {suggestionLoading && (
                        <div className="p-4 rounded-xl bg-gradient-to-r from-purple-950/30 to-indigo-950/30 border border-purple-500/30 flex items-center gap-3">
                          <Loader2 className="w-4 h-4 text-purple-400 animate-spin shrink-0" />
                          <span className="text-xs text-purple-300">
                            BookkeepingAgent is classifying this transaction…
                          </span>
                        </div>
                      )}

                      {suggestionError && !suggestionLoading && (
                        <div
                          className={`p-3 rounded-xl flex items-start gap-2 ${
                            suggestionError.includes('Run Recon Engine')
                              ? 'bg-blue-950/30 border border-blue-500/30'
                              : 'bg-red-950/30 border border-red-500/30'
                          }`}
                        >
                          {suggestionError.includes('Run Recon Engine') ? (
                            <Info className="w-4 h-4 text-blue-400 mt-0.5 shrink-0" />
                          ) : (
                            <AlertCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
                          )}
                          <span
                            className={`text-xs ${
                              suggestionError.includes('Run Recon Engine')
                                ? 'text-blue-300'
                                : 'text-red-300'
                            }`}
                          >
                            {suggestionError}
                          </span>
                        </div>
                      )}


                      {suggestion && !suggestionLoading && (
                        <div className="p-4 rounded-xl bg-gradient-to-r from-purple-950/30 to-indigo-950/30 border border-purple-500/30 space-y-3">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <Sparkles className="w-4 h-4 text-purple-400" />
                              <span className="text-xs font-bold text-purple-300 uppercase tracking-wider">
                                AI COA Suggestion
                              </span>
                            </div>
                            <div className="flex items-center gap-1.5">
                              {suggestion.uses_sensitive_account && (
                                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                                  Sensitive
                                </span>
                              )}
                              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30 font-mono">
                                {Math.round(suggestion.confidence_score * 100)}% Confidence
                              </span>
                            </div>
                          </div>

                          {/* Rationale from LLM */}
                          <p className="text-[11px] text-slate-300 leading-relaxed italic border-l-2 border-purple-500/40 pl-2">
                            {suggestion.rationale}
                          </p>

                          {/* Risk flags */}
                          {suggestion.risk_flags.length > 0 && (
                            <div className="flex flex-wrap gap-1">
                              {suggestion.risk_flags.map((flag) => (
                                <span
                                  key={flag}
                                  className="px-2 py-0.5 rounded text-[10px] bg-amber-500/10 text-amber-400 border border-amber-500/20"
                                >
                                  ⚠ {flag}
                                </span>
                              ))}
                            </div>
                          )}

                          {/* Double-entry lines */}
                          <div className="rounded-lg bg-slate-900/80 border border-slate-800 overflow-hidden">
                            <div className="px-3 py-1.5 bg-slate-800/60 border-b border-slate-700">
                              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                                Proposed Journal Lines
                              </span>
                            </div>
                            <div className="divide-y divide-slate-800">
                              {suggestion.suggested_lines.map((line, idx) => (
                                <div key={idx} className="px-3 py-2 flex items-center justify-between text-xs">
                                  <div>
                                    <span className={`font-mono font-bold mr-1 ${ line.debit_amount > 0 ? 'text-emerald-400' : 'text-slate-400' }`}>
                                      [{line.debit_amount > 0 ? 'DR' : 'CR'}]
                                    </span>
                                    <span className="text-white font-medium">{line.account_code}</span>
                                    <span className="text-slate-400 ml-1">• {line.account_name}</span>
                                  </div>
                                  <span className={`font-mono font-semibold ${ line.debit_amount > 0 ? 'text-emerald-400' : 'text-slate-300' }`}>
                                    {line.debit_amount > 0
                                      ? formatCardAmount(line.debit_amount, suggestion.currency)
                                      : formatCardAmount(line.credit_amount, suggestion.currency)}
                                  </span>
                                </div>
                              ))}
                            </div>
                            {!suggestion.is_balanced && (
                              <div className="px-3 py-1.5 bg-red-950/30 border-t border-red-800/40 text-[10px] text-red-400 font-semibold">
                                ⚠ Journal is not balanced — please review before posting
                              </div>
                            )}
                          </div>

                          <button
                            type="button"
                            onClick={openCreateAdjustmentModal}
                            className="w-full py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-semibold text-xs transition-colors flex items-center justify-center gap-1.5 shadow-md shadow-purple-600/20 cursor-pointer"
                          >
                            <PlusCircle className="w-4 h-4" /> Review &amp; Create Journal Entry
                          </button>
                        </div>
                      )}

                      {/* Resolution Actions for Bank Only (Section 12) */}
                      <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-3">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                          Bank Mutation Resolution Actions
                        </span>
                        <div className="flex flex-wrap items-center gap-2">
                          <button
                            type="button"
                            onClick={() => setShowFindMatchModal(true)}
                            className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-semibold transition-colors flex items-center gap-1.5 cursor-pointer"
                          >
                            <Search className="w-3.5 h-3.5 text-emerald-400" /> Find GL Match
                          </button>
                          <button
                            type="button"
                            onClick={openCreateAdjustmentModal}
                            className="px-3.5 py-2 rounded-xl bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 text-xs font-semibold transition-colors flex items-center gap-1.5 cursor-pointer"
                          >
                            <PlusCircle className="w-3.5 h-3.5" /> Create Journal Entry
                          </button>
                          <button
                            type="button"
                            onClick={() => toggleOutstandingTx(selectedTx.id)}
                            className={`px-3.5 py-2 rounded-xl border text-xs font-semibold transition-colors flex items-center gap-1.5 cursor-pointer ${
                              outstandingTxIds.has(selectedTx.id)
                                ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                                : 'bg-slate-800 hover:bg-slate-700 text-slate-300 border-slate-700'
                            }`}
                          >
                            <Clock className="w-3.5 h-3.5" />
                            {outstandingTxIds.has(selectedTx.id)
                              ? 'Marked Outstanding'
                              : 'Mark as Outstanding'}
                          </button>
                        </div>
                      </div>
                    </div>
                  )
                }

                const isAlreadyAccepted =
                  selectedMatch.status === 'accepted' || selectedMatch.status === 'matched'

                if (isAlreadyAccepted) {
                  // State: MATCHED / RECONCILED GL TRANSACTION
                  const score = Math.round((selectedMatch.confidence_score ?? 1) * 100)
                  const isExact =
                    selectedMatch.match_type === 'exact' ||
                    selectedMatch.match_rule_type === 'EXACT_MATCH' ||
                    score >= 95

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
                          {isExact ? '✓ EXACT MATCH (100%)' : `✓ RECONCILED (${score}%)`}
                        </span>
                      </div>

                      {/* Match Comparison Grid */}
                      <div className="grid grid-cols-2 gap-3 text-xs bg-slate-900/80 p-3.5 rounded-lg border border-slate-800">
                        <div>
                          <span className="text-slate-500 block text-[11px]">Ledger Entry ID</span>
                          <span className="font-semibold text-slate-200 font-mono">
                            {selectedMatch.journal_entry?.id
                              ? `#JE-${selectedMatch.journal_entry.id.substring(0, 8)}`
                              : selectedMatch.journal_entry_id
                                ? `#JE-${selectedMatch.journal_entry_id.substring(0, 8)}`
                                : 'N/A'}
                          </span>
                        </div>
                        <div>
                          <span className="text-slate-500 block text-[11px]">
                            Ledger Entry Date
                          </span>
                          <span className="font-semibold text-slate-200 font-mono">
                            {formatCardDate(selectedMatch.journal_entry?.entry_date || '')}
                          </span>
                        </div>
                        <div className="col-span-2 border-t border-slate-800 pt-2">
                          <span className="text-slate-500 block text-[11px]">
                            Journal Description
                          </span>
                          <span className="font-semibold text-slate-100">
                            {selectedMatch.journal_entry?.description || 'Matched General Ledger Entry'}
                          </span>
                        </div>
                      </div>

                      {/* Live Loading Feedback while BookkeepingAgent generates suggestion */}
                      {actionLoading && (
                        <div className="p-3 rounded-xl bg-purple-950/40 border border-purple-500/30 text-purple-200 text-xs flex items-center gap-2.5 animate-pulse">
                          <Loader2 className="w-4 h-4 animate-spin text-purple-400 shrink-0" />
                          <span>Unmatching transaction and invoking BookkeepingAgent to generate COA suggestions…</span>
                        </div>
                      )}

                      {/* Verification Confirmation & Action */}
                      <div className="flex items-center justify-between pt-2 border-t border-slate-800/80">
                        <div className="flex items-center gap-1.5 text-xs text-emerald-400 font-semibold">
                          <ShieldCheck className="w-4 h-4" />
                          Amounts &amp; Dates Verified
                        </div>

                        <div className="flex items-center gap-2">
                          <span className="px-3 py-1.5 rounded-lg bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-xs font-bold flex items-center gap-1">
                            <CheckCircle2 className="w-3.5 h-3.5" /> Reconciled
                          </span>
                          {onRejectMatch && (
                            <button
                              type="button"
                              disabled={actionLoading}
                              onClick={() => handleUnmatch(selectedMatch.id)}
                              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-rose-300 border border-slate-700 hover:border-slate-600 text-xs font-semibold transition-colors cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed flex items-center gap-1.5"
                              title="Unmatch / Undo Match"
                            >
                              {actionLoading ? (
                                <>
                                  <Loader2 className="w-3.5 h-3.5 animate-spin text-purple-400" />
                                  <span className="text-[11px] text-purple-300">Unmatching…</span>
                                </>
                              ) : (
                                <>
                                  <Undo2 className="w-3.5 h-3.5" />
                                  <span className="text-[12px]">Unmatch</span>
                                </>
                              )}
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  )
                }

                // State: POSSIBLE GL CANDIDATE / AI SUGGESTED (Review Required / Proposed)
                const score = Math.round((selectedMatch.confidence_score ?? 1) * 100)
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
                        <span className="text-slate-500 block text-[11px]">
                          Candidate Journal ID
                        </span>
                        <span className="font-semibold text-slate-200 font-mono">
                          {selectedMatch.journal_entry?.id
                            ? `#JE-${selectedMatch.journal_entry.id.substring(0, 8)}`
                            : selectedMatch.journal_entry_id
                              ? `#JE-${selectedMatch.journal_entry_id.substring(0, 8)}`
                              : 'N/A'}
                        </span>
                      </div>
                      <div>
                        <span className="text-slate-500 block text-[11px]">Ledger Entry Date</span>
                        <span className="font-semibold text-slate-200 font-mono">
                          {formatCardDate(selectedMatch.journal_entry?.entry_date || '')}
                        </span>
                      </div>
                      <div className="col-span-2 border-t border-slate-800 pt-2">
                        <span className="text-slate-500 block text-[11px]">
                          Journal Description
                        </span>
                        <span className="font-semibold text-slate-100">
                          {selectedMatch.journal_entry?.description || 'Proposed Candidate Journal Entry'}
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
                                selectedMatch.amount_score >= 0.9
                                  ? 'text-emerald-400'
                                  : 'text-rose-400'
                              }`}
                            >
                              {selectedMatch.amount_score >= 0.9 ? '✓' : '✕'}{' '}
                              <span>Similar amount</span>
                            </div>
                          )}
                          {selectedMatch.vendor_score != null && (
                            <div
                              className={`flex items-center gap-1.5 ${
                                selectedMatch.vendor_score >= 0.7
                                  ? 'text-emerald-400'
                                  : 'text-amber-400'
                              }`}
                            >
                              {selectedMatch.vendor_score >= 0.7 ? '✓' : '⚠'}{' '}
                              <span>Vendor/Memo</span>
                            </div>
                          )}
                          {selectedMatch.date_score != null && (
                            <div
                              className={`flex items-center gap-1.5 ${
                                selectedMatch.date_score >= 0.8
                                  ? 'text-emerald-400'
                                  : 'text-amber-400'
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

                    {/* Actions Bar for Possible Match (Section 12) */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pt-2 border-t border-slate-800/80">
                      <span className="text-[11px] text-amber-400 font-medium">
                        Human review required
                      </span>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          disabled={actionLoading}
                          onClick={() => handleUnmatch(selectedMatch.id)}
                          className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 hover:border-slate-600 text-xs font-semibold transition-colors cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed flex items-center gap-1.5"
                        >
                          {actionLoading ? (
                            <>
                              <Loader2 className="w-3.5 h-3.5 animate-spin text-purple-400" />
                              <span className="text-[11px] text-purple-300">Unmatching…</span>
                            </>
                          ) : (
                            'Mark Unmatched'
                          )}
                        </button>
                        <button
                          type="button"
                          onClick={() => setShowFindMatchModal(true)}
                          className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-semibold transition-colors cursor-pointer"
                        >
                          Find Another Match
                        </button>
                        <button
                          type="button"
                          disabled={actionLoading}
                          onClick={() => onAcceptMatch?.(selectedMatch.id)}
                          className="px-3.5 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold transition-colors shadow-md shadow-amber-600/20 flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                        >
                          {actionLoading ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <CheckCircle2 className="w-3.5 h-3.5" />
                          )}
                          Confirm Match
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

      {/* Modal: Find & Select Matching General Ledger Entry */}
      {showFindMatchModal && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 w-full max-w-2xl rounded-2xl p-6 shadow-2xl space-y-4 max-h-[85vh] flex flex-col">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-base font-bold text-white flex items-center gap-2">
                  <Search className="w-4 h-4 text-emerald-400" />
                  Select Matching General Ledger Entry
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Pick a posted journal entry to link with this transaction.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowFindMatchModal(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input
                type="text"
                placeholder="Search ledger entries by description, date, or #JE-ID..."
                value={findMatchSearch}
                onChange={(e) => setFindMatchSearch(e.target.value)}
                className="w-full pl-9 pr-4 py-2 rounded-xl bg-slate-950/70 border border-slate-700 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500/50"
              />
            </div>

            <div className="flex-1 overflow-y-auto space-y-2 pr-1">
              {postedJournalEntries
                .filter((je) => {
                  if (!findMatchSearch.trim()) return true
                  const q = findMatchSearch.toLowerCase().trim()
                  return (
                    je.description.toLowerCase().includes(q) ||
                    je.entry_date.includes(q) ||
                    je.id.toLowerCase().includes(q)
                  )
                })
                .map((je) => (
                  <div
                    key={je.id}
                    className="p-3 rounded-xl bg-slate-950/50 border border-slate-800 hover:border-emerald-500/50 hover:bg-slate-800/60 transition-colors flex items-center justify-between gap-4"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-white">{je.description}</span>
                        <span className="text-[10px] font-mono text-indigo-400">
                          #JE-{je.id.substring(0, 8)}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 font-mono mt-0.5">
                        Date: {formatCardDate(je.entry_date)}
                      </p>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-xs font-bold font-mono text-emerald-400">
                        {formatCardAmount(je.total_debit || 0)}
                      </span>
                      <button
                        type="button"
                        onClick={async () => {
                          if (selectedTx) {
                            try {
                              await manualMatchReconciliation(
                                selectedTx.id,
                                je.id,
                                `Manually linked to #JE-${je.id.substring(0, 8)}`
                              )
                              showToast(
                                `Linked transaction to Journal Entry #JE-${je.id.substring(0, 8)}`
                              )
                              onRefresh?.()
                            } catch (err) {
                              console.error('Failed to link match:', err)
                            }
                          }
                          setShowFindMatchModal(false)
                        }}
                        className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs transition-colors cursor-pointer"
                      >
                        Link Match
                      </button>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        </div>
      )}

      {/* Modal: Interactive Create / Edit Adjusting Journal Entry from Unmatched Bank Mutation */}
      {showCreateJEModal && selectedTx && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-slate-900 border border-slate-700/80 w-full max-w-3xl rounded-2xl p-6 shadow-2xl space-y-5 my-auto max-h-[92vh] flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-slate-800 pb-3 shrink-0">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-purple-500/10 border border-purple-500/30 flex items-center justify-center text-purple-400">
                  <PlusCircle className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-bold text-white tracking-wide">
                      Create Adjusting Journal Entry
                    </h3>
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30 uppercase tracking-wider">
                      Manual / AI-Assisted
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Customize double-entry accounts, amounts, or use AI prefilled recommendation before posting.
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {suggestion?.suggested_lines && suggestion.suggested_lines.length >= 2 && (
                  <button
                    type="button"
                    onClick={resetToAISuggestion}
                    className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-purple-300 border border-purple-500/30 text-[11px] font-medium transition-colors flex items-center gap-1.5 cursor-pointer"
                    title="Reset lines back to AI suggestion"
                  >
                    <RotateCcw className="w-3.5 h-3.5 text-purple-400" />
                    Reset to AI Suggestion
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setShowCreateJEModal(false)}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Scrollable Body */}
            <div className="space-y-4 overflow-y-auto flex-1 pr-1">
              {/* Bank Transaction Reference Box */}
              <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 space-y-2">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-slate-400 font-semibold uppercase tracking-wider flex items-center gap-1.5">
                    <Building2 className="w-3.5 h-3.5 text-blue-400" /> Source Bank Mutation
                  </span>
                  <span className="font-mono text-slate-500">Ref: {selectedTx.reference_number || 'N/A'}</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs pt-1">
                  <div>
                    <span className="text-[10px] text-slate-500 block">Bank Description</span>
                    <span className="font-semibold text-white">{selectedTx.description}</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 block">Transaction Date</span>
                    <span className="font-mono text-slate-300 font-medium">{formatCardDate(selectedTx.transaction_date)}</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 block">Mutation Amount</span>
                    <span className={`font-mono font-bold ${selectedTx.amount < 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                      {formatCardAmount(selectedTx.amount, selectedTx.currency)}
                    </span>
                  </div>
                </div>
              </div>

              {/* Journal Header Inputs */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="text-[11px] font-semibold text-slate-400 block mb-1">
                    Entry Date <span className="text-rose-400">*</span>
                  </label>
                  <input
                    type="date"
                    value={entryDate}
                    onChange={(e) => setEntryDate(e.target.value)}
                    className="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-700 text-white text-xs font-mono focus:outline-none focus:border-purple-500 transition-colors"
                  />
                </div>
                <div className="sm:col-span-2">
                  <label className="text-[11px] font-semibold text-slate-400 block mb-1">
                    Journal Description / Memo <span className="text-rose-400">*</span>
                  </label>
                  <input
                    type="text"
                    value={entryDescription}
                    onChange={(e) => setEntryDescription(e.target.value)}
                    placeholder="Enter journal description..."
                    className="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-700 text-white text-xs focus:outline-none focus:border-purple-500 transition-colors"
                  />
                </div>
              </div>

              {/* Interactive Double-Entry Lines Table */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                    <BookOpen className="w-3.5 h-3.5 text-purple-400" />
                    Double-Entry Journal Lines
                  </span>
                  <button
                    type="button"
                    onClick={handleAddLine}
                    className="px-2.5 py-1 rounded-lg bg-purple-950/60 hover:bg-purple-900/80 border border-purple-500/40 text-purple-300 text-[11px] font-semibold transition-colors flex items-center gap-1 cursor-pointer"
                  >
                    <Plus className="w-3.5 h-3.5 text-purple-400" />
                    Add Line
                  </button>
                </div>

                <div className="rounded-xl border border-slate-800 overflow-hidden bg-slate-950/60">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="border-b border-slate-800 bg-slate-900/80 text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                        <th className="py-2 px-3 w-5/12">Account (COA)</th>
                        <th className="py-2 px-2 w-3/12">Line Memo</th>
                        <th className="py-2 px-2 text-right w-2/12">Debit (IDR)</th>
                        <th className="py-2 px-2 text-right w-2/12">Credit (IDR)</th>
                        <th className="py-2 px-2 text-center w-8"></th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 text-xs">
                      {journalLines.map((line, idx) => (
                        <tr key={idx} className="hover:bg-slate-900/40 transition-colors">
                          {/* Account Dropdown */}
                          <td className="py-2 px-3">
                            <select
                              value={line.account_code}
                              onChange={(e) => handleLineAccountChange(idx, e.target.value)}
                              className="w-full px-2 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-slate-200 text-xs focus:outline-none focus:border-purple-500 transition-colors"
                            >
                              {dbCOA.map((coa: ChartOfAccountResponse) => (
                                <option key={coa.account_code} value={coa.account_code}>
                                  [{coa.account_code}] {coa.account_name} ({coa.account_type})
                                </option>
                              ))}
                            </select>
                          </td>

                          {/* Line Memo */}
                          <td className="py-2 px-2">
                            <input
                              type="text"
                              value={line.description || ''}
                              onChange={(e) => handleLineFieldChange(idx, 'description', e.target.value)}
                              placeholder="Line description"
                              className="w-full px-2 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-slate-200 text-xs focus:outline-none focus:border-purple-500 transition-colors"
                            />
                          </td>

                          {/* Debit Amount */}
                          <td className="py-2 px-2 text-right">
                            <input
                              type="number"
                              min="0"
                              step="any"
                              value={line.debit_amount || ''}
                              onChange={(e) => handleLineFieldChange(idx, 'debit_amount', e.target.value)}
                              placeholder="0"
                              className="w-full px-2 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-emerald-400 font-mono font-semibold text-right text-xs focus:outline-none focus:border-purple-500 transition-colors"
                            />
                          </td>

                          {/* Credit Amount */}
                          <td className="py-2 px-2 text-right">
                            <input
                              type="number"
                              min="0"
                              step="any"
                              value={line.credit_amount || ''}
                              onChange={(e) => handleLineFieldChange(idx, 'credit_amount', e.target.value)}
                              placeholder="0"
                              className="w-full px-2 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-slate-200 font-mono font-semibold text-right text-xs focus:outline-none focus:border-purple-500 transition-colors"
                            />
                          </td>

                          {/* Remove Row */}
                          <td className="py-2 px-2 text-center">
                            <button
                              type="button"
                              disabled={journalLines.length <= 2}
                              onClick={() => handleRemoveLine(idx)}
                              className="p-1 rounded text-slate-500 hover:text-rose-400 hover:bg-slate-800 disabled:opacity-30 disabled:hover:text-slate-500 disabled:hover:bg-transparent transition-colors cursor-pointer"
                              title={journalLines.length <= 2 ? 'Minimum 2 lines required' : 'Remove line'}
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className="border-t border-slate-800 bg-slate-900/90 text-xs font-mono font-bold">
                        <td colSpan={2} className="py-2.5 px-3 text-slate-400 text-right">
                          Total:
                        </td>
                        <td className="py-2.5 px-2 text-right text-emerald-400 font-semibold">
                          {formatCardAmount(totalDebit)}
                        </td>
                        <td className="py-2.5 px-2 text-right text-slate-200 font-semibold">
                          {formatCardAmount(totalCredit)}
                        </td>
                        <td></td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </div>

              {/* Real-time Balanced Verification Banner */}
              <div
                className={`p-3 rounded-xl border flex items-center justify-between text-xs transition-colors ${
                  isBalanced
                    ? 'bg-emerald-950/30 border-emerald-500/40 text-emerald-300'
                    : 'bg-rose-950/30 border-rose-500/40 text-rose-300'
                }`}
              >
                <div className="flex items-center gap-2 font-medium">
                  {isBalanced ? (
                    <>
                      <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                      <span>Balanced! Double-entry mathematical equality verified (Debits == Credits).</span>
                    </>
                  ) : (
                    <>
                      <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                      <span>
                        Unbalanced Journal Entry — Difference: <strong>{formatCardAmount(imbalance)}</strong>. Debits must equal Credits to post.
                      </span>
                    </>
                  )}
                </div>
                <div className="font-mono font-bold text-xs shrink-0">
                  {isBalanced ? (
                    <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                      Diff: Rp 0
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30">
                      Diff: {formatCardAmount(imbalance)}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Modal Footer Actions */}
            <div className="flex items-center justify-between border-t border-slate-800 pt-3 shrink-0">
              <div className="text-[11px] text-slate-400">
                {journalLines.length} double-entry lines
              </div>

              <div className="flex items-center gap-3">
                <button
                  type="button"
                  disabled={isPostingJE}
                  onClick={() => setShowCreateJEModal(false)}
                  className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold text-xs transition-colors cursor-pointer disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={isPostingJE || !isBalanced}
                  onClick={handleSaveAndPostJournalEntry}
                  className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-xs transition-colors shadow-md shadow-purple-600/20 flex items-center gap-1.5 cursor-pointer"
                >
                  {isPostingJE ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" /> Posting to Ledger...
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="w-4 h-4" /> Save &amp; Post Journal Entry
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Investigate GL Entry */}
      {showInvestigateModal && selectedGL && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 w-full max-w-xl rounded-2xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-base font-bold text-white flex items-center gap-2">
                  <Eye className="w-4 h-4 text-indigo-400" />
                  Investigate GL Entry #JE-{selectedGL.id.substring(0, 8)}
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">Posted ledger transaction details.</p>
              </div>
              <button
                type="button"
                onClick={() => setShowInvestigateModal(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3 bg-slate-950/60 p-4 rounded-xl border border-slate-800 text-xs">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-slate-400 block text-[11px]">Description</span>
                  <span className="font-bold text-white text-sm">{selectedGL.description}</span>
                </div>
                <div className="text-right">
                  <span className="text-slate-400 block text-[11px]">Total Debit</span>
                  <span className="font-bold font-mono text-indigo-400">
                    {formatCardAmount(selectedGL.total_debit || 0)}
                  </span>
                </div>
              </div>
              <p className="text-[11px] text-slate-400 font-mono">
                Entry Date: {formatCardDate(selectedGL.entry_date)} • Status: {selectedGL.status}
              </p>
            </div>

            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={() => setShowInvestigateModal(false)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-semibold text-xs transition-colors cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}


