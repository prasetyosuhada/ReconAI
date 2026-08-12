import React, { useState } from 'react'
import {
  BookOpen,
  CheckCircle2,
  Clock,
  Eye,
  Filter,
  RefreshCw,
  Search,
  Sparkles,
} from 'lucide-react'
import type { JournalEntryResponse } from '../../services/api'

interface JournalEntryListTableProps {
  entries: JournalEntryResponse[]
  loading: boolean
  onRefresh: () => void
  onSelectEntry: (entryId: string) => void
  statusFilter: string
  onStatusFilterChange: (status: string) => void
}

export const JournalEntryListTable: React.FC<JournalEntryListTableProps> = ({
  entries,
  loading,
  onRefresh,
  onSelectEntry,
  statusFilter,
  onStatusFilterChange,
}) => {
  const [searchTerm, setSearchTerm] = useState('')

  const filteredEntries = entries.filter((e) => {
    const matchesSearch =
      e.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (e.agent_name && e.agent_name.toLowerCase().includes(searchTerm.toLowerCase()))
    return matchesSearch
  })

  const getStatusBadge = (status: string) => {
    switch (status.toLowerCase()) {
      case 'posted':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-semibold">
            <CheckCircle2 className="w-3 h-3" />
            Posted
          </span>
        )
      case 'approved':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-semibold">
            Approved
          </span>
        )
      case 'review_required':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs font-semibold">
            <Clock className="w-3 h-3" />
            Review Needed
          </span>
        )
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-400 text-xs font-semibold capitalize">
            {status}
          </span>
        )
    }
  }

  return (
    <div className="p-6 rounded-2xl bg-slate-800/40 border border-slate-700/50 shadow-xl backdrop-blur-sm space-y-4 animate-fade-in">
      {/* Header Toolbar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h3 className="text-lg font-bold text-white flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-indigo-400" />
            General Ledger Journal Entries
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Complete list of posted and pending journal entries.
          </p>
        </div>

        <div className="flex items-center gap-3 w-full sm:w-auto">
          {/* Search */}
          <div className="relative flex-1 sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search description..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 bg-slate-900/80 border border-slate-700/60 rounded-xl text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500/50 transition-all"
            />
          </div>

          {/* Status Filter */}
          <div className="relative">
            <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
            <select
              value={statusFilter}
              onChange={(e) => onStatusFilterChange(e.target.value)}
              className="pl-8 pr-8 py-1.5 bg-slate-900/80 border border-slate-700/60 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-indigo-500/50 transition-all appearance-none cursor-pointer"
            >
              <option value="">Status: All</option>
              <option value="posted">Posted</option>
              <option value="approved">Approved</option>
              <option value="review_required">Review Required</option>
              <option value="draft">Draft</option>
            </select>
          </div>

          {/* Refresh */}
          <button
            type="button"
            onClick={onRefresh}
            disabled={loading}
            className="p-2 rounded-xl bg-slate-900/80 hover:bg-slate-800 border border-slate-700/60 text-slate-300 hover:text-white transition-all disabled:opacity-50"
            title="Refresh journal entries"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Table Content */}
      <div className="overflow-x-auto rounded-xl border border-slate-800/80 bg-slate-950/40">
        <table className="w-full text-left text-xs text-slate-300">
          <thead className="bg-slate-900/80 text-slate-400 border-b border-slate-800 font-semibold uppercase tracking-wider text-[10px]">
            <tr>
              <th className="py-3 px-4">Date</th>
              <th className="py-3 px-4">Description</th>
              <th className="py-3 px-4">Agent / Origin</th>
              <th className="py-3 px-4">Status</th>
              <th className="py-3 px-4 text-right">Debit (IDR)</th>
              <th className="py-3 px-4 text-right">Credit (IDR)</th>
              <th className="py-3 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 font-medium">
            {loading ? (
              [1, 2, 3].map((idx) => (
                <tr key={idx} className="animate-pulse">
                  <td className="py-3.5 px-4">
                    <div className="h-4 bg-slate-800/80 rounded w-20" />
                  </td>
                  <td className="py-3.5 px-4">
                    <div className="h-4 bg-slate-800/80 rounded w-48" />
                  </td>
                  <td className="py-3.5 px-4">
                    <div className="h-4 bg-slate-800/80 rounded w-28" />
                  </td>
                  <td className="py-3.5 px-4">
                    <div className="h-4 bg-slate-800/80 rounded w-16" />
                  </td>
                  <td className="py-3.5 px-4">
                    <div className="h-4 bg-slate-800/80 rounded w-20 ml-auto" />
                  </td>
                  <td className="py-3.5 px-4">
                    <div className="h-4 bg-slate-800/80 rounded w-20 ml-auto" />
                  </td>
                  <td className="py-3.5 px-4 text-right">
                    <div className="h-6 bg-slate-800/80 rounded w-20 ml-auto" />
                  </td>
                </tr>
              ))
            ) : filteredEntries.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-16 text-center text-slate-400 space-y-2">
                  <BookOpen className="w-10 h-10 text-slate-600 mx-auto" />
                  <p className="text-sm font-semibold text-slate-300">No Journal Entries Found</p>
                  <p className="text-xs text-slate-500">
                    No entries match your current filter settings.
                  </p>
                </td>
              </tr>
            ) : (
              filteredEntries.map((entry) => (
                <tr key={entry.id} className="hover:bg-slate-900/60 transition-colors">
                  <td className="py-3.5 px-4 font-mono text-slate-300 whitespace-nowrap">
                    {entry.entry_date}
                  </td>

                  <td className="py-3.5 px-4 font-semibold text-slate-100 max-w-xs truncate">
                    {entry.description}
                  </td>

                  <td className="py-3.5 px-4">
                    <span className="inline-flex items-center gap-1 text-[11px] text-indigo-300 font-mono">
                      <Sparkles className="w-3 h-3 text-indigo-400" />
                      {entry.agent_name || 'Bookkeeping Agent'}
                    </span>
                  </td>

                  <td className="py-3.5 px-4">{getStatusBadge(entry.status)}</td>

                  <td className="py-3.5 px-4 text-right font-mono font-bold text-emerald-400">
                    {entry.total_debit.toLocaleString()}
                  </td>

                  <td className="py-3.5 px-4 text-right font-mono font-bold text-indigo-400">
                    {entry.total_credit.toLocaleString()}
                  </td>

                  <td className="py-3.5 px-4 text-right">
                    <button
                      type="button"
                      onClick={() => onSelectEntry(entry.id)}
                      className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/40 border border-indigo-500/30 text-indigo-300 text-xs font-semibold transition-all hover:scale-105 active:scale-95"
                    >
                      <Eye className="w-3.5 h-3.5" />
                      View Lines
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
