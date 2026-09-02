import React, { useEffect, useState } from 'react'
import { Activity, Bot, Clock, History, Loader2, RefreshCw, User, X } from 'lucide-react'
import type { AuditEventResponse, BankStatementImportResponse } from '../../services/api'
import { fetchAuditEvents } from '../../services/api'

interface ReconciliationAuditTimelineProps {
  activeImport?: BankStatementImportResponse
  isOpen: boolean
  onClose: () => void
}

export const ReconciliationAuditTimeline: React.FC<ReconciliationAuditTimelineProps> = ({
  activeImport,
  isOpen,
  onClose,
}) => {
  const [auditEvents, setAuditEvents] = useState<AuditEventResponse[]>([])
  const [loading, setLoading] = useState<boolean>(false)

  const loadAuditEvents = async () => {
    setLoading(true)
    try {
      const res = await fetchAuditEvents({ limit: 50 })
      setAuditEvents(res.items)
    } catch (err) {
      console.error('Failed to load audit events:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (isOpen) {
      loadAuditEvents()
    }
  }, [isOpen, activeImport?.id])

  if (!isOpen) return null

  const formatEventTime = (isoString: string) => {
    try {
      const d = new Date(isoString)
      return d.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      })
    } catch {
      return isoString
    }
  }

  const formatEventDate = (isoString: string) => {
    try {
      const d = new Date(isoString)
      return d.toLocaleDateString('en-US', {
        month: 'short',
        day: '2-digit',
        year: 'numeric',
      })
    } catch {
      return isoString
    }
  }

  const getActorBadge = (actorType: string, actorName: string) => {
    switch (actorType.toLowerCase()) {
      case 'agent':
        return (
          <span className="px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30 text-[10px] font-bold font-mono flex items-center gap-1">
            <Bot className="w-3 h-3" /> {actorName || 'AI Agent'}
          </span>
        )
      case 'human':
        return (
          <span className="px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 text-[10px] font-bold font-mono flex items-center gap-1">
            <User className="w-3 h-3" /> {actorName || 'Reviewer'}
          </span>
        )
      default:
        return (
          <span className="px-2 py-0.5 rounded-full bg-slate-700 text-slate-300 border border-slate-600 text-[10px] font-bold font-mono flex items-center gap-1">
            <Activity className="w-3 h-3 text-emerald-400" /> {actorName || 'System'}
          </span>
        )
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 w-full max-w-2xl rounded-2xl p-6 shadow-2xl space-y-4 max-h-[85vh] flex flex-col">
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
              <History className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">
                Reconciliation Activity &amp; Audit Trail
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Audit-ready timeline of actions taken on statement{' '}
                <span className="font-mono text-emerald-400">
                  {activeImport?.original_filename || 'Active Batch'}
                </span>
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={loadAuditEvents}
              disabled={loading}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer"
              title="Refresh timeline"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Timeline Events Content */}
        <div className="flex-1 overflow-y-auto pr-2 space-y-4">
          {loading && auditEvents.length === 0 ? (
            <div className="py-12 text-center text-slate-400 space-y-2">
              <Loader2 className="w-6 h-6 animate-spin text-emerald-400 mx-auto" />
              <p className="text-xs">Loading audit log events...</p>
            </div>
          ) : auditEvents.length === 0 ? (
            <div className="py-12 text-center text-slate-400 space-y-2 bg-slate-950/40 rounded-xl border border-slate-800">
              <History className="w-8 h-8 text-slate-600 mx-auto" />
              <p className="text-xs font-semibold text-slate-300">No Audit Events Logged</p>
              <p className="text-[11px] text-slate-500">
                Actions such as CSV import, matching, and match reviews will appear here.
              </p>
            </div>
          ) : (
            <div className="relative pl-6 space-y-6 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-800">
              {auditEvents.map((evt, idx) => (
                <div key={evt.id || idx} className="relative group">
                  {/* Timeline dot */}
                  <div className="absolute -left-6 top-1.5 w-3 h-3 rounded-full bg-slate-900 border-2 border-emerald-500 ring-4 ring-slate-900 group-hover:scale-125 transition-transform" />

                  <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800 group-hover:border-slate-700 transition-colors space-y-2">
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-white uppercase tracking-wider">
                          {evt.event_type.replace(/_/g, ' ')}
                        </span>
                        {getActorBadge(evt.actor_type, evt.actor_name)}
                      </div>
                      <span className="text-[11px] font-mono text-slate-400 flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {formatEventDate(evt.created_at)} {formatEventTime(evt.created_at)}
                      </span>
                    </div>

                    {/* Snapshot / metadata */}
                    {evt.input_snapshot?.resolution_note && (
                      <p className="text-xs text-slate-300 italic bg-slate-900/80 p-2 rounded border border-slate-800">
                        Note: "{evt.input_snapshot.resolution_note}"
                      </p>
                    )}
                    {evt.output_snapshot && (
                      <p className="text-[11px] font-mono text-slate-400">
                        Result: {JSON.stringify(evt.output_snapshot)}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-between border-t border-slate-800 pt-3 text-xs text-slate-400">
          <span>Deterministic Audit Trail (Immutable Log)</span>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-semibold transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
