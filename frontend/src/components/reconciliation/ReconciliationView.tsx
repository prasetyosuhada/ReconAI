import React, { useEffect, useState } from 'react'
import { ReconciliationHeader } from './ReconciliationHeader'
import { Reconciliation2ColumnView } from './Reconciliation2ColumnView'
import type { BankTransactionResponse, ReconciliationMatchResponse } from '../../services/api'
import { fetchBankTransactions, fetchReconciliationMatches } from '../../services/api'

export const ReconciliationView: React.FC = () => {
  const [activeImportId, setActiveImportId] = useState<string | null>(null)
  const [transactions, setTransactions] = useState<BankTransactionResponse[]>([])
  const [matches, setMatches] = useState<ReconciliationMatchResponse[]>([])
  const [loading, setLoading] = useState<boolean>(false)
  const [selectedTxId, setSelectedTxId] = useState<string | null>(null)

  const loadData = async (importId?: string) => {
    const targetId = importId || activeImportId
    if (!targetId) return

    setLoading(true)
    try {
      const [txRes, matchRes] = await Promise.all([
        fetchBankTransactions(targetId),
        fetchReconciliationMatches({ bank_statement_import_id: targetId }),
      ])
      setTransactions(txRes.items)
      setMatches(matchRes.items)
      if (txRes.items.length > 0 && !selectedTxId) {
        setSelectedTxId(txRes.items[0].id)
      }
    } catch (err: unknown) {
      console.error('Failed to load reconciliation data:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (activeImportId) {
      loadData(activeImportId)
    }
  }, [activeImportId])

  const matchedCount = matches.filter(
    (m) => m.status === 'accepted' || m.status === 'matched'
  ).length
  const proposedCount = matches.filter((m) => m.status === 'proposed').length
  const unmatchedCount = transactions.length - (matchedCount + proposedCount)

  return (
    <div className="space-y-6">
      {/* Header Statistics & Control Actions */}
      <ReconciliationHeader
        totalCount={transactions.length}
        matchedCount={matchedCount}
        proposedCount={proposedCount}
        unmatchedCount={unmatchedCount < 0 ? 0 : unmatchedCount}
        activeImportId={activeImportId}
        onImportSuccess={(newImportId) => {
          setActiveImportId(newImportId)
        }}
        onRunSuccess={() => {
          loadData(activeImportId || undefined)
        }}
      />

      {/* 2-Column Split Reconciliation Dashboard */}
      <Reconciliation2ColumnView
        transactions={transactions}
        matches={matches}
        loading={loading}
        selectedTxId={selectedTxId}
        onSelectTx={(txId) => setSelectedTxId(txId)}
      />
    </div>
  )
}
