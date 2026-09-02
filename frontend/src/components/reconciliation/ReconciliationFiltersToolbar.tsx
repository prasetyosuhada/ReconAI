import React from 'react'
import {
  AlertCircle,
  Building2,
  CheckCircle2,
  Clock,
  Filter,
  Layers,
  Search,
  X,
} from 'lucide-react'

export type ReconFilterType =
  'all' | 'matched' | 'needs_review' | 'bank_only' | 'gl_only' | 'reconciled'

interface ReconciliationFiltersToolbarProps {
  activeFilter: ReconFilterType
  onSelectFilter: (filter: ReconFilterType) => void
  searchQuery: string
  onSearchChange: (query: string) => void
  counts: {
    all: number
    matched: number
    needs_review: number
    bank_only: number
    gl_only: number
    reconciled: number
  }
}

export const ReconciliationFiltersToolbar: React.FC<ReconciliationFiltersToolbarProps> = ({
  activeFilter,
  onSelectFilter,
  searchQuery,
  onSearchChange,
  counts,
}) => {
  const filterTabs: Array<{
    id: ReconFilterType
    label: string
    count: number
    icon: React.ComponentType<{ className?: string }>
    badgeActive: string
    badgeInactive: string
  }> = [
    {
      id: 'all',
      label: 'All',
      count: counts.all,
      icon: Layers,
      badgeActive: 'bg-emerald-500 text-slate-950',
      badgeInactive: 'bg-slate-800 text-slate-400',
    },
    {
      id: 'matched',
      label: 'Matched',
      count: counts.matched,
      icon: CheckCircle2,
      badgeActive: 'bg-emerald-400 text-slate-950',
      badgeInactive: 'bg-emerald-950/60 text-emerald-400 border border-emerald-500/20',
    },
    {
      id: 'needs_review',
      label: 'Needs Review',
      count: counts.needs_review,
      icon: Clock,
      badgeActive: 'bg-amber-400 text-slate-950',
      badgeInactive: 'bg-amber-950/60 text-amber-400 border border-amber-500/20',
    },
    {
      id: 'bank_only',
      label: 'Bank Only',
      count: counts.bank_only,
      icon: AlertCircle,
      badgeActive: 'bg-cyan-400 text-slate-950',
      badgeInactive: 'bg-cyan-950/60 text-cyan-400 border border-cyan-500/20',
    },
    {
      id: 'gl_only',
      label: 'GL Only',
      count: counts.gl_only,
      icon: Building2,
      badgeActive: 'bg-indigo-400 text-slate-950',
      badgeInactive: 'bg-indigo-950/60 text-indigo-400 border border-indigo-500/20',
    },
    {
      id: 'reconciled',
      label: 'Reconciled',
      count: counts.reconciled,
      icon: CheckCircle2,
      badgeActive: 'bg-teal-400 text-slate-950',
      badgeInactive: 'bg-teal-950/60 text-teal-400 border border-teal-500/20',
    },
  ]

  return (
    <div className="p-4 rounded-2xl bg-slate-900/90 border border-slate-800 shadow-lg backdrop-blur-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
      {/* Filter Tabs */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0 scrollbar-none">
        <div className="flex items-center gap-1 text-slate-400 text-xs font-semibold uppercase tracking-wider mr-2 shrink-0">
          <Filter className="w-3.5 h-3.5 text-emerald-400" />
          <span>Filter:</span>
        </div>

        {filterTabs.map((tab) => {
          const isActive = activeFilter === tab.id
          const Icon = tab.icon

          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => onSelectFilter(tab.id)}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all flex items-center gap-2 shrink-0 cursor-pointer ${
                isActive
                  ? 'bg-slate-800 text-white border border-slate-600/80 shadow-sm shadow-emerald-500/10'
                  : 'bg-slate-950/40 text-slate-400 border border-slate-800 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-emerald-400' : 'text-slate-500'}`} />
              <span>{tab.label}</span>
              <span
                className={`px-1.5 py-0.5 rounded-full text-[10px] font-bold ${
                  isActive ? tab.badgeActive : tab.badgeInactive
                }`}
              >
                {tab.count}
              </span>
            </button>
          )
        })}
      </div>

      {/* Search Input Bar */}
      <div className="relative min-w-[240px] md:max-w-xs w-full">
        <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search description, ref, amount..."
          className="w-full pl-9 pr-8 py-2 rounded-xl bg-slate-950/60 border border-slate-800 focus:border-emerald-500/60 text-slate-200 placeholder-slate-500 text-xs transition-colors focus:outline-none"
        />
        {searchQuery && (
          <button
            type="button"
            onClick={() => onSearchChange('')}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 cursor-pointer"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </div>
  )
}
