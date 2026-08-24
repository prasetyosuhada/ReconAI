import React, { useState } from 'react'
import {
  AlertTriangle,
  ArrowLeftRight,
  Clock,
  Code2,
  ExternalLink,
  History,
  Layers,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  UserCheck,
} from 'lucide-react'
import type { AuditEventResponse } from '../../services/api'
import { AuditEventInspectorModal } from './AuditEventInspectorModal'

interface AuditTimelineProps {
  events: AuditEventResponse[]
  highlightedEventId?: string | null
  onSelectJournalEntry?: (journalEntryId: string) => void
  onSelectBankTransaction?: (bankTransactionId: string) => void
}

export const AuditTimeline: React.FC<AuditTimelineProps> = ({
  events,
  highlightedEventId,
  onSelectJournalEntry,
  onSelectBankTransaction,
}) => {
  const [selectedEvent, setSelectedEvent] = useState<AuditEventResponse | null>(null)
  const [inspectorTab, setInspectorTab] = useState<'formatted' | 'raw'>('formatted')

  const openInspector = (evt: AuditEventResponse, tab: 'formatted' | 'raw') => {
    setSelectedEvent(evt)
    setInspectorTab(tab)
  }

  const closeInspector = () => {
    setSelectedEvent(null)
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

  const renderTwoLineActorBadge = (actorType: string, actorName: string) => {
    switch (actorType?.toLowerCase()) {
      case 'agent':
        return (
          <div className="px-2.5 py-1 rounded-lg bg-purple-500/10 border border-purple-500/25 text-purple-300 flex items-center gap-1.5 shrink-0">
            <Sparkles className="w-3.5 h-3.5 text-purple-400 shrink-0" />
            <div className="text-left leading-none">
              <span className="text-[9px] font-bold tracking-wider text-purple-400 uppercase block">
                AI AGENT
              </span>
              <span className="text-[11px] font-semibold text-slate-200 block mt-0.5 max-w-[130px] sm:max-w-[180px] truncate">
                {actorName || 'BookkeepingAgent'}
              </span>
            </div>
          </div>
        )
      case 'human':
        return (
          <div className="px-2.5 py-1 rounded-lg bg-amber-500/10 border border-amber-500/25 text-amber-300 flex items-center gap-1.5 shrink-0">
            <UserCheck className="w-3.5 h-3.5 text-amber-400 shrink-0" />
            <div className="text-left leading-none">
              <span className="text-[9px] font-bold tracking-wider text-amber-400 uppercase block">
                HUMAN
              </span>
              <span className="text-[11px] font-semibold text-slate-200 block mt-0.5 max-w-[130px] sm:max-w-[180px] truncate">
                {actorName || 'human_user'}
              </span>
            </div>
          </div>
        )
      default:
        return (
          <div className="px-2.5 py-1 rounded-lg bg-slate-800/80 border border-slate-700 text-slate-300 flex items-center gap-1.5 shrink-0">
            <Layers className="w-3.5 h-3.5 text-slate-400 shrink-0" />
            <div className="text-left leading-none">
              <span className="text-[9px] font-bold tracking-wider text-slate-400 uppercase block">
                SYSTEM
              </span>
              <span className="text-[11px] font-semibold text-slate-200 block mt-0.5 max-w-[130px] sm:max-w-[180px] truncate">
                {actorName || 'System'}
              </span>
            </div>
          </div>
        )
    }
  }

  return (
    <div className="relative pl-6 border-l-2 border-slate-800 space-y-6 ml-3 my-4">
      {events.map((evt) => {
        const outSnap = evt.output_snapshot || {}
        const decision = typeof outSnap.decision === 'string' ? outSnap.decision : null
        const reasoningList: string[] = Array.isArray(outSnap.reasoning)
          ? outSnap.reasoning.map(String)
          : []

        const lowConfidenceFields: string[] = Array.isArray(outSnap.low_confidence_fields)
          ? outSnap.low_confidence_fields.map(String)
          : []

        const confPercent =
          evt.confidence_score !== undefined && evt.confidence_score !== null
            ? Math.round(Number(evt.confidence_score) * 100)
            : null

        const isHighlighted = highlightedEventId === evt.id

        return (
          <div key={evt.id} id={`audit-event-${evt.id}`} className="relative group scroll-mt-24">
            {/* Timeline Dot Icon */}
            <div
              className={`absolute -left-[35px] top-1.5 p-2 rounded-full bg-slate-900 border transition-all shadow-lg ${
                isHighlighted
                  ? 'border-indigo-400 bg-indigo-950/80 scale-110 shadow-indigo-500/30'
                  : 'border-slate-700 group-hover:border-indigo-500'
              }`}
            >
              {getEventIcon(evt.event_type, evt.actor_type)}
            </div>

            {/* Event Content Card */}
            <div
              className={`p-4 sm:p-5 rounded-2xl border transition-all space-y-3.5 shadow-md backdrop-blur-sm ${
                isHighlighted
                  ? 'bg-indigo-950/40 border-indigo-500/70 ring-2 ring-indigo-500/50 shadow-indigo-500/15'
                  : 'bg-slate-900/70 border-slate-800/90 hover:border-slate-700/80'
              }`}
            >
              {/* Header row: Event Title + Two-Line Actor Badge + Timestamp */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2.5">
                  <span className="text-xs font-bold text-slate-100 uppercase tracking-wider font-mono">
                    {evt.event_type.replace(/_/g, ' ')}
                  </span>
                  {renderTwoLineActorBadge(evt.actor_type, evt.actor_name)}
                </div>

                <span className="text-[11px] font-mono text-slate-400 flex items-center gap-1 shrink-0">
                  <Clock className="w-3.5 h-3.5 text-slate-500" />
                  {new Date(evt.created_at).toLocaleString()}
                </span>
              </div>

              {/* Extraction completed: Low confidence fields warning badge */}
              {evt.event_type === 'extraction_completed' && lowConfidenceFields.length > 0 && (
                <div className="p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/25 text-amber-200 text-xs flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                  <span>
                    <strong className="font-semibold">Low confidence fields: </strong>
                    <span className="font-mono text-amber-300">
                      {lowConfidenceFields.join(', ')}
                    </span>
                  </span>
                </div>
              )}

              {/* Conditional Rendering: Structured Decision Card vs Simple Card */}
              {decision ? (
                /* Rich Structured AI Decision Block */
                <div className="space-y-3 pt-1">
                  {/* Decision Headline */}
                  <div
                    className={`p-3 rounded-xl border flex items-center gap-2.5 text-xs sm:text-sm font-bold ${
                      decision === 'failed'
                        ? 'bg-rose-500/10 border-rose-500/30 text-rose-200'
                        : 'bg-indigo-950/30 border-indigo-500/25 text-slate-100'
                    }`}
                  >
                    <Sparkles
                      className={`w-4 h-4 shrink-0 ${
                        decision === 'failed' ? 'text-rose-400' : 'text-indigo-400'
                      }`}
                    />
                    <span className="truncate">{decision}</span>
                  </div>

                  {/* Confidence Bar if available */}
                  {confPercent !== null && (
                    <div className="flex items-center gap-2 text-xs">
                      <span className="text-[11px] text-slate-400 font-medium">Confidence:</span>
                      <div className="w-24 bg-slate-800 h-1.5 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${
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

                  {/* Reasoning Bullet List */}
                  {reasoningList.length > 0 && (
                    <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80 space-y-1.5">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                        Reasoning & Decision Drivers:
                      </span>
                      <ul className="space-y-1 text-xs text-slate-300 pl-4 list-disc marker:text-indigo-400 leading-relaxed">
                        {reasoningList.map((reason, idx) => (
                          <li key={idx}>{reason}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ) : (
                /* Simpler Layout for Events without Decision */
                <div className="space-y-2.5">
                  {/* Rationale Quote if present */}
                  {evt.output_snapshot?.rationale && (
                    <div className="text-xs text-slate-300 bg-slate-950/70 p-3 rounded-xl border border-slate-800/80 leading-relaxed italic">
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
                </div>
              )}

              {/* Actions Row */}
              <div className="pt-2 border-t border-slate-800/60 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={() => openInspector(evt, 'formatted')}
                  className="text-xs font-semibold text-indigo-400 hover:text-indigo-300 flex items-center gap-1.5 transition-colors cursor-pointer"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  View Details
                </button>

                <span className="text-slate-700">•</span>

                <button
                  type="button"
                  onClick={() => openInspector(evt, 'raw')}
                  className="text-xs font-semibold text-slate-400 hover:text-slate-200 flex items-center gap-1.5 transition-colors cursor-pointer"
                >
                  <Code2 className="w-3.5 h-3.5" />
                  View Raw Payload
                </button>

                {/* Inline Jump Link: View in GL */}
                {(() => {
                  if (!onSelectJournalEntry) return null
                  const isJeEvent =
                    evt.event_type === 'journal_entry_posted' ||
                    evt.event_type === 'journal_entry_suggested'
                  if (!isJeEvent) return null

                  const snapInput =
                    typeof evt.input_snapshot === 'object' && !Array.isArray(evt.input_snapshot)
                      ? evt.input_snapshot
                      : null
                  const targetJeId =
                    outSnap.journal_entry_id ||
                    (evt.source_type === 'journal_entry' ? evt.source_id : null) ||
                    snapInput?.journal_entry_id

                  if (!targetJeId) return null

                  return (
                    <>
                      <span className="text-slate-700">•</span>
                      <button
                        type="button"
                        onClick={() => onSelectJournalEntry(String(targetJeId))}
                        className="text-xs font-semibold text-emerald-400 hover:text-emerald-300 flex items-center gap-1 transition-colors cursor-pointer"
                        title="Trace by this Journal Entry"
                      >
                        <ShieldCheck className="w-3.5 h-3.5" />
                        View in GL →
                      </button>
                    </>
                  )
                })()}

                {/* Inline Jump Link: View Match */}
                {(() => {
                  if (!onSelectBankTransaction) return null
                  const isMatchEvent = evt.event_type.startsWith('reconciliation_match_')
                  if (!isMatchEvent) return null

                  const snapInput =
                    typeof evt.input_snapshot === 'object' && !Array.isArray(evt.input_snapshot)
                      ? evt.input_snapshot
                      : null
                  const targetTxId =
                    outSnap.bank_transaction_id ||
                    (evt.source_type === 'bank_transaction' ? evt.source_id : null) ||
                    snapInput?.bank_transaction_id ||
                    snapInput?.tx_id

                  if (!targetTxId) return null

                  return (
                    <>
                      <span className="text-slate-700">•</span>
                      <button
                        type="button"
                        onClick={() => onSelectBankTransaction(String(targetTxId))}
                        className="text-xs font-semibold text-teal-400 hover:text-teal-300 flex items-center gap-1 transition-colors cursor-pointer"
                        title="Trace by this Bank Transaction"
                      >
                        <ArrowLeftRight className="w-3.5 h-3.5" />
                        View Match →
                      </button>
                    </>
                  )
                })()}
              </div>
            </div>
          </div>
        )
      })}

      {/* Tabbed Inspector Modal */}
      {selectedEvent && (
        <AuditEventInspectorModal
          event={selectedEvent}
          initialTab={inspectorTab}
          onClose={closeInspector}
        />
      )}
    </div>
  )
}
