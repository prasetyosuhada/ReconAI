import React, { useState } from 'react'
import {
  ArrowLeftRight,
  ChevronDown,
  ChevronUp,
  Clock,
  Code2,
  History,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  UserCheck,
} from 'lucide-react'
import type { AuditEventResponse } from '../../services/api'

interface AuditTimelineProps {
  events: AuditEventResponse[]
}

export const AuditTimeline: React.FC<AuditTimelineProps> = ({ events }) => {
  const [expandedSnapshots, setExpandedSnapshots] = useState<Record<string, boolean>>({})

  const toggleSnapshot = (id: string) => {
    setExpandedSnapshots((prev) => ({
      ...prev,
      [id]: !prev[id],
    }))
  }

  const getEventIcon = (eventType: string, actorType: string) => {
    if (eventType.includes('upload')) {
      return <UploadCloud className="w-4 h-4 text-indigo-400" />
    }
    if (eventType.includes('extraction') || eventType.includes('bookkeeping')) {
      return <Sparkles className="w-4 h-4 text-purple-400" />
    }
    if (eventType.includes('review') || actorType === 'human') {
      return <UserCheck className="w-4 h-4 text-amber-400" />
    }
    if (eventType.includes('post') || eventType.includes('ledger')) {
      return <ShieldCheck className="w-4 h-4 text-emerald-400" />
    }
    if (eventType.includes('reconcil')) {
      return <ArrowLeftRight className="w-4 h-4 text-teal-400" />
    }
    return <History className="w-4 h-4 text-slate-400" />
  }

  const getActorBadge = (actorType: string, actorName: string) => {
    switch (actorType.toLowerCase()) {
      case 'agent':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-purple-500/10 text-purple-300 border border-purple-500/20 flex items-center gap-1">
            <Sparkles className="w-3 h-3 text-purple-400" />
            AI Agent: {actorName}
          </span>
        )
      case 'human':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/10 text-amber-300 border border-amber-500/20 flex items-center gap-1">
            <UserCheck className="w-3 h-3 text-amber-400" />
            Human: {actorName}
          </span>
        )
      default:
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-800 text-slate-400 border border-slate-700">
            System: {actorName}
          </span>
        )
    }
  }

  return (
    <div className="relative pl-6 border-l-2 border-slate-800 space-y-6 ml-3 my-4">
      {events.map((evt) => {
        const isExpanded = !!expandedSnapshots[evt.id]
        const hasSnapshots =
          (evt.input_snapshot && Object.keys(evt.input_snapshot).length > 0) ||
          (evt.output_snapshot && Object.keys(evt.output_snapshot).length > 0)

        const confPercent =
          evt.confidence_score !== undefined ? Math.round((evt.confidence_score || 0) * 100) : null

        return (
          <div key={evt.id} className="relative group">
            {/* Timeline Dot Icon */}
            <div className="absolute -left-[35px] top-1 p-2 rounded-full bg-slate-900 border border-slate-700 group-hover:border-indigo-500 transition-colors shadow-lg">
              {getEventIcon(evt.event_type, evt.actor_type)}
            </div>

            {/* Event Content Card */}
            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80 hover:border-slate-700 transition-all space-y-3 shadow-md">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-bold text-slate-100 uppercase tracking-wider font-mono">
                    {evt.event_type.replace(/_/g, ' ')}
                  </span>
                  {getActorBadge(evt.actor_type, evt.actor_name)}
                </div>

                <span className="text-[11px] font-mono text-slate-400 flex items-center gap-1">
                  <Clock className="w-3 h-3 text-slate-500" />
                  {new Date(evt.created_at).toLocaleString()}
                </span>
              </div>

              {/* Rationale / Summary Output Snapshot */}
              {evt.output_snapshot?.rationale && (
                <div className="text-xs text-slate-300 bg-slate-950/80 p-3 rounded-lg border border-slate-800/80 leading-relaxed italic">
                  "{evt.output_snapshot.rationale}"
                </div>
              )}

              {/* Confidence Score Bar if available */}
              {confPercent !== null && (
                <div className="flex items-center gap-2 text-xs">
                  <span className="text-[11px] text-slate-400 font-medium">Extraction Score:</span>
                  <div className="w-24 bg-slate-800 h-1.5 rounded-full overflow-hidden">
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
                  <span className="font-bold text-slate-200 text-[11px] font-mono">
                    {confPercent}%
                  </span>
                </div>
              )}

              {/* Snapshot Toggle */}
              {hasSnapshots && (
                <div>
                  <button
                    type="button"
                    onClick={() => toggleSnapshot(evt.id)}
                    className="text-[11px] font-medium text-indigo-400 hover:text-indigo-300 flex items-center gap-1 transition-colors"
                  >
                    <Code2 className="w-3 h-3" />
                    {isExpanded ? 'Hide Data Snapshot' : 'View Payload Snapshot'}
                    {isExpanded ? (
                      <ChevronUp className="w-3 h-3" />
                    ) : (
                      <ChevronDown className="w-3 h-3" />
                    )}
                  </button>

                  {isExpanded && (
                    <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                      {evt.input_snapshot && (
                        <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 space-y-1">
                          <span className="text-[10px] font-bold text-slate-400 uppercase font-mono">
                            Input Snapshot
                          </span>
                          <pre className="text-[10px] text-emerald-300 font-mono overflow-x-auto p-1 max-h-40">
                            {JSON.stringify(evt.input_snapshot, null, 2)}
                          </pre>
                        </div>
                      )}

                      {evt.output_snapshot && (
                        <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 space-y-1">
                          <span className="text-[10px] font-bold text-slate-400 uppercase font-mono">
                            Output Snapshot
                          </span>
                          <pre className="text-[10px] text-indigo-300 font-mono overflow-x-auto p-1 max-h-40">
                            {JSON.stringify(evt.output_snapshot, null, 2)}
                          </pre>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
