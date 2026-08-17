import React, { useCallback, useEffect, useState } from 'react'
import { ReconciliationHeader } from './ReconciliationHeader'
import { ReconciliationBalanceSummary } from './ReconciliationBalanceSummary'
import { ReconciliationCompletionBanner } from './ReconciliationCompletionBanner'
import { ReconciliationAuditTimeline } from './ReconciliationAuditTimeline'
import {
  ReconciliationFiltersToolbar,
  type ReconFilterType,
} from './ReconciliationFiltersToolbar'
import { Reconciliation2ColumnView } from './Reconciliation2ColumnView'
import type {
  BankStatementImportResponse,
  BankTransactionResponse,
  ChartOfAccountResponse,
  JournalEntryResponse,
  ReconciliationMatchResponse,
} from '../../services/api'
import {
  acceptReconciliationMatch,
  fetchBankStatementImports,
  fetchBankTransactions,
  fetchChartOfAccounts,
  fetchJournalEntries,
  fetchReconciliationMatches,
  rejectReconciliationMatch,
} from '../../services/api'

export const ReconciliationView: React.FC = () => {
  const [imports, setImports] = useState<BankStatementImportResponse[]>([])
  const [activeImportId, setActiveImportId] = useState<string | null>(null)
  const [transactions, setTransactions] = useState<BankTransactionResponse[]>([])
  const [matches, setMatches] = useState<ReconciliationMatchResponse[]>([])
  const [journalEntries, setJournalEntries] = useState<JournalEntryResponse[]>([])
  const [chartOfAccounts, setChartOfAccounts] = useState<ChartOfAccountResponse[]>([])
  const [loading, setLoading] = useState<boolean>(false)
  const [actionLoading, setActionLoading] = useState<boolean>(false)
  const [selectedTxId, setSelectedTxId] = useState<string | null>(null)
  const [selectedGLEntryId, setSelectedGLEntryId] = useState<string | null>(null)
  const [activeFilter, setActiveFilter] = useState<ReconFilterType>('all')
  const [searchQuery, setSearchQuery] = useState<string>('')
  const [showAuditTimeline, setShowAuditTimeline] = useState<boolean>(false)

  // Load bank transactions, matches, posted GL entries, and COA
  const loadData = useCallback(async (importId: string) => {
    setLoading(true)
    try {
      const [txRes, matchRes, jeRes, coaRes] = await Promise.all([
        fetchBankTransactions(importId),
        fetchReconciliationMatches({ bank_statement_import_id: importId }),
        fetchJournalEntries({ status: 'posted', limit: 100 }),
        fetchChartOfAccounts().catch(() => ({ items: [], total: 0, limit: 100, offset: 0 })),
      ])
      setTransactions(txRes.items)
      setMatches(matchRes.items)
      setJournalEntries(jeRes.items)
      setChartOfAccounts(coaRes.items)
      setSelectedTxId((prev) => (txRes.items.length > 0 && !prev ? txRes.items[0].id : prev))
      if (jeRes.items.length > 0) {
        setSelectedGLEntryId((prev) => prev ?? jeRes.items[0].id)
      }
    } catch (err: unknown) {
      console.error('Failed to load reconciliation data:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  // On mount: fetch all bank statement imports and auto-select the latest one
  useEffect(() => {
    const init = async () => {
      try {
        const res = await fetchBankStatementImports({ limit: 50 })
        setImports(res.items)
        if (res.items.length > 0) {
          // items are sorted by imported_at DESC from backend
          const latestId = res.items[0].id
          setActiveImportId(latestId)
          await loadData(latestId)
        }
      } catch (err) {
        console.error('Failed to load bank statement imports:', err)
      }
    }
    init()
  }, [loadData])

  // Reload when activeImportId changes (e.g., user switches batch via dropdown)
  useEffect(() => {
    if (activeImportId) {
      setSelectedTxId(null)
      loadData(activeImportId)
    }
  }, [activeImportId, loadData])

  const handleImportSuccess = (newImportId: string, newImport: BankStatementImportResponse) => {
    setImports((prev) => [newImport, ...prev])
    setActiveImportId(newImportId)
  }

  const matchedCount = matches.filter(
    (m) => m.status === 'accepted' || m.status === 'matched'
  ).length
  const proposedCount = matches.filter((m) => m.status === 'proposed').length
  const unmatchedCount = Math.max(0, transactions.length - (matchedCount + proposedCount))

  // Find set of Journal Entries matched to bank transactions
  const matchedJEIds = new Set(
    matches
      .filter(
        (m) =>
          m.journal_entry_id &&
          (m.status === 'accepted' || m.status === 'matched' || m.status === 'proposed')
      )
      .map((m) => m.journal_entry_id)
  )

  // GL-Only entries (posted journal entries not matched to any bank mutation in this batch)
  const allGLOnlyEntries = journalEntries.filter((je) => !matchedJEIds.has(je.id))
  const filteredGLOnlyEntries = allGLOnlyEntries.filter((je) => {
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim()
      const descMatch = je.description.toLowerCase().includes(q)
      const amtMatch = (je.total_debit || 0).toString().includes(q)
      const dateMatch = je.entry_date.toLowerCase().includes(q)
      const idMatch = je.id.toLowerCase().includes(q)
      return descMatch || amtMatch || dateMatch || idMatch
    }
    return true
  })

  // Determine Statement Period from transactions
  const statementPeriod = (() => {
    if (transactions.length === 0) return 'Aug 01 – Aug 31, 2026'
    const sortedDates = [...transactions]
      .map((t) => t.transaction_date)
      .sort((a, b) => new Date(a).getTime() - new Date(b).getTime())
    const formatDate = (iso: string) => {
      try {
        const d = new Date(iso)
        return d.toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' })
      } catch {
        return iso
      }
    }
    return `${formatDate(sortedDates[0])} – ${formatDate(sortedDates[sortedDates.length - 1])}`
  })()

  // Calculate Bank Balance vs GL Balance Difference
  const bankBalance = transactions.reduce((acc, t) => acc + t.amount, 0)
  const glBalance = matches
    .filter((m) => m.journal_entry_id && (m.status === 'accepted' || m.status === 'matched'))
    .reduce((acc, m) => acc + (m.journal_entry?.total_debit || 0), 0)
  const difference = Math.abs(bankBalance - glBalance)

  // Reconciliation Completion state: transactions exist, difference is Rp0, and all matched
  const isComplete =
    transactions.length > 0 &&
    (difference < 0.01 || matchedCount === transactions.length) &&
    proposedCount === 0 &&
    unmatchedCount === 0

  // Filter transactions based on active tab and search query
  const filteredTransactions = transactions.filter((tx) => {
    const match = matches.find((m) => m.bank_transaction_id === tx.id)
    const isMatched = match?.status === 'accepted' || match?.status === 'matched'
    const isProposed = match?.status === 'proposed'
    const isUnmatched =
      !match || match.status === 'unmatched' || match.match_rule_type === 'unmatched'

    if (activeFilter === 'matched' && !isMatched) return false
    if (activeFilter === 'needs_review' && !isProposed) return false
    if (activeFilter === 'bank_only' && !isUnmatched) return false
    if (activeFilter === 'reconciled' && !isMatched) return false
    if (activeFilter === 'gl_only') return false

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim()
      const descMatch = tx.description.toLowerCase().includes(q)
      const refMatch = tx.reference_number?.toLowerCase().includes(q) ?? false
      const amtMatch = tx.amount.toString().includes(q)
      const dateMatch = tx.transaction_date.toLowerCase().includes(q)
      const idMatch = tx.id.toLowerCase().includes(q)
      return descMatch || refMatch || amtMatch || dateMatch || idMatch
    }

    return true
  })

  // Auto select active transaction when filter changes
  useEffect(() => {
    if (activeFilter === 'gl_only') {
      if (filteredGLOnlyEntries.length > 0) {
        const stillExists = filteredGLOnlyEntries.some((g) => g.id === selectedGLEntryId)
        if (!stillExists) {
          setSelectedGLEntryId(filteredGLOnlyEntries[0].id)
        }
      }
    } else if (filteredTransactions.length > 0) {
      const stillExists = filteredTransactions.some((t) => t.id === selectedTxId)
      if (!stillExists) {
        setSelectedTxId(filteredTransactions[0].id)
      }
    }
  }, [activeFilter, filteredGLOnlyEntries, filteredTransactions, selectedGLEntryId, selectedTxId])

  // Handlers for accepting and rejecting reconciliation matches
  const handleAcceptMatch = async (matchId: string) => {
    setActionLoading(true)
    try {
      await acceptReconciliationMatch(matchId)
      setMatches((prev) =>
        prev.map((m) => (m.id === matchId ? { ...m, status: 'accepted' } : m))
      )
      if (activeImportId) {
        await loadData(activeImportId)
      }
    } catch (err) {
      console.error('Failed to accept match:', err)
    } finally {
      setActionLoading(false)
    }
  }

  const handleRejectMatch = async (matchId: string) => {
    setActionLoading(true)
    try {
      await rejectReconciliationMatch(matchId)
      setMatches((prev) =>
        prev.map((m) => (m.id === matchId ? { ...m, status: 'rejected' } : m))
      )
      if (activeImportId) {
        await loadData(activeImportId)
      }
    } catch (err) {
      console.error('Failed to reject match:', err)
    } finally {
      setActionLoading(false)
    }
  }

  const activeImport = imports.find((i) => i.id === activeImportId)

  return (
    <div className="space-y-6">
      {/* Header Statistics & Control Actions */}
      <ReconciliationHeader
        totalCount={transactions.length}
        matchedCount={matchedCount}
        proposedCount={proposedCount}
        unmatchedCount={unmatchedCount}
        activeImportId={activeImportId}
        imports={imports}
        transactions={transactions}
        onSelectImport={(id) => setActiveImportId(id)}
        onImportSuccess={handleImportSuccess}
        onRunSuccess={() => {
          if (activeImportId) loadData(activeImportId)
        }}
      />

      {/* Reconciliation Balance Comparison & Progress */}
      <ReconciliationBalanceSummary
        transactions={transactions}
        matches={matches}
        totalCount={transactions.length}
        matchedCount={matchedCount}
        proposedCount={proposedCount}
        unmatchedCount={unmatchedCount}
        loading={loading}
      />

      {/* Celebratory Completion State Banner (Section 7) */}
      <ReconciliationCompletionBanner
        isComplete={isComplete}
        statementPeriod={statementPeriod}
        activeImport={activeImport}
        transactions={transactions}
        matches={matches}
        onOpenAuditTrail={() => setShowAuditTimeline(true)}
      />

      {/* Filters Toolbar & Search */}
      <ReconciliationFiltersToolbar
        activeFilter={activeFilter}
        onSelectFilter={setActiveFilter}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        counts={{
          all: transactions.length,
          matched: matchedCount,
          needs_review: proposedCount,
          bank_only: unmatchedCount,
          gl_only: allGLOnlyEntries.length,
          reconciled: matchedCount,
        }}
      />

      {/* 2-Column Split Reconciliation Dashboard */}
      <Reconciliation2ColumnView
        transactions={filteredTransactions}
        matches={matches}
        glOnlyEntries={filteredGLOnlyEntries}
        postedJournalEntries={journalEntries}
        chartOfAccounts={chartOfAccounts}
        activeFilter={activeFilter}
        loading={loading}
        actionLoading={actionLoading}
        selectedTxId={selectedTxId}
        selectedGLEntryId={selectedGLEntryId}
        onSelectTx={(txId) => setSelectedTxId(txId)}
        onSelectGLEntry={(glId) => setSelectedGLEntryId(glId)}
        onAcceptMatch={handleAcceptMatch}
        onRejectMatch={handleRejectMatch}
        onRefresh={() => {
          if (activeImportId) loadData(activeImportId)
        }}
      />

      {/* Activity Timeline & Audit Trail Modal (Section 15) */}
      <ReconciliationAuditTimeline
        activeImport={activeImport}
        isOpen={showAuditTimeline}
        onClose={() => setShowAuditTimeline(false)}
      />
    </div>
  )
}

