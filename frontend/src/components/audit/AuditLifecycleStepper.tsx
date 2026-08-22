import React, { useState } from 'react'
import {
  ArrowLeftRight,
  ChevronDown,
  ChevronUp,
  Clock,
  CornerDownRight,
  FileText,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  UserCheck,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { AuditEventResponse } from '../../services/api'

export type StageStatus = 'completed' | 'failed' | 'in_progress' | 'skipped' | 'not_reached'

export interface ReviewSubStep {
  id: string
  label: string
  status: 'approved' | 'edited' | 'rejected' | 'pending'
  timestamp: string
  eventId: string
  actorName: string
}

export interface LifecycleStage {
  key: 'upload' | 'intake' | 'bookkeeping' | 'review' | 'posted' | 'reconciliation'
  label: string
  subtitle: string
  icon: LucideIcon
  status: StageStatus
  durationText: string
  timestamp?: string
  eventId?: string
  subSteps?: ReviewSubStep[]
}

function formatDuration(startIso?: string, endIso?: string): string {
  if (!startIso || !endIso) return '—'
  const start = new Date(startIso).getTime()
  const end = new Date(endIso).getTime()
  const diffSec = Math.max(0, (end - start) / 1000)

  if (diffSec < 1) return '< 1s'
  if (diffSec < 60) return `${Math.round(diffSec)}s`
  const mins = Math.floor(diffSec / 60)
  const secs = Math.round(diffSec % 60)
  return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`
}

export function deriveLifecycleStages(events: AuditEventResponse[]): LifecycleStage[] {
  const sorted = [...events].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  )

  // Helper getters
  const uploadEvt = sorted.find((e) => e.event_type === 'document_uploaded')
  const intakeEvt = sorted.find((e) => e.event_type === 'extraction_completed')
  const bookkeepingEvt = sorted.find((e) => e.event_type === 'bookkeeping_completed')
  
  const reviewEvts = sorted.filter((e) =>
    e.event_type.startsWith('review_item_') ||
    e.event_type === 'bookkeeping_continued_after_extraction_review'
  )

  const postedEvt = sorted.find((e) => e.event_type === 'journal_entry_posted')
  const reconEvt = sorted.find((e) => e.event_type.startsWith('reconciliation_match_'))

  // 1. Stage 1: Upload
  let uploadStatus: StageStatus = uploadEvt ? 'completed' : 'not_reached'

  // 2. Stage 2: Document Intake
  let intakeStatus: StageStatus = 'not_reached'
  if (intakeEvt) {
    const snap = intakeEvt.output_snapshot || {}
    intakeStatus = snap.status === 'failed' ? 'failed' : 'completed'
  }

  // 3. Stage 3: AI Bookkeeping
  let bkStatus: StageStatus = 'not_reached'
  if (bookkeepingEvt) {
    const snap = bookkeepingEvt.output_snapshot || {}
    bkStatus =
      snap.status === 'failed' || snap.decision === 'failed' ? 'failed' : 'completed'
  }

  // 4. Stage 4: Human Review (Sub-steps calculation)
  const subSteps: ReviewSubStep[] = []
  
  // Extraction review sub-step
  const extReview = reviewEvts.find(
    (e) =>
      e.source_type === 'document' ||
      e.event_type === 'bookkeeping_continued_after_extraction_review' ||
      (e.input_snapshot?.review_type === 'extraction')
  )
  if (extReview) {
    let subStatus: 'approved' | 'edited' | 'rejected' | 'pending' = 'pending'
    if (extReview.event_type === 'review_item_approved' || extReview.event_type === 'bookkeeping_continued_after_extraction_review') {
      subStatus = 'approved'
    } else if (extReview.event_type === 'review_item_edited') {
      subStatus = 'edited'
    } else if (extReview.event_type === 'review_item_rejected') {
      subStatus = 'rejected'
    }
    subSteps.push({
      id: `ext-${extReview.id}`,
      label: 'Extraction Review',
      status: subStatus,
      timestamp: extReview.created_at,
      eventId: extReview.id,
      actorName: extReview.actor_name || 'Reviewer',
    })
  }

  // Bookkeeping review sub-step
  const bkReview = reviewEvts.find(
    (e) =>
      (e.source_type === 'journal_entry' && e.event_type.startsWith('review_item_')) ||
      (e.input_snapshot?.review_type === 'bookkeeping') ||
      (e.source_type === 'review_item' && e.id !== extReview?.id) ||
      (e.source_type === 'review_item' && e.id !== extReview?.id)
  )
  if (bkReview && bkReview.id !== extReview?.id) {
    let subStatus: 'approved' | 'edited' | 'rejected' | 'pending' = 'pending'
    if (bkReview.event_type === 'review_item_approved') {
      subStatus = 'approved'
    } else if (bkReview.event_type === 'review_item_edited') {
      subStatus = 'edited'
    } else if (bkReview.event_type === 'review_item_rejected') {
      subStatus = 'rejected'
    }
    subSteps.push({
      id: `bk-${bkReview.id}`,
      label: 'Bookkeeping Review',
      status: subStatus,
      timestamp: bkReview.created_at,
      eventId: bkReview.id,
      actorName: bkReview.actor_name || 'Reviewer',
    })
  }

  let reviewStatus: StageStatus = 'not_reached'
  if (subSteps.length > 0) {
    if (subSteps.some((s) => s.status === 'rejected')) {
      reviewStatus = 'failed'
    } else if (subSteps.every((s) => s.status === 'approved' || s.status === 'edited')) {
      reviewStatus = 'completed'
    } else {
      reviewStatus = 'in_progress'
    }
  }

  // 5. Stage 5: GL Posted
  let postedStatus: StageStatus = 'not_reached'
  if (postedEvt) {
    postedStatus = 'completed'
  }

  // 6. Stage 6: Bank Reconciliation
  let reconStatus: StageStatus = 'not_reached'
  if (reconEvt) {
    if (reconEvt.event_type === 'reconciliation_match_rejected') {
      reconStatus = 'failed'
    } else if (
      reconEvt.event_type === 'reconciliation_match_accepted' ||
      reconEvt.event_type === 'reconciliation_match_manual'
    ) {
      reconStatus = 'completed'
    } else {
      reconStatus = 'in_progress'
    }
  }

  const rawStages: {
    key: LifecycleStage['key']
    label: string
    subtitle: string
    icon: LucideIcon
    status: StageStatus
    timestamp?: string
    eventId?: string
    subSteps?: ReviewSubStep[]
  }[] = [
    {
      key: 'upload',
      label: 'Upload',
      subtitle: 'File Ingest',
      icon: UploadCloud,
      status: uploadStatus,
      timestamp: uploadEvt?.created_at,
      eventId: uploadEvt?.id,
    },
    {
      key: 'intake',
      label: 'Document Intake',
      subtitle: 'OCR & Entities',
      icon: FileText,
      status: intakeStatus,
      timestamp: intakeEvt?.created_at,
      eventId: intakeEvt?.id,
    },
    {
      key: 'bookkeeping',
      label: 'AI Bookkeeping',
      subtitle: 'COA Proposal',
      icon: Sparkles,
      status: bkStatus,
      timestamp: bookkeepingEvt?.created_at,
      eventId: bookkeepingEvt?.id,
    },
    {
      key: 'review',
      label: 'Human Review',
      subtitle: subSteps.length > 0 ? `${subSteps.length} Touchpoint(s)` : 'Zero Review',
      icon: UserCheck,
      status: reviewStatus,
      timestamp: subSteps[subSteps.length - 1]?.timestamp,
      eventId: subSteps[subSteps.length - 1]?.eventId,
      subSteps: subSteps.length > 0 ? subSteps : undefined,
    },
    {
      key: 'posted',
      label: 'GL Posted',
      subtitle: 'Ledger Entry',
      icon: ShieldCheck,
      status: postedStatus,
      timestamp: postedEvt?.created_at,
      eventId: postedEvt?.id,
    },
    {
      key: 'reconciliation',
      label: 'Bank Reconciliation',
      subtitle: 'Match & Verify',
      icon: ArrowLeftRight,
      status: reconStatus,
      timestamp: reconEvt?.created_at,
      eventId: reconEvt?.id,
    },
  ]

  // Apply skipped vs not_reached logic & failure propagation
  let hasFailedPrior = false

  for (let i = 0; i < rawStages.length; i++) {
    const current = rawStages[i]

    if (hasFailedPrior) {
      current.status = 'not_reached'
      continue
    }

    if (current.status === 'failed') {
      hasFailedPrior = true
      continue
    }

    if (current.status === 'not_reached') {
      // If any stage after this one has a completed/failed/in_progress event, mark as skipped
      const hasLaterEvents = rawStages
        .slice(i + 1)
        .some((s) => s.status === 'completed' || s.status === 'failed' || s.status === 'in_progress')

      if (hasLaterEvents) {
        current.status = 'skipped'
      }
    }
  }

  // Calculate durations between consecutive active stages
  const finalStages: LifecycleStage[] = []
  let previousTimestamp: string | undefined = undefined

  for (let i = 0; i < rawStages.length; i++) {
    const stage = rawStages[i]
    let durationText = '—'

    if (stage.status === 'completed' || stage.status === 'failed' || stage.status === 'in_progress') {
      if (i === 0) {
        durationText = '0s'
      } else if (stage.timestamp) {
        durationText = formatDuration(previousTimestamp, stage.timestamp)
      }
      if (stage.timestamp) {
        previousTimestamp = stage.timestamp
      }
    }

    finalStages.push({
      ...stage,
      durationText,
    })
  }

  return finalStages
}

interface AuditLifecycleStepperProps {
  events: AuditEventResponse[]
  onSelectEvent?: (eventId: string) => void
  activeEventId?: string | null
}

export const AuditLifecycleStepper: React.FC<AuditLifecycleStepperProps> = ({
  events,
  onSelectEvent,
  activeEventId,
}) => {
  const [expandedReview, setExpandedReview] = useState<boolean>(false)
  const stages = deriveLifecycleStages(events)

  if (stages.length === 0 || events.length === 0) return null

  const getStageStyles = (status: StageStatus) => {
    switch (status) {
      case 'completed':
        return {
          container: 'bg-emerald-950/30 border-emerald-500/40 text-slate-100 hover:bg-emerald-950/50 shadow-emerald-500/10 cursor-pointer',
          iconWrap: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40',
          badge: 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30',
          badgeText: 'Completed',
          connector: 'bg-emerald-500/60',
        }
      case 'failed':
        return {
          container: 'bg-rose-950/30 border-rose-500/40 text-slate-100 hover:bg-rose-950/50 shadow-rose-500/10 cursor-pointer',
          iconWrap: 'bg-rose-500/20 text-rose-400 border border-rose-500/40',
          badge: 'bg-rose-500/20 text-rose-300 border border-rose-500/30',
          badgeText: 'Failed',
          connector: 'bg-rose-500/40',
        }
      case 'in_progress':
        return {
          container: 'bg-amber-950/30 border-amber-500/40 text-slate-100 hover:bg-amber-950/50 shadow-amber-500/10 cursor-pointer',
          iconWrap: 'bg-amber-500/20 text-amber-400 border border-amber-500/40',
          badge: 'bg-amber-500/20 text-amber-300 border border-amber-500/30',
          badgeText: 'In Progress',
          connector: 'bg-amber-500/40',
        }
      case 'skipped':
        return {
          container: 'bg-slate-900/40 border-slate-700/60 border-dashed text-slate-400 opacity-75',
          iconWrap: 'bg-slate-800/80 text-slate-400 border border-slate-700',
          badge: 'bg-slate-800/80 text-slate-400 border border-slate-700 border-dashed',
          badgeText: 'Skipped',
          connector: 'bg-slate-700/60 border-dashed',
        }
      default: // not_reached
        return {
          container: 'bg-slate-950/40 border-slate-800 text-slate-500 opacity-50',
          iconWrap: 'bg-slate-900 text-slate-600 border border-slate-800',
          badge: 'bg-slate-900 text-slate-500 border border-slate-800',
          badgeText: 'Not Reached',
          connector: 'bg-slate-800',
        }
    }
  }

  return (
    <div className="p-4 sm:p-5 rounded-2xl bg-slate-900/60 border border-slate-800/90 shadow-xl backdrop-blur-sm space-y-3.5 animate-fade-in">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-indigo-400" />
          <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider font-mono">
            Accounting Pipeline Lifecycle Stepper
          </h3>
        </div>
        <span className="text-[10px] text-slate-400 font-mono">
          Stage Duration & Traceability
        </span>
      </div>

      {/* 6-Stage Horizontal Stepper Container */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
        {stages.map((stage, idx) => {
          const style = getStageStyles(stage.status)
          const Icon = stage.icon
          const hasReviewSubsteps = stage.key === 'review' && stage.subSteps && stage.subSteps.length > 0
          const isSelected = activeEventId === stage.eventId

          return (
            <div
              key={stage.key}
              className={`relative p-3 rounded-xl border flex flex-col justify-between transition-all select-none ${style.container} ${
                isSelected ? 'ring-2 ring-indigo-500 scale-[1.02]' : ''
              }`}
              onClick={() => {
                if (stage.eventId && onSelectEvent) {
                  onSelectEvent(stage.eventId)
                }
              }}
            >
              {/* Top Row: Icon + Status Badge */}
              <div className="flex items-center justify-between gap-1.5 mb-2">
                <div className={`p-1.5 rounded-lg shrink-0 ${style.iconWrap}`}>
                  <Icon className="w-3.5 h-3.5" />
                </div>

                <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider font-mono shrink-0 ${style.badge}`}>
                  {style.badgeText}
                </span>
              </div>

              {/* Middle: Stage Number + Name */}
              <div className="space-y-0.5">
                <span className="text-[10px] font-mono font-bold text-slate-400 block">
                  0{idx + 1}.
                </span>
                <p className="text-xs font-bold leading-tight truncate text-slate-100">
                  {stage.label}
                </p>
                <p className="text-[10px] text-slate-400 truncate">
                  {stage.subtitle}
                </p>
              </div>

              {/* Bottom: Duration & Expand trigger if review */}
              <div className="pt-2 mt-2 border-t border-slate-800/80 flex items-center justify-between text-[10px] font-mono">
                <span className="text-slate-400 flex items-center gap-1">
                  <Clock className="w-2.5 h-2.5 text-slate-500" />
                  {stage.durationText}
                </span>

                {hasReviewSubsteps && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      setExpandedReview(!expandedReview)
                    }}
                    className="p-1 rounded bg-slate-800 hover:bg-slate-700 text-indigo-300 transition-colors flex items-center gap-0.5 text-[9px] cursor-pointer"
                    title="Toggle review sub-steps"
                  >
                    <span>Sub-steps</span>
                    {expandedReview ? (
                      <ChevronUp className="w-2.5 h-2.5" />
                    ) : (
                      <ChevronDown className="w-2.5 h-2.5" />
                    )}
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Expandable Human Review Sub-steps Panel */}
      {expandedReview && stages.find((s) => s.key === 'review')?.subSteps && (
        <div className="p-3.5 rounded-xl bg-slate-950/90 border border-slate-800 space-y-2 animate-fade-in">
          <span className="text-[10px] font-bold text-amber-400 uppercase tracking-wider block font-mono">
            Human Review Touchpoints Detail:
          </span>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {stages
              .find((s) => s.key === 'review')
              ?.subSteps?.map((sub) => {
                const isSubSelected = activeEventId === sub.eventId
                return (
                  <button
                    key={sub.id}
                    type="button"
                    onClick={() => onSelectEvent?.(sub.eventId)}
                    className={`p-2.5 rounded-lg border flex items-center justify-between text-left transition-all cursor-pointer ${
                      sub.status === 'rejected'
                        ? 'bg-rose-500/10 border-rose-500/30 hover:bg-rose-500/20'
                        : 'bg-slate-900 border-slate-800 hover:bg-slate-800/80 hover:border-slate-700'
                    } ${isSubSelected ? 'ring-2 ring-indigo-500' : ''}`}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <CornerDownRight className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                      <div className="min-w-0">
                        <span className="text-xs font-semibold text-slate-200 block truncate">
                          {sub.label}
                        </span>
                        <span className="text-[10px] text-slate-400 font-mono block">
                          by {sub.actorName} • {new Date(sub.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                    </div>

                    <span
                      className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase font-mono tracking-wider shrink-0 ${
                        sub.status === 'rejected'
                          ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                          : sub.status === 'edited'
                            ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                            : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                      }`}
                    >
                      {sub.status}
                    </span>
                  </button>
                )
              })}
          </div>
        </div>
      )}
    </div>
  )
}
