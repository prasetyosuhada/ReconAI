import React from 'react'
import { Sparkles } from 'lucide-react'

interface NavbarProps {
  activeTabTitle?: string
  pendingReviewCount?: number
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTabTitle = 'Dashboard',
}) => {
  return (
    <header className="sticky top-0 z-30 h-16 bg-slate-900/80 backdrop-blur-md border-b border-slate-800/80 px-6 flex items-center justify-between">
      {/* Left spacer — mirrors profile avatar width so title is truly centered */}
      <div className="w-10" />

      {/* Center: Page Title */}
      <h1 className="text-xl font-bold bg-gradient-to-r from-white via-slate-200 to-indigo-300 bg-clip-text text-transparent tracking-tight">
        {activeTabTitle}
      </h1>

      {/* Right: Profile Avatar */}
      <div className="flex items-center gap-3">
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
    </header>
  )
}
