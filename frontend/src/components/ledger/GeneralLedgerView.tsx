import React, { useCallback, useEffect, useState } from 'react'
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
  const [total, setTotal] = useState<number>(0)
  const [trialBalance, setTrialBalance] = useState<TrialBalanceResponse | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [searchTerm, setSearchTerm] = useState<string>('')
  const [page, setPage] = useState<number>(1)
  const [pageSize, setPageSize] = useState<number>(10)
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [entriesRes, tbRes] = await Promise.all([
        fetchJournalEntries({
          status: statusFilter || undefined,
          search: searchTerm.trim() || undefined,
          limit: pageSize,
          offset: (page - 1) * pageSize,
        }),
        fetchTrialBalance(),
      ])
      setEntries(entriesRes.items)
      setTotal(entriesRes.total)
      setTrialBalance(tbRes)
    } catch (err: unknown) {
      console.error('Failed to load general ledger data:', err)
    } finally {
      setLoading(false)
    }
  }, [statusFilter, searchTerm, page, pageSize])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleStatusFilterChange = (newStatus: string) => {
    setStatusFilter(newStatus)
    setPage(1)
  }

  const handleSearchChange = (newSearch: string) => {
    setSearchTerm(newSearch)
    setPage(1)
  }

  return (
    <div className="space-y-6">
      {/* Trial Balance Card */}
      <TrialBalanceSummaryCard trialBalance={trialBalance} loading={loading} onRefresh={loadData} />

      {/* Journal Entry List Table */}
      <JournalEntryListTable
        entries={entries}
        total={total}
        loading={loading}
        onRefresh={loadData}
        onSelectEntry={(id) => setSelectedEntryId(id)}
        statusFilter={statusFilter}
        onStatusFilterChange={handleStatusFilterChange}
        searchTerm={searchTerm}
        onSearchChange={handleSearchChange}
        page={page}
        pageSize={pageSize}
        onPageChange={setPage}
        onPageSizeChange={(newSize) => {
          setPageSize(newSize)
          setPage(1)
        }}
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

