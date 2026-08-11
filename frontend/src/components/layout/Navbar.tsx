import React from 'react'
import { Bell, Search, ShieldCheck, Sparkles } from 'lucide-react'

interface NavbarProps {
  activeTabTitle?: string
  pendingReviewCount?: number
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTabTitle = 'Dashboard',
  pendingReviewCount = 3,
}) => {
  return (
    <header className="sticky top-0 z-30 h-16 bg-slate-900/80 backdrop-blur-md border-b border-slate-800/80 px-6 flex items-center justify-between">
      {/* Left: Active Title & Status */}
      <div className="flex items-center gap-4">
        <h1 className="text-xl font-bold bg-gradient-to-r from-white via-slate-200 to-indigo-300 bg-clip-text text-transparent">
          {activeTabTitle}
        </h1>

        <div className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-medium">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span>Accounting Engine Ready</span>
        </div>
      </div>

      {/* Right: Search, Notifications, Profile */}
      <div className="flex items-center gap-4">
        {/* Quick Search */}
        <div className="relative hidden md:block w-64">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search documents, invoices..."
            className="w-full pl-9 pr-4 py-1.5 bg-slate-800/60 border border-slate-700/60 rounded-lg text-xs text-slate-200 placeholder-slate-400 focus:outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/50 transition-all"
          />
        </div>

        {/* Guardrail Badge */}
        <div className="hidden lg:flex items-center gap-1.5 px-3 py-1 bg-indigo-500/10 border border-indigo-500/20 rounded-lg text-indigo-300 text-xs font-medium">
          <ShieldCheck className="w-4 h-4 text-indigo-400" />
          <span>Deterministic Guardrails Active</span>
        </div>

        {/* Notifications */}
        <button
          type="button"
          className="relative p-2 rounded-lg bg-slate-800/60 hover:bg-slate-800 text-slate-300 hover:text-white border border-slate-700/50 transition-all"
          title="Review Queue Notifications"
        >
          <Bell className="w-4 h-4" />
          {pendingReviewCount > 0 && (
            <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-amber-500 text-slate-950 font-bold text-[10px] flex items-center justify-center animate-bounce">
              {pendingReviewCount}
            </span>
          )}
        </button>

        {/* Profile Avatar */}
        <div className="flex items-center gap-3 pl-2 border-l border-slate-800">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center text-white text-xs font-bold shadow-md shadow-indigo-500/20">
            AI
          </div>
          <div className="hidden xl:block text-left">
            <div className="text-xs font-semibold text-slate-200 flex items-center gap-1">
              ReconAI Agent
              <Sparkles className="w-3 h-3 text-indigo-400" />
            </div>
            <div className="text-[10px] text-slate-400">Bookkeeper Assistant</div>
          </div>
        </div>
      </div>
    </header>
  )
}
