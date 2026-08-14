import React, { useEffect, useState } from 'react'
import { TrialBalanceSummaryCard } from './TrialBalanceSummaryCard'
import { JournalEntryListTable } from './JournalEntryListTable'
import { JournalDetailModal } from './JournalDetailModal'
import type { JournalEntryResponse, TrialBalanceResponse } from '../../services/api'
import { fetchJournalEntries, fetchTrialBalance } from '../../services/api'

interface GeneralLedgerViewProps {
  onNavigateToReview?: () => void
}

export const GeneralLedgerView: React.FC<GeneralLedgerViewProps> = ({ onNavigateToReview }) => {
  const [entries, setEntries] = useState<JournalEntryResponse[]>([])
  const [trialBalance, setTrialBalance] = useState<TrialBalanceResponse | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [statusFilter, setStatusFilter] = useState<string>('posted')
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(null)

  const loadData = async () => {
    setLoading(true)
    try {
      const [entriesRes, tbRes] = await Promise.all([
        fetchJournalEntries({ status: statusFilter || undefined, limit: 50 }),
        fetchTrialBalance(),
      ])
      setEntries(entriesRes.items)
      setTrialBalance(tbRes)
    } catch (err: unknown) {
      console.error('Failed to load general ledger data:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [statusFilter])

  return (
    <div className="space-y-6">
      {/* Trial Balance Card */}
      <TrialBalanceSummaryCard trialBalance={trialBalance} loading={loading} onRefresh={loadData} />

      {/* Journal Entry List Table */}
      <JournalEntryListTable
        entries={entries}
        loading={loading}
        onRefresh={loadData}
        onSelectEntry={(id) => setSelectedEntryId(id)}
        statusFilter={statusFilter}
        onStatusFilterChange={setStatusFilter}
      />

      {/* Journal Detail Modal */}
      {selectedEntryId && (
        <JournalDetailModal
          entryId={selectedEntryId}
          onClose={() => setSelectedEntryId(null)}
          onPosted={loadData}
          onNavigateToReview={onNavigateToReview}
        />
      )}
    </div>
  )
}
