import React from 'react'
import {
  ArrowLeftRight,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  History,
  LayoutDashboard,
  Sparkles,
  UploadCloud,
  UserCheck,
} from 'lucide-react'

export type NavTab = 'dashboard' | 'documents' | 'review' | 'ledger' | 'reconciliation' | 'audit'

interface SidebarProps {
  activeTab: NavTab
  onSelectTab: (tab: NavTab) => void
  collapsed: boolean
  onToggleCollapse: () => void
  pendingReviewCount?: number
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onSelectTab,
  collapsed,
  onToggleCollapse,
  pendingReviewCount = 3,
}) => {
  const navItems = [
    {
      id: 'dashboard' as NavTab,
      label: 'Dashboard',
      icon: LayoutDashboard,
    },
    {
      id: 'documents' as NavTab,
      label: 'Document Intake',
      icon: UploadCloud,
    },
    {
      id: 'review' as NavTab,
      label: 'Review Queue',
      icon: UserCheck,
      badge: pendingReviewCount > 0 ? pendingReviewCount : undefined,
      badgeColor: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
    },
    {
      id: 'ledger' as NavTab,
      label: 'General Ledger',
      icon: BookOpen,
    },
    {
      id: 'reconciliation' as NavTab,
      label: 'Bank Reconciliation',
      icon: ArrowLeftRight,
    },
    {
      id: 'audit' as NavTab,
      label: 'Audit Traceability',
      icon: History,
    },
  ]

  return (
    <aside
      className={`relative z-40 bg-slate-950/90 border-r border-slate-800/80 flex flex-col justify-between transition-all duration-300 ${
        collapsed ? 'w-20' : 'w-64'
      }`}
    >
      {/* Brand Header */}
      <div>
        <div className="h-16 px-4 flex items-center justify-between border-b border-slate-800/80">
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-violet-500 flex items-center justify-center text-white shadow-lg shadow-indigo-500/30 shrink-0">
              <Sparkles className="w-5 h-5 text-indigo-100" />
            </div>
            {!collapsed && (
              <div className="flex flex-col">
                <span className="text-lg font-extrabold tracking-tight bg-gradient-to-r from-white via-slate-100 to-indigo-200 bg-clip-text text-transparent">
                  ReconAI
                </span>
                <span className="text-[10px] text-indigo-400 font-medium uppercase tracking-wider">
                  Accounting Platform
                </span>
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={onToggleCollapse}
            className="p-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-white hover:bg-slate-800 transition-all"
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          </button>
        </div>

        {/* Navigation List */}
        <nav className="p-3 space-y-1.5">
          {navItems.map((item) => {
            const Icon = item.icon
            const isActive = activeTab === item.id

            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onSelectTab(item.id)}
                className={`w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl font-medium text-sm transition-all duration-150 ${
                  isActive
                    ? 'bg-gradient-to-r from-indigo-600 to-indigo-700 text-white shadow-md shadow-indigo-600/30 font-semibold'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
                }`}
                title={collapsed ? item.label : undefined}
              >
                <Icon
                  className={`w-5 h-5 shrink-0 ${isActive ? 'text-white' : 'text-slate-400'}`}
                />
                {!collapsed && <span className="truncate flex-1 text-left">{item.label}</span>}
                {!collapsed && item.badge !== undefined && (
                  <span
                    className={`px-2 py-0.5 rounded-full text-[11px] font-bold border ${item.badgeColor}`}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            )
          })}
        </nav>
      </div>

      {/* Footer Info */}
      <div className="p-4 border-t border-slate-800/80">
        {!collapsed ? (
          <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800/80 text-xs text-slate-400 space-y-1">
            <div className="font-semibold text-slate-300 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
              LangGraph Multi-Agent
            </div>
            <p className="text-[11px] text-slate-500 leading-tight">
              Deterministic double-entry guardrails active.
            </p>
          </div>
        ) : (
          <div className="flex justify-center">
            <span
              className="w-3 h-3 rounded-full bg-emerald-400 animate-ping"
              title="System Active"
            />
          </div>
        )}
      </div>
    </aside>
  )
}
