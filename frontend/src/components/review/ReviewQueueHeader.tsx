import React from 'react'
import { AlertTriangle, CheckCircle2, ShieldCheck, UserCheck } from 'lucide-react'

interface ReviewQueueHeaderProps {
  pendingCount: number
  highPriorityCount: number
  approvedCount: number
}

export const ReviewQueueHeader: React.FC<ReviewQueueHeaderProps> = ({
  pendingCount,
  highPriorityCount,
  approvedCount,
}) => {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {/* Pending Reviews */}
      <div className="p-5 rounded-2xl bg-slate-800/40 border border-slate-700/50 shadow-xl backdrop-blur-sm space-y-2 relative overflow-hidden">
        <div className="flex items-center justify-between text-slate-400">
          <span className="text-xs font-medium">Pending Review Items</span>
          <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <UserCheck className="w-4 h-4" />
          </div>
        </div>
        <div className="text-3xl font-extrabold text-white">{pendingCount}</div>
        <p className="text-[11px] text-amber-400/90 font-medium flex items-center gap-1">
          Awaiting human verification
        </p>
      </div>

      {/* High Priority */}
      <div className="p-5 rounded-2xl bg-slate-800/40 border border-slate-700/50 shadow-xl backdrop-blur-sm space-y-2 relative overflow-hidden">
        <div className="flex items-center justify-between text-slate-400">
          <span className="text-xs font-medium">High Priority Flags</span>
          <div className="p-2 rounded-lg bg-rose-500/10 text-rose-400 border border-rose-500/20">
            <AlertTriangle className="w-4 h-4" />
          </div>
        </div>
        <div className="text-3xl font-extrabold text-rose-400">{highPriorityCount}</div>
        <p className="text-[11px] text-rose-300/80 font-medium">Sensitive accounts / low score</p>
      </div>

      {/* Approved / Resolved */}
      <div className="p-5 rounded-2xl bg-slate-800/40 border border-slate-700/50 shadow-xl backdrop-blur-sm space-y-2 relative overflow-hidden">
        <div className="flex items-center justify-between text-slate-400">
          <span className="text-xs font-medium">Resolved Today</span>
          <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 className="w-4 h-4" />
          </div>
        </div>
        <div className="text-3xl font-extrabold text-emerald-400">{approvedCount}</div>
        <p className="text-[11px] text-emerald-300/80 font-medium">Posted to General Ledger</p>
      </div>

      {/* Guardrail Guarantee */}
      <div className="p-5 rounded-2xl bg-gradient-to-br from-indigo-950/60 via-slate-900 to-slate-900 border border-indigo-500/30 shadow-xl backdrop-blur-sm space-y-2">
        <div className="flex items-center justify-between text-indigo-300">
          <span className="text-xs font-medium">Safety Policy</span>
          <ShieldCheck className="w-4 h-4 text-indigo-400" />
        </div>
        <div className="text-xs font-semibold text-slate-200">LLM Core + Guardrails</div>
        <p className="text-[11px] text-slate-400 leading-tight">
          Uncertain journal entries require explicit human approval before posting.
        </p>
      </div>
    </div>
  )
}
