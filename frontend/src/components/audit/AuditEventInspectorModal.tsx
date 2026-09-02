import React, { useState, useEffect } from 'react'
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  Clock,
  Code2,
  Copy,
  FileText,
  HelpCircle,
  Layers,
  Sparkles,
  UserCheck,
  X,
} from 'lucide-react'
import type { AuditEventResponse } from '../../services/api'

interface AuditEventInspectorModalProps {
  event: AuditEventResponse | null
  initialTab?: 'formatted' | 'raw'
  onClose: () => void
}

export const AuditEventInspectorModal: React.FC<AuditEventInspectorModalProps> = ({
  event,
  initialTab = 'formatted',
  onClose,
}) => {
  const [activeTab, setActiveTab] = useState<'formatted' | 'raw'>(initialTab)
  const [copied, setCopied] = useState<boolean>(false)

  useEffect(() => {
    setActiveTab(initialTab)
  }, [initialTab, event])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  if (!event) return null

  const outSnap = event.output_snapshot || {}
  const inSnap = event.input_snapshot || {}

  const decision = typeof outSnap.decision === 'string' ? outSnap.decision : null
  const reasoningList: string[] = Array.isArray(outSnap.reasoning)
    ? outSnap.reasoning.map(String)
    : event.rationale
      ? [event.rationale]
      : []

  const lowConfidenceFields: string[] = Array.isArray(outSnap.low_confidence_fields)
    ? outSnap.low_confidence_fields.map(String)
    : []

  const confPercent =
    event.confidence_score !== undefined && event.confidence_score !== null
      ? Math.round(Number(event.confidence_score) * 100)
      : null

  const handleCopyJson = async () => {
    const payload = {
      event_id: event.id,
      event_type: event.event_type,
      actor_type: event.actor_type,
      actor_name: event.actor_name,
      source_type: event.source_type,
      source_id: event.source_id,
      confidence_score: event.confidence_score,
      created_at: event.created_at,
      input_snapshot: event.input_snapshot,
      output_snapshot: event.output_snapshot,
    }
    await navigator.clipboard.writeText(JSON.stringify(payload, null, 2))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const getActorBadgeStyle = (actorType: string) => {
    switch (actorType?.toLowerCase()) {
      case 'agent':
        return {
          wrapper: 'bg-purple-500/10 border-purple-500/30 text-purple-300',
          typeText: 'AI AGENT',
          typeColor: 'text-purple-400',
          icon: <Sparkles className="w-3.5 h-3.5 text-purple-400" />,
        }
      case 'human':
        return {
          wrapper: 'bg-amber-500/10 border-amber-500/30 text-amber-300',
          typeText: 'HUMAN',
          typeColor: 'text-amber-400',
          icon: <UserCheck className="w-3.5 h-3.5 text-amber-400" />,
        }
      default:
        return {
          wrapper: 'bg-slate-800 border-slate-700 text-slate-300',
          typeText: 'SYSTEM',
          typeColor: 'text-slate-400',
          icon: <Layers className="w-3.5 h-3.5 text-slate-400" />,
        }
    }
  }

  const actorBadge = getActorBadgeStyle(event.actor_type)

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/85 backdrop-blur-md flex items-start justify-center p-3 sm:p-4 overflow-y-auto">
      <div className="relative w-full max-w-4xl bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl shadow-black/60 overflow-hidden flex flex-col my-4 sm:my-8 animate-fade-in">
        {/* Header */}
        <div className="px-5 py-4 bg-slate-950 border-b border-slate-800 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              onClick={onClose}
              className="p-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-400 hover:text-white transition-all shrink-0"
              title="Close inspector"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div className="min-w-0">
              <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-wider block">
                Audit Event Inspector
              </span>
              <h2 className="text-base font-bold text-white font-mono truncate uppercase">
                {event.event_type.replace(/_/g, ' ')}
              </h2>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Actor Two-line Badge */}
            <div
              className={`px-3 py-1 rounded-xl border flex items-center gap-2 ${actorBadge.wrapper}`}
            >
              {actorBadge.icon}
              <div className="text-left">
                <span
                  className={`text-[9px] font-bold tracking-wider block ${actorBadge.typeColor}`}
                >
                  {actorBadge.typeText}
                </span>
                <span className="text-xs font-semibold block leading-tight">
                  {event.actor_name || 'Anonymous'}
                </span>
              </div>
            </div>

            <button
              type="button"
              onClick={onClose}
              className="p-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-400 hover:text-white transition-all"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Tab Controls Bar */}
        <div className="px-5 bg-slate-950/60 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setActiveTab('formatted')}
              className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition-all cursor-pointer ${
                activeTab === 'formatted'
                  ? 'border-indigo-500 text-white bg-slate-800/30'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <FileText className="w-3.5 h-3.5" />
              Formatted Overview
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('raw')}
              className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition-all cursor-pointer ${
                activeTab === 'raw'
                  ? 'border-indigo-500 text-white bg-slate-800/30'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <Code2 className="w-3.5 h-3.5" />
              Raw JSON Payload
            </button>
          </div>

          <div className="text-[11px] font-mono text-slate-400 flex items-center gap-1.5 py-1">
            <Clock className="w-3 h-3 text-slate-500" />
            {new Date(event.created_at).toLocaleString()}
          </div>
        </div>

        {/* Modal Body */}
        <div className="p-5 sm:p-6 overflow-y-auto max-h-[70vh] space-y-5">
          {activeTab === 'formatted' ? (
            <div className="space-y-5">
              {/* Decision Headline Banner */}
              {decision && (
                <div
                  className={`p-4 rounded-xl border ${
                    decision === 'failed'
                      ? 'bg-rose-500/10 border-rose-500/30 text-rose-200'
                      : 'bg-indigo-950/40 border-indigo-500/30 text-slate-100'
                  }`}
                >
                  <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-wider block mb-1">
                    AI Decision Summary
                  </span>
                  <div className="flex items-center gap-2 text-sm sm:text-base font-bold">
                    <Sparkles
                      className={`w-4 h-4 shrink-0 ${
                        decision === 'failed' ? 'text-rose-400' : 'text-indigo-400'
                      }`}
                    />
                    <span>{decision}</span>
                  </div>
                </div>
              )}

              {/* Low Confidence Warning */}
              {lowConfidenceFields.length > 0 && (
                <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/25 text-amber-200 text-xs flex items-center gap-2.5">
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                  <div>
                    <span className="font-bold">Low Confidence Extracted Fields: </span>
                    <span className="font-mono">{lowConfidenceFields.join(', ')}</span>
                  </div>
                </div>
              )}

              {/* Reasoning Bullets */}
              {reasoningList.length > 0 && (
                <div className="p-4 rounded-xl bg-slate-950/70 border border-slate-800 space-y-2">
                  <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                    <HelpCircle className="w-3.5 h-3.5 text-indigo-400" />
                    Reasoning & Decision Drivers
                  </h3>
                  <ul className="space-y-1.5 text-xs text-slate-300 pl-4 list-disc marker:text-indigo-400 leading-relaxed">
                    {reasoningList.map((reason, idx) => (
                      <li key={idx}>{reason}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Key Attributes Grid */}
              <div className="p-4 rounded-xl bg-slate-950/70 border border-slate-800 space-y-3">
                <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider">
                  Event Metadata & Properties
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 text-xs">
                  <div className="p-2.5 rounded-lg bg-slate-900/90 border border-slate-800">
                    <span className="text-[10px] text-slate-400 block font-semibold">
                      Event Type
                    </span>
                    <span className="font-mono text-slate-200">{event.event_type}</span>
                  </div>

                  <div className="p-2.5 rounded-lg bg-slate-900/90 border border-slate-800">
                    <span className="text-[10px] text-slate-400 block font-semibold">
                      Source Entity
                    </span>
                    <span className="font-mono text-slate-200">
                      {event.source_type} ({event.source_id.slice(0, 8)}...)
                    </span>
                  </div>

                  <div className="p-2.5 rounded-lg bg-slate-900/90 border border-slate-800">
                    <span className="text-[10px] text-slate-400 block font-semibold">
                      Confidence Score
                    </span>
                    <span
                      className={`font-bold font-mono ${
                        confPercent !== null && confPercent >= 85
                          ? 'text-emerald-400'
                          : confPercent !== null && confPercent >= 70
                            ? 'text-amber-400'
                            : 'text-rose-400'
                      }`}
                    >
                      {confPercent !== null ? `${confPercent}% (${event.confidence_score})` : 'N/A'}
                    </span>
                  </div>

                  {outSnap.status && (
                    <div className="p-2.5 rounded-lg bg-slate-900/90 border border-slate-800">
                      <span className="text-[10px] text-slate-400 block font-semibold">Status</span>
                      <span className="font-bold text-slate-200 uppercase">{outSnap.status}</span>
                    </div>
                  )}

                  {outSnap.journal_entry_id && (
                    <div className="p-2.5 rounded-lg bg-slate-900/90 border border-slate-800">
                      <span className="text-[10px] text-slate-400 block font-semibold">
                        Journal Entry ID
                      </span>
                      <span className="font-mono text-indigo-300">
                        #JE-{String(outSnap.journal_entry_id).slice(0, 8)}
                      </span>
                    </div>
                  )}

                  {outSnap.is_balanced !== undefined && (
                    <div className="p-2.5 rounded-lg bg-slate-900/90 border border-slate-800">
                      <span className="text-[10px] text-slate-400 block font-semibold">
                        Double-Entry Balance
                      </span>
                      <span
                        className={`font-bold uppercase ${
                          outSnap.is_balanced ? 'text-emerald-400' : 'text-rose-400'
                        }`}
                      >
                        {outSnap.is_balanced ? 'Balanced' : 'Unbalanced'}
                      </span>
                    </div>
                  )}

                  {outSnap.document_id && (
                    <div className="p-2.5 rounded-lg bg-slate-900/90 border border-slate-800">
                      <span className="text-[10px] text-slate-400 block font-semibold">
                        Document Reference
                      </span>
                      <span className="font-mono text-slate-300">
                        {String(outSnap.document_id).slice(0, 8)}...
                      </span>
                    </div>
                  )}
                </div>
              </div>

              {/* Input Context Highlights */}
              {inSnap && Object.keys(inSnap).length > 0 && (
                <div className="p-4 rounded-xl bg-slate-950/70 border border-slate-800 space-y-2">
                  <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider">
                    Input Snapshot Context
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                    {Object.entries(inSnap)
                      .filter(([k]) => typeof inSnap[k] !== 'object')
                      .map(([key, val]) => (
                        <div
                          key={key}
                          className="flex items-center justify-between p-2 rounded bg-slate-900/80 border border-slate-800/80"
                        >
                          <span className="text-slate-400 font-mono text-[11px]">{key}</span>
                          <span className="text-slate-200 font-mono text-[11px] font-semibold truncate max-w-[200px]">
                            {String(val)}
                          </span>
                        </div>
                      ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            /* Raw JSON Tab */
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-400">
                  Full raw payload snapshots serialized from database:
                </span>
                <button
                  type="button"
                  onClick={handleCopyJson}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold transition-all shadow-md cursor-pointer"
                >
                  {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                  {copied ? 'Copied Payload!' : 'Copy Full JSON'}
                </button>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Input Snapshot */}
                <div className="space-y-1.5">
                  <span className="text-[11px] font-bold text-emerald-400 uppercase font-mono tracking-wider block">
                    Input Snapshot
                  </span>
                  <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 overflow-x-auto max-h-96">
                    <pre className="text-xs font-mono text-emerald-300 leading-relaxed">
                      {JSON.stringify(inSnap, null, 2)}
                    </pre>
                  </div>
                </div>

                {/* Output Snapshot */}
                <div className="space-y-1.5">
                  <span className="text-[11px] font-bold text-indigo-400 uppercase font-mono tracking-wider block">
                    Output Snapshot
                  </span>
                  <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 overflow-x-auto max-h-96">
                    <pre className="text-xs font-mono text-indigo-300 leading-relaxed">
                      {JSON.stringify(outSnap, null, 2)}
                    </pre>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 bg-slate-950 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
          <span className="font-mono text-[11px]">Event ID: {event.id}</span>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold transition-all"
          >
            Close Inspector
          </button>
        </div>
      </div>
    </div>
  )
}
