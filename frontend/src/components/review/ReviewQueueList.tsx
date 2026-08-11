import React, { useState } from 'react'
import {
  AlertTriangle,
  ArrowRight,
  Check,
  CheckCircle2,
  Clock,
  ExternalLink,
  FileCheck,
  Filter,
  Loader2,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  X,
} from 'lucide-react'
import type { ReviewItemResponse } from '../../services/api'
import { approveReviewItem, rejectReviewItem } from '../../services/api'

interface ReviewQueueListProps {
  items: ReviewItemResponse[]
  loading: boolean
  onRefresh: () => void
  onInspectItem: (item: ReviewItemResponse) => void
  statusFilter: string
  onStatusFilterChange: (status: string) => void
  typeFilter: string
  onTypeFilterChange: (type: string) => void
}

export const ReviewQueueList: React.FC<ReviewQueueListProps> = ({
  items,
  loading,
  onRefresh,
  onInspectItem,
  statusFilter,
  onStatusFilterChange,
  typeFilter,
  onTypeFilterChange,
}) => {
  const [searchTerm, setSearchTerm] = useState('')
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null)

  const filteredItems = items.filter((item) => {
    const matchesSearch =
      item.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      item.summary.toLowerCase().includes(searchTerm.toLowerCase())
    return matchesSearch
  })

  const handleQuickApprove = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    setActionLoadingId(id)
    try {
      await approveReviewItem(id)
      onRefresh()
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Approval failed')
    } finally {
      setActionLoadingId(null)
    }
  }

  const handleQuickReject = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    if (!confirm('Are you sure you want to reject this review item?')) return

    setActionLoadingId(id)
    try {
      await rejectReviewItem(id)
      onRefresh()
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Rejection failed')
    } finally {
      setActionLoadingId(null)
    }
  }

  const getPriorityBadge = (priority: string) => {
    switch (priority.toLowerCase()) {
      case 'high':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/10 text-rose-400 border border-rose-500/20 uppercase tracking-wider flex items-center gap-1">
            <AlertTriangle className="w-3 h-3" /> High
          </span>
        )
      case 'normal':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20 uppercase tracking-wider">
            Normal
          </span>
        )
      default:
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-800 text-slate-400 border border-slate-700 uppercase tracking-wider">
            Low
          </span>
        )
    }
  }

  const getTypeBadge = (type: string) => {
    return (
      <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 capitalize flex items-center gap-1">
        <Sparkles className="w-3 h-3 text-indigo-400" />
        {type}
      </span>
    )
  }

  return (
    <div className="p-6 rounded-2xl bg-slate-800/40 border border-slate-700/50 shadow-xl backdrop-blur-sm space-y-5">
      {/* Header & Search / Filter Controls */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div>
          <h3 className="text-lg font-bold text-white flex items-center gap-2">
            <FileCheck className="w-5 h-5 text-indigo-400" />
            Human Review Queue Dashboard
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Review and resolve flagged AI suggestions before posting to General Ledger.
          </p>
        </div>

        {/* Filter Toolbar */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Search */}
          <div className="relative flex-1 sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
            <input
              type="text"
              placeholder="Filter title or summary..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 bg-slate-900/80 border border-slate-700/60 rounded-xl text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500/50 transition-all"
            />
          </div>

          {/* Status Select */}
          <div className="relative">
            <select
              value={statusFilter}
              onChange={(e) => onStatusFilterChange(e.target.value)}
              className="pl-3 pr-8 py-1.5 bg-slate-900/80 border border-slate-700/60 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-indigo-500/50 transition-all appearance-none cursor-pointer"
            >
              <option value="pending">Status: Pending</option>
              <option value="posted">Status: Posted</option>
              <option value="rejected">Status: Rejected</option>
              <option value="">Status: All</option>
            </select>
          </div>

          {/* Type Select */}
          <div className="relative">
            <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
            <select
              value={typeFilter}
              onChange={(e) => onTypeFilterChange(e.target.value)}
              className="pl-8 pr-8 py-1.5 bg-slate-900/80 border border-slate-700/60 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-indigo-500/50 transition-all appearance-none cursor-pointer"
            >
              <option value="">All Types</option>
              <option value="bookkeeping">Bookkeeping</option>
              <option value="extraction">Extraction</option>
              <option value="reconciliation">Reconciliation</option>
              <option value="validation">Validation</option>
            </select>
          </div>

          {/* Refresh */}
          <button
            type="button"
            onClick={onRefresh}
            disabled={loading}
            className="p-2 rounded-xl bg-slate-900/80 hover:bg-slate-800 border border-slate-700/60 text-slate-300 hover:text-white transition-all disabled:opacity-50"
            title="Refresh review items"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Items List */}
      {loading && filteredItems.length === 0 ? (
        <div className="py-16 text-center text-slate-400 space-y-2">
          <Loader2 className="w-8 h-8 animate-spin text-indigo-400 mx-auto" />
          <p className="text-xs">Loading review queue...</p>
        </div>
      ) : filteredItems.length === 0 ? (
        <div className="py-16 text-center text-slate-400 space-y-2 bg-slate-900/30 rounded-2xl border border-slate-800/80">
          <CheckCircle2 className="w-10 h-10 text-emerald-400 mx-auto" />
          <p className="text-sm font-semibold text-slate-200">Review Queue Clear!</p>
          <p className="text-xs text-slate-500">No items match the selected filter criteria.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredItems.map((item) => {
            const isPending = item.status === 'pending'
            const isActioning = actionLoadingId === item.id
            const confPercent = Math.round((item.confidence_score || 0) * 100)

            return (
              <div
                key={item.id}
                onClick={() => onInspectItem(item)}
                className="group relative p-4 rounded-xl bg-slate-950/40 hover:bg-slate-900/80 border border-slate-800/80 hover:border-indigo-500/40 transition-all duration-150 cursor-pointer shadow-md flex flex-col md:flex-row md:items-center justify-between gap-4"
              >
                {/* Left: Priority & Content info */}
                <div className="space-y-2 flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    {getPriorityBadge(item.priority)}
                    {getTypeBadge(item.review_type)}

                    <span className="text-[11px] text-slate-500 flex items-center gap-1 ml-auto md:ml-0">
                      <Clock className="w-3 h-3" />
                      {new Date(item.created_at).toLocaleString()}
                    </span>
                  </div>

                  <div>
                    <h4 className="text-sm font-bold text-slate-100 group-hover:text-indigo-300 transition-colors flex items-center gap-2">
                      {item.title}
                      <ExternalLink className="w-3.5 h-3.5 text-slate-500 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </h4>
                    <p className="text-xs text-slate-400 mt-1 line-clamp-2 leading-relaxed">
                      {item.summary}
                    </p>
                  </div>

                  {/* Risk Flags & Confidence */}
                  <div className="flex flex-wrap items-center gap-3 pt-1">
                    {/* Confidence Meter */}
                    {item.confidence_score !== undefined && (
                      <div className="flex items-center gap-2 bg-slate-900 px-2.5 py-1 rounded-lg border border-slate-800 text-xs">
                        <span className="text-[10px] text-slate-400 font-medium">Confidence:</span>
                        <div className="w-16 bg-slate-800 h-1.5 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              confPercent >= 85
                                ? 'bg-emerald-400'
                                : confPercent >= 70
                                  ? 'bg-amber-400'
                                  : 'bg-rose-400'
                            }`}
                            style={{ width: `${confPercent}%` }}
                          />
                        </div>
                        <span className="font-bold text-slate-200 text-[11px]">{confPercent}%</span>
                      </div>
                    )}

                    {/* Risk Flags */}
                    {item.risk_flags && item.risk_flags.length > 0 && (
                      <div className="flex flex-wrap items-center gap-1.5">
                        {item.risk_flags.map((flag) => (
                          <span
                            key={flag}
                            className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/10 text-amber-300 border border-amber-500/20 flex items-center gap-1"
                          >
                            <ShieldAlert className="w-3 h-3 text-amber-400" />
                            {flag.replace('_', ' ')}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {/* Right: Status / Action Buttons */}
                <div className="flex items-center gap-2 justify-end border-t md:border-t-0 pt-3 md:pt-0 border-slate-800">
                  {isPending ? (
                    <>
                      <button
                        type="button"
                        onClick={(e) => handleQuickApprove(e, item.id)}
                        disabled={isActioning}
                        className="px-3.5 py-1.5 rounded-xl bg-emerald-600/20 hover:bg-emerald-600/40 border border-emerald-500/30 text-emerald-300 font-semibold text-xs transition-all flex items-center gap-1.5 disabled:opacity-50"
                        title="Quick Approve as-is"
                      >
                        {isActioning ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Check className="w-3.5 h-3.5" />
                        )}
                        Approve
                      </button>

                      <button
                        type="button"
                        onClick={(e) => handleQuickReject(e, item.id)}
                        disabled={isActioning}
                        className="px-3.5 py-1.5 rounded-xl bg-rose-600/10 hover:bg-rose-600/20 border border-rose-500/20 text-rose-300 font-semibold text-xs transition-all flex items-center gap-1.5 disabled:opacity-50"
                        title="Reject item"
                      >
                        <X className="w-3.5 h-3.5" />
                        Reject
                      </button>

                      <button
                        type="button"
                        onClick={() => onInspectItem(item)}
                        className="px-3.5 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs transition-all shadow-md shadow-indigo-600/20 flex items-center gap-1"
                      >
                        Inspect & Edit
                        <ArrowRight className="w-3.5 h-3.5" />
                      </button>
                    </>
                  ) : (
                    <span className="px-3 py-1 rounded-full text-xs font-bold capitalize bg-slate-900 border border-slate-800 text-slate-400">
                      Status: {item.status}
                    </span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
