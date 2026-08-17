import React, { useCallback, useEffect, useState } from 'react'
import { ReconciliationHeader } from './ReconciliationHeader'
import { ReconciliationBalanceSummary } from './ReconciliationBalanceSummary'
import {
  ReconciliationFiltersToolbar,
  type ReconFilterType,
} from './ReconciliationFiltersToolbar'
import { Reconciliation2ColumnView } from './Reconciliation2ColumnView'
import type {
  BankStatementImportResponse,
  BankTransactionResponse,
  ReconciliationMatchResponse,
} from '../../services/api'
import {
  fetchBankStatementImports,
  fetchBankTransactions,
  fetchReconciliationMatches,
} from '../../services/api'

export const ReconciliationView: React.FC = () => {
  const [imports, setImports] = useState<BankStatementImportResponse[]>([])
  const [activeImportId, setActiveImportId] = useState<string | null>(null)
  const [transactions, setTransactions] = useState<BankTransactionResponse[]>([])
  const [matches, setMatches] = useState<ReconciliationMatchResponse[]>([])
  const [loading, setLoading] = useState<boolean>(false)
  const [selectedTxId, setSelectedTxId] = useState<string | null>(null)
  const [activeFilter, setActiveFilter] = useState<ReconFilterType>('all')
  const [searchQuery, setSearchQuery] = useState<string>('')

  // Load bank transactions + reconciliation matches for a given import ID
  const loadData = useCallback(async (importId: string) => {
    setLoading(true)
    try {
      const [txRes, matchRes] = await Promise.all([
        fetchBankTransactions(importId),
        fetchReconciliationMatches({ bank_statement_import_id: importId }),
      ])
      setTransactions(txRes.items)
      setMatches(matchRes.items)
      setSelectedTxId((prev) => (txRes.items.length > 0 && !prev ? txRes.items[0].id : prev))
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
    if (filteredTransactions.length > 0) {
      const stillExists = filteredTransactions.some((t) => t.id === selectedTxId)
      if (!stillExists) {
        setSelectedTxId(filteredTransactions[0].id)
      }
    }
  }, [filteredTransactions, selectedTxId])

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
          gl_only: 0,
          reconciled: matchedCount,
        }}
      />

      {/* 2-Column Split Reconciliation Dashboard */}
      <Reconciliation2ColumnView
        transactions={filteredTransactions}
        matches={matches}
        loading={loading}
        selectedTxId={selectedTxId}
        onSelectTx={(txId) => setSelectedTxId(txId)}
      />
    </div>
  )
}

