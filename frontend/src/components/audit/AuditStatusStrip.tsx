import React from 'react'
import {
  ArrowRight,
  CheckCircle2,
  History,
} from 'lucide-react'
import type { AuditEventResponse } from '../../services/api'

export interface StatusTransitionNode {
  eventId: string
  rawStatus: string
  label: string
  timestamp: string
  actorName: string
  actorType: string
  eventType: string
}

export function formatStatusLabel(status: string): string {
  switch (status.toLowerCase()) {
    case 'uploaded':
      return 'Uploaded'
    case 'extracting':
      return 'Extracting'
    case 'extracted':
      return 'Extracted'
    case 'extraction_review_required':
      return 'Extraction Review Required'
    case 'bookkeeping_review_required':
      return 'Bookkeeping Review Required'
    case 'ready_to_post':
      return 'Ready to Post'
    case 'approved':
      return 'Approved'
    case 'posted':
      return 'Posted'
    case 'rejected':
      return 'Rejected'
    case 'failed':
      return 'Failed'
    default:
      return status
        .split('_')
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(' ')
  }
}

export function getStatusTone(status: string) {
  switch (status.toLowerCase()) {
    case 'posted':
    case 'approved':
      return {
        pill: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/35 hover:bg-emerald-500/25',
        dot: 'bg-emerald-400',
        badgeText: 'text-emerald-400',
      }
    case 'ready_to_post':
      return {
        pill: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/35 hover:bg-indigo-500/25',
        dot: 'bg-indigo-400',
        badgeText: 'text-indigo-400',
      }
    case 'extraction_review_required':
    case 'bookkeeping_review_required':
      return {
        pill: 'bg-amber-500/15 text-amber-300 border-amber-500/35 hover:bg-amber-500/25',
        dot: 'bg-amber-400',
        badgeText: 'text-amber-400',
      }
    case 'rejected':
    case 'failed':
      return {
        pill: 'bg-rose-500/15 text-rose-300 border-rose-500/35 hover:bg-rose-500/25',
        dot: 'bg-rose-400',
        badgeText: 'text-rose-400',
      }
    default:
      return {
        pill: 'bg-slate-800/90 text-slate-300 border-slate-700 hover:bg-slate-800',
        dot: 'bg-slate-400',
        badgeText: 'text-slate-400',
      }
  }
}

export function deriveStatusTransitions(events: AuditEventResponse[]): StatusTransitionNode[] {
  const sorted = [...events].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  )

  const transitions: StatusTransitionNode[] = []
  let lastStatus = ''

  for (const evt of sorted) {
    const isDocSource = evt.source_type === 'document'
    const isPosted = evt.event_type === 'journal_entry_posted'

    if (!isDocSource && !isPosted) continue

    const outSnap = evt.output_snapshot || {}
    let statusCandidate: string | null = null

    if (isPosted) {
      statusCandidate = 'posted'
    } else if (outSnap.next_workflow_status) {
      statusCandidate = String(outSnap.next_workflow_status)
    } else if (outSnap.status) {
      statusCandidate = String(outSnap.status)
    }

    if (!statusCandidate) continue

    const normalizedStatus = statusCandidate.toLowerCase().trim()

    // Deduplicate consecutive identical statuses
    if (normalizedStatus === lastStatus) continue

    lastStatus = normalizedStatus
    transitions.push({
      eventId: evt.id,
      rawStatus: normalizedStatus,
      label: formatStatusLabel(normalizedStatus),
      timestamp: evt.created_at,
      actorName: evt.actor_name || 'System',
      actorType: evt.actor_type || 'system',
      eventType: evt.event_type,
    })
  }

  return transitions
}

interface AuditStatusStripProps {
  events: AuditEventResponse[]
  onSelectEvent?: (eventId: string) => void
  activeEventId?: string | null
}

export const AuditStatusStrip: React.FC<AuditStatusStripProps> = ({
  events,
  onSelectEvent,
  activeEventId,
}) => {
  const transitions = deriveStatusTransitions(events)

  if (transitions.length === 0) return null

  return (
    <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-2.5 animate-fade-in shadow-inner">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-slate-400">
          <History className="w-3.5 h-3.5 text-indigo-400" />
          <span className="text-[11px] font-bold uppercase tracking-wider text-slate-300">
            Document Status Transition History
          </span>
        </div>
        <span className="text-[10px] text-slate-500 font-medium">
          Click any state to jump to its audit event
        </span>
      </div>

      {/* Horizontal Pills Strip */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 pt-0.5 scrollbar-thin scrollbar-thumb-slate-800">
        {transitions.map((node, index) => {
          const tone = getStatusTone(node.rawStatus)
          const isLatest = index === transitions.length - 1
          const isSelected = activeEventId === node.eventId

          return (
            <React.Fragment key={node.eventId}>
              <button
                type="button"
                onClick={() => onSelectEvent?.(node.eventId)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-xl border text-xs font-semibold transition-all shrink-0 cursor-pointer shadow-sm ${tone.pill} ${
                  isSelected
                    ? 'ring-2 ring-indigo-500 ring-offset-2 ring-offset-slate-950 scale-105'
                    : isLatest
                      ? 'border-emerald-500/50 shadow-emerald-500/10'
                      : ''
                }`}
                title={`Event: ${node.eventType} by ${node.actorName} at ${new Date(node.timestamp).toLocaleTimeString()}`}
              >
                <span className={`w-2 h-2 rounded-full ${tone.dot} ${isLatest ? 'animate-pulse' : ''}`} />
                <span>{node.label}</span>
                {isLatest && node.rawStatus === 'posted' && (
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                )}
              </button>

              {index < transitions.length - 1 && (
                <ArrowRight className="w-3.5 h-3.5 text-slate-600 shrink-0" />
              )}
            </React.Fragment>
          )
        })}
      </div>
    </div>
  )
}
