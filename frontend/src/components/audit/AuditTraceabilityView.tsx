import React, { useEffect, useRef, useState } from 'react'
import {
  AlertCircle,
  BookOpen,
  Calendar,
  FileText,
  Filter,
  Globe,
  History,
  Landmark,
  Loader2,
  RefreshCw,
  Search,
  X,
} from 'lucide-react'
import { AuditTimeline } from './AuditTimeline'
import { AuditStatusStrip } from './AuditStatusStrip'
import { AuditLifecycleStepper } from './AuditLifecycleStepper'
import type {
  AuditEventResponse,
  BankTransactionResponse,
  DocumentAuditTraceabilityResponse,
  DocumentResponse,
  JournalEntryResponse,
} from '../../services/api'
import {
  fetchAuditEvents,
  fetchBankTransactions,
  fetchDocumentAuditTraceability,
  fetchDocuments,
  fetchJournalEntries,
  fetchJournalEntryAuditTraceability,
  fetchBankTransactionAuditTraceability,
} from '../../services/api'

type TraceMode = 'document' | 'journal_entry' | 'bank_transaction' | 'global'

export const AuditTraceabilityView: React.FC = () => {
  const [traceMode, setTraceMode] = useState<TraceMode>('document')

  // Document mode state
  const [documents, setDocuments] = useState<DocumentResponse[]>([])
  const [selectedDocId, setSelectedDocId] = useState<string>('')

  // Journal entry mode state
  const [journalSearch, setJournalSearch] = useState<string>('')
  const [journalOptions, setJournalOptions] = useState<JournalEntryResponse[]>([])
  const [selectedJournalEntry, setSelectedJournalEntry] = useState<JournalEntryResponse | null>(null)
  const [showJournalDropdown, setShowJournalDropdown] = useState<boolean>(false)
  const [loadingJournals, setLoadingJournals] = useState<boolean>(false)

  // Bank transaction mode state
  const [bankSearch, setBankSearch] = useState<string>('')
  const [bankOptions, setBankOptions] = useState<BankTransactionResponse[]>([])
  const [selectedBankTx, setSelectedBankTx] = useState<BankTransactionResponse | null>(null)
  const [showBankDropdown, setShowBankDropdown] = useState<boolean>(false)
  const [loadingBankTx, setLoadingBankTx] = useState<boolean>(false)

  // Global & common filters
  const [actorFilter, setActorFilter] = useState<string>('')
  const [eventTypeFilter, setEventTypeFilter] = useState<string>('')
  const [startDateFilter, setStartDateFilter] = useState<string>('')
  const [endDateFilter, setEndDateFilter] = useState<string>('')
  const [globalSearch, setGlobalSearch] = useState<string>('')

  // Trace result data
  const [docAudit, setDocAudit] = useState<DocumentAuditTraceabilityResponse | null>(null)
  const [globalEvents, setGlobalEvents] = useState<AuditEventResponse[]>([])
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [highlightedEventId, setHighlightedEventId] = useState<string | null>(null)

  const journalDropdownRef = useRef<HTMLDivElement>(null)
  const bankDropdownRef = useRef<HTMLDivElement>(null)

  // Close typeahead dropdowns when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (journalDropdownRef.current && !journalDropdownRef.current.contains(e.target as Node)) {
        setShowJournalDropdown(false)
      }
      if (bankDropdownRef.current && !bankDropdownRef.current.contains(e.target as Node)) {
        setShowBankDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Load initial documents list
  useEffect(() => {
    const loadDocList = async () => {
      try {
        const res = await fetchDocuments({ limit: 50 })
        setDocuments(res.items)
        if (res.items.length > 0 && !selectedDocId) {
          setSelectedDocId(res.items[0].id)
        }
      } catch (err: unknown) {
        console.error('Failed to fetch document list for audit selector:', err)
      }
    }
    loadDocList()
  }, [])

  // Search journal entries for typeahead
  useEffect(() => {
    if (traceMode !== 'journal_entry') return
    const timer = setTimeout(async () => {
      setLoadingJournals(true)
      try {
        const res = await fetchJournalEntries({ search: journalSearch || undefined, limit: 20 })
        setJournalOptions(res.items)
      } catch (err: unknown) {
        console.error('Failed to search journal entries:', err)
      } finally {
        setLoadingJournals(false)
      }
    }, 200)
    return () => clearTimeout(timer)
  }, [journalSearch, traceMode])

  // Search bank transactions for typeahead
  useEffect(() => {
    if (traceMode !== 'bank_transaction') return
    const timer = setTimeout(async () => {
      setLoadingBankTx(true)
      try {
        const res = await fetchBankTransactions({ search: bankSearch || undefined, limit: 20 })
        setBankOptions(res.items)
      } catch (err: unknown) {
        console.error('Failed to search bank transactions:', err)
      } finally {
        setLoadingBankTx(false)
      }
    }, 200)
    return () => clearTimeout(timer)
  }, [bankSearch, traceMode])

  // Fetch audit data based on active mode and selected entity
  const loadAuditData = async () => {
    setLoading(true)
    setError(null)
    try {
      if (traceMode === 'document') {
        if (selectedDocId) {
          const res = await fetchDocumentAuditTraceability(selectedDocId)
          setDocAudit(res)
        } else {
          setDocAudit(null)
          const res = await fetchAuditEvents({ limit: 50 })
          setGlobalEvents(res.items)
        }
      } else if (traceMode === 'journal_entry') {
        if (selectedJournalEntry) {
          const res = await fetchJournalEntryAuditTraceability(selectedJournalEntry.id)
          setDocAudit(res)
        } else {
          setDocAudit(null)
        }
      } else if (traceMode === 'bank_transaction') {
        if (selectedBankTx) {
          const res = await fetchBankTransactionAuditTraceability(selectedBankTx.id)
          setDocAudit(res)
        } else {
          setDocAudit(null)
        }
      } else if (traceMode === 'global') {
        setDocAudit(null)
        const res = await fetchAuditEvents({
          actor_type: actorFilter || undefined,
          event_type: eventTypeFilter || undefined,
          start_date: startDateFilter || undefined,
          end_date: endDateFilter || undefined,
          search: globalSearch || undefined,
          limit: 100,
        })
        setGlobalEvents(res.items)
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch audit log')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAuditData()
  }, [
    traceMode,
    selectedDocId,
    selectedJournalEntry,
    selectedBankTx,
    actorFilter,
    eventTypeFilter,
    startDateFilter,
    endDateFilter,
    globalSearch,
  ])

  // Determine displayed timeline events
  const displayedEvents =
    traceMode === 'global' ? globalEvents : docAudit ? docAudit.timeline || [] : []

  // Client-side filtering on displayed events (if local filters apply)
  const filteredEvents = displayedEvents.filter((evt) => {
    if (actorFilter && evt.actor_type.toLowerCase() !== actorFilter.toLowerCase()) return false
    if (eventTypeFilter && !evt.event_type.toLowerCase().includes(eventTypeFilter.toLowerCase()))
      return false
    return true
  })

  // Handle stepping into an event from Stepper or Strip
  const handleSelectTransitionEvent = (eventId: string) => {
    setHighlightedEventId(eventId)
    const el = document.getElementById(`audit-event-${eventId}`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
    setTimeout(() => {
      setHighlightedEventId((prev) => (prev === eventId ? null : prev))
    }, 3000)
  }

  // Inline Jump Handlers (Requirement 9)
  const handleJumpToJournalEntry = async (jeId: string) => {
    setTraceMode('journal_entry')
    setJournalSearch(jeId)
    setSelectedJournalEntry({
      id: jeId,
      description: `Journal Entry #${jeId.slice(0, 8)}`,
      entry_date: '',
      status: 'posted',
      total_debit: 0,
      total_credit: 0,
      created_at: new Date().toISOString(),
    })
  }

  const handleJumpToBankTx = async (txId: string) => {
    setTraceMode('bank_transaction')
    setBankSearch(txId)
    setSelectedBankTx({
      id: txId,
      bank_statement_import_id: '',
      transaction_date: '',
      description: `Bank Transaction #${txId.slice(0, 8)}`,
      amount: 0,
      currency: 'IDR',
      status: 'matched',
      created_at: new Date().toISOString(),
    })
  }

  return (
    <div className="space-y-6">
      {/* Header & Mode Controls Card */}
      <div className="relative z-20 p-6 rounded-2xl bg-slate-800/40 border border-slate-700/50 shadow-xl backdrop-blur-sm space-y-5">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
              <History className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white flex items-center gap-2">
                Audit Trail &amp; End-to-End Traceability
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Cross-entity timeline tracing across source documents, general ledger entries, bank
                mutations, and global audit logs.
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={loadAuditData}
            disabled={loading}
            className="p-2.5 rounded-xl bg-slate-900/80 hover:bg-slate-800 border border-slate-700/60 text-slate-300 hover:text-white transition-all disabled:opacity-50 cursor-pointer"
            title="Refresh audit timeline"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {/* Mode Selector (Segmented Tabs) (§4) */}
        <div className="flex flex-wrap items-center gap-1.5 p-1.5 rounded-xl bg-slate-950/80 border border-slate-800">
          <button
            type="button"
            onClick={() => setTraceMode('document')}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
              traceMode === 'document'
                ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            By Document
          </button>

          <button
            type="button"
            onClick={() => {
              setTraceMode('journal_entry')
              if (journalOptions.length === 0) {
                fetchJournalEntries({ limit: 20 }).then((res) => setJournalOptions(res.items))
              }
            }}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
              traceMode === 'journal_entry'
                ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
            }`}
          >
            <BookOpen className="w-3.5 h-3.5" />
            By Journal Entry
          </button>

          <button
            type="button"
            onClick={() => {
              setTraceMode('bank_transaction')
              if (bankOptions.length === 0) {
                fetchBankTransactions({ limit: 20 }).then((res) => setBankOptions(res.items))
              }
            }}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
              traceMode === 'bank_transaction'
                ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
            }`}
          >
            <Landmark className="w-3.5 h-3.5" />
            By Bank Transaction
          </button>

          <button
            type="button"
            onClick={() => setTraceMode('global')}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
              traceMode === 'global'
                ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
            }`}
          >
            <Globe className="w-3.5 h-3.5" />
            Global Events
          </button>
        </div>

        {/* Dynamic Mode Controls Toolbar */}
        {traceMode === 'document' && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
            {/* Document Selector */}
            <div>
              <label className="block text-[11px] font-semibold text-slate-400 mb-1">
                Select Document
              </label>
              <div className="relative">
                <FileText className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                <select
                  value={selectedDocId}
                  onChange={(e) => setSelectedDocId(e.target.value)}
                  className="w-full pl-9 pr-8 py-2 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-slate-100 focus:outline-none focus:border-indigo-500 appearance-none cursor-pointer"
                >
                  <option value="">View All System Audit Events</option>
                  {documents.map((d) => (
                    <option key={d.id} value={d.id}>
                      📄 {d.original_filename} ({d.status})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Actor Filter */}
            <div>
              <label className="block text-[11px] font-semibold text-slate-400 mb-1">
                Actor Filter
              </label>
              <div className="relative">
                <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                <select
                  value={actorFilter}
                  onChange={(e) => setActorFilter(e.target.value)}
                  className="w-full pl-9 pr-8 py-2 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-slate-100 focus:outline-none focus:border-indigo-500 appearance-none cursor-pointer"
                >
                  <option value="">All Actors (Agent, Human, System)</option>
                  <option value="agent">AI Agents</option>
                  <option value="human">Human Reviewers</option>
                  <option value="system">System Engine</option>
                </select>
              </div>
            </div>

            {/* Search Event Type */}
            <div>
              <label className="block text-[11px] font-semibold text-slate-400 mb-1">
                Event Type Filter
              </label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                <input
                  type="text"
                  placeholder="e.g. extraction, bookkeeping..."
                  value={eventTypeFilter}
                  onChange={(e) => setEventTypeFilter(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
              </div>
            </div>
          </div>
        )}

        {/* Mode: By Journal Entry (Typeahead Input) (§4.2 / §4.6) */}
        {traceMode === 'journal_entry' && (
          <div className="space-y-3 pt-1">
            <div className="relative" ref={journalDropdownRef}>
              <label className="block text-[11px] font-semibold text-slate-400 mb-1">
                Search &amp; Select Journal Entry
              </label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search by description, date, #JE-xxxx, or document filename..."
                  value={journalSearch}
                  onFocus={() => setShowJournalDropdown(true)}
                  onChange={(e) => {
                    setJournalSearch(e.target.value)
                    setShowJournalDropdown(true)
                  }}
                  className="w-full pl-9 pr-10 py-2.5 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 shadow-inner"
                />
                {loadingJournals ? (
                  <Loader2 className="w-4 h-4 text-indigo-400 animate-spin absolute right-3 top-1/2 -translate-y-1/2" />
                ) : selectedJournalEntry ? (
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedJournalEntry(null)
                      setJournalSearch('')
                      setDocAudit(null)
                    }}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
                  >
                    <X className="w-4 h-4" />
                  </button>
                ) : null}
              </div>

              {/* Typeahead Dropdown */}
              {showJournalDropdown && (
                <div className="absolute z-50 left-0 right-0 mt-1 max-h-72 overflow-y-auto rounded-xl bg-slate-900/98 border border-slate-700 shadow-2xl divide-y divide-slate-800 ring-1 ring-slate-700/50 backdrop-blur-md">
                  {journalOptions.length === 0 ? (
                    <div className="p-4 text-center text-xs text-slate-400">
                      No matching journal entries found.
                    </div>
                  ) : (
                    journalOptions.map((je) => (
                      <button
                        key={je.id}
                        type="button"
                        onClick={() => {
                          setSelectedJournalEntry(je)
                          setJournalSearch(je.description)
                          setShowJournalDropdown(false)
                        }}
                        className={`w-full p-3 text-left hover:bg-slate-800/80 transition-colors flex items-center justify-between gap-3 cursor-pointer ${
                          selectedJournalEntry?.id === je.id ? 'bg-indigo-950/40' : ''
                        }`}
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-slate-100 text-xs truncate">
                              {je.description}
                            </span>
                            <span className="font-mono text-[10px] text-indigo-400 bg-indigo-500/10 px-1.5 py-0.5 rounded border border-indigo-500/20">
                              #JE-{je.id.slice(0, 8)}
                            </span>
                          </div>
                          <div className="flex items-center gap-3 text-[11px] text-slate-400 mt-1 font-mono">
                            <span>Date: {je.entry_date}</span>
                            {je.document_id ? (
                              <span className="text-emerald-400/90">Linked to Source Doc</span>
                            ) : (
                              <span className="text-amber-400/90">Manual / Standalone Entry</span>
                            )}
                          </div>
                        </div>

                        <div className="text-right shrink-0">
                          <span
                            className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                              je.status === 'posted'
                                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                                : 'bg-amber-500/10 text-amber-300 border border-amber-500/20'
                            }`}
                          >
                            {je.status}
                          </span>
                          <span className="block text-[11px] font-mono text-slate-300 mt-1">
                            IDR {Number(je.total_debit || 0).toLocaleString()}
                          </span>
                        </div>
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Mode: By Bank Transaction (Typeahead Input) (§4.3 / §4.6) */}
        {traceMode === 'bank_transaction' && (
          <div className="space-y-3 pt-1">
            <div className="relative" ref={bankDropdownRef}>
              <label className="block text-[11px] font-semibold text-slate-400 mb-1">
                Search &amp; Select Bank Transaction
              </label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search by description, reference number, amount, or #TX-xxxx..."
                  value={bankSearch}
                  onFocus={() => setShowBankDropdown(true)}
                  onChange={(e) => {
                    setBankSearch(e.target.value)
                    setShowBankDropdown(true)
                  }}
                  className="w-full pl-9 pr-10 py-2.5 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 shadow-inner"
                />
                {loadingBankTx ? (
                  <Loader2 className="w-4 h-4 text-indigo-400 animate-spin absolute right-3 top-1/2 -translate-y-1/2" />
                ) : selectedBankTx ? (
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedBankTx(null)
                      setBankSearch('')
                      setDocAudit(null)
                    }}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
                  >
                    <X className="w-4 h-4" />
                  </button>
                ) : null}
              </div>

              {/* Typeahead Dropdown */}
              {showBankDropdown && (
                <div className="absolute z-50 left-0 right-0 mt-1 max-h-72 overflow-y-auto rounded-xl bg-slate-900/98 border border-slate-700 shadow-2xl divide-y divide-slate-800 ring-1 ring-slate-700/50 backdrop-blur-md">
                  {bankOptions.length === 0 ? (
                    <div className="p-4 text-center text-xs text-slate-400">
                      No matching bank transactions found.
                    </div>
                  ) : (
                    bankOptions.map((tx) => (
                      <button
                        key={tx.id}
                        type="button"
                        onClick={() => {
                          setSelectedBankTx(tx)
                          setBankSearch(tx.description)
                          setShowBankDropdown(false)
                        }}
                        className={`w-full p-3 text-left hover:bg-slate-800/80 transition-colors flex items-center justify-between gap-3 cursor-pointer ${
                          selectedBankTx?.id === tx.id ? 'bg-indigo-950/40' : ''
                        }`}
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-slate-100 text-xs truncate">
                              {tx.description}
                            </span>
                            <span className="font-mono text-[10px] text-teal-400 bg-teal-500/10 px-1.5 py-0.5 rounded border border-teal-500/20">
                              #TX-{tx.id.slice(0, 8)}
                            </span>
                          </div>
                          <div className="flex items-center gap-3 text-[11px] text-slate-400 mt-1 font-mono">
                            <span>Date: {tx.transaction_date}</span>
                            {tx.reference_number && <span>Ref: {tx.reference_number}</span>}
                          </div>
                        </div>

                        <div className="text-right shrink-0">
                          <span
                            className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                              tx.status === 'matched'
                                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                                : 'bg-slate-800 text-slate-300 border border-slate-700'
                            }`}
                          >
                            {tx.status}
                          </span>
                          <span
                            className={`block text-[11px] font-mono font-bold mt-1 ${
                              Number(tx.amount) < 0 ? 'text-rose-400' : 'text-emerald-400'
                            }`}
                          >
                            {Number(tx.amount) < 0 ? '-' : '+'}IDR{' '}
                            {Math.abs(Number(tx.amount)).toLocaleString()}
                          </span>
                        </div>
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Mode: Global Events Filter Toolbar (§4.7) */}
        {traceMode === 'global' && (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 pt-1">
            {/* Free text search */}
            <div>
              <label className="block text-[11px] font-semibold text-slate-400 mb-1">
                Search Events
              </label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search rationale, actor, event..."
                  value={globalSearch}
                  onChange={(e) => setGlobalSearch(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
              </div>
            </div>

            {/* Actor Type */}
            <div>
              <label className="block text-[11px] font-semibold text-slate-400 mb-1">
                Actor Type
              </label>
              <div className="relative">
                <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                <select
                  value={actorFilter}
                  onChange={(e) => setActorFilter(e.target.value)}
                  className="w-full pl-9 pr-8 py-2 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-slate-100 focus:outline-none focus:border-indigo-500 appearance-none cursor-pointer"
                >
                  <option value="">All Actors (Agent, Human, System)</option>
                  <option value="agent">AI Agents</option>
                  <option value="human">Human Reviewers</option>
                  <option value="system">System Engine</option>
                </select>
              </div>
            </div>

            {/* Date Range: Start */}
            <div>
              <label className="block text-[11px] font-semibold text-slate-400 mb-1">
                From Date
              </label>
              <div className="relative">
                <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                <input
                  type="date"
                  value={startDateFilter}
                  onChange={(e) => setStartDateFilter(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-slate-100 focus:outline-none focus:border-indigo-500 [color-scheme:dark]"
                />
              </div>
            </div>

            {/* Date Range: End */}
            <div>
              <label className="block text-[11px] font-semibold text-slate-400 mb-1">
                To Date
              </label>
              <div className="relative">
                <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                <input
                  type="date"
                  value={endDateFilter}
                  onChange={(e) => setEndDateFilter(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-slate-100 focus:outline-none focus:border-indigo-500 [color-scheme:dark]"
                />
              </div>
            </div>
          </div>
        )}

        {/* Selected Context Banner (Document OR Resolved Entity) */}
        {traceMode !== 'global' && docAudit && (
          <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
            <div>
              <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-wider block">
                {docAudit.document_id
                  ? 'Source Document Audit Context'
                  : docAudit.resolved_entity_type === 'bank_transaction'
                    ? 'Bank Transaction Audit Context (Unmatched / Bank-Only)'
                    : 'Journal Entry Audit Context (Manual / Standalone)'}
              </span>
              <p className="font-bold text-slate-100 text-sm">{docAudit.filename}</p>
              <p className="text-slate-400 font-mono text-[11px] mt-0.5">
                {docAudit.document_id ? `Document ID: ${docAudit.document_id}` : `Resolved ID: ${docAudit.resolved_entity_id || '—'}`}
              </p>
            </div>

            <div className="flex items-center gap-3">
              <div className="text-right">
                <span className="text-slate-400 text-[11px] block">Current Status</span>
                <span className="font-bold text-emerald-400 uppercase">
                  {docAudit.current_status || 'PROCESSED'}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Accounting Pipeline Lifecycle Stepper (§5.1) - Rendered only when document context exists */}
        {traceMode !== 'global' && docAudit?.document_id && displayedEvents.length > 0 && (
          <AuditLifecycleStepper
            events={displayedEvents}
            onSelectEvent={handleSelectTransitionEvent}
            activeEventId={highlightedEventId}
          />
        )}

        {/* Status Transition History Strip (§5.4) - Rendered only when document context exists */}
        {traceMode !== 'global' && docAudit?.document_id && displayedEvents.length > 0 && (
          <AuditStatusStrip
            events={displayedEvents}
            onSelectEvent={handleSelectTransitionEvent}
            activeEventId={highlightedEventId}
          />
        )}
      </div>

      {/* Main Timeline Card */}
      <div className="relative z-10 p-6 rounded-2xl bg-slate-800/40 border border-slate-700/50 shadow-xl backdrop-blur-sm space-y-4">
        {error && (
          <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {loading ? (
          <div className="py-16 text-center text-slate-400 space-y-2">
            <Loader2 className="w-8 h-8 animate-spin text-indigo-400 mx-auto" />
            <p className="text-xs">Building chronological audit timeline...</p>
          </div>
        ) : filteredEvents.length === 0 ? (
          <div className="py-16 text-center text-slate-400 space-y-2 bg-slate-900/40 rounded-xl border border-slate-800">
            <History className="w-10 h-10 text-slate-600 mx-auto" />
            <p className="text-sm font-semibold text-slate-300">No Audit Events Found</p>
            <p className="text-xs text-slate-500">
              No audit records match your current trace mode and filter criteria.
            </p>
          </div>
        ) : (
          <AuditTimeline
            events={filteredEvents}
            highlightedEventId={highlightedEventId}
            onSelectJournalEntry={handleJumpToJournalEntry}
            onSelectBankTransaction={handleJumpToBankTx}
          />
        )}
      </div>
    </div>
  )
}
