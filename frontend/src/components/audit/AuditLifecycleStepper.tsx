import React from 'react'
import {
  ArrowLeftRight,
  Clock,
  FileText,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  UserCheck,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { AuditEventResponse } from '../../services/api'
import { getActorMeta } from './auditDisplayUtils'

export type StageStatus =
  'completed' | 'needs_review' | 'rejected' | 'failed' | 'skipped' | 'not_reached'

export interface ReviewedInfo {
  reviewer: string
  action: 'approved' | 'edited' | 'reviewed' | 'matched'
  timestamp: string
  eventId: string
}

export interface LifecycleStage {
  key: 'upload' | 'intake' | 'bookkeeping' | 'posted' | 'reconciliation'
  label: string
  subtitle: string
  icon: LucideIcon
  status: StageStatus
  durationText?: string
  actorType?: string
  timestamp?: string
  eventId?: string
  reviewedInfo?: ReviewedInfo
}

function formatProcessingDuration(value: unknown): string {
  const durationMs = Number(value)
  if (!Number.isFinite(durationMs) || durationMs < 0) return '—'
  if (durationMs < 1) return '<1ms'
  if (durationMs < 1000) return `${Math.round(durationMs)}ms`

  const durationSeconds = durationMs / 1000
  if (durationSeconds < 60) return `${Number(durationSeconds.toFixed(1))}s`

  const totalSeconds = Math.round(durationSeconds)
  const mins = Math.floor(totalSeconds / 60)
  const secs = totalSeconds % 60
  return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`
}

function deriveLifecycleStages(events: AuditEventResponse[]): LifecycleStage[] {
  const sorted = [...events].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  )

  // 1. Stage anchor events
  const uploadEvt = sorted.find((e) => e.event_type === 'document_uploaded')
  const intakeEvt = sorted.find((e) => e.event_type === 'extraction_completed')
  const bookkeepingEvt = sorted.find((e) => e.event_type === 'bookkeeping_completed')
  const postedEvt = sorted.find((e) => e.event_type === 'journal_entry_posted')
  const reconEvts = sorted.filter((e) => e.event_type.startsWith('reconciliation_match_'))

  // Review events
  const reviewEvts = sorted.filter((e) => e.event_type.startsWith('review_item_'))

  const intakeTs = intakeEvt ? new Date(intakeEvt.created_at).getTime() : null
  const bkTs = bookkeepingEvt ? new Date(bookkeepingEvt.created_at).getTime() : null

  // Route review events to their owning stage
  const getReviewStage = (evt: AuditEventResponse): 'intake' | 'bookkeeping' | 'reconciliation' => {
    const rType = evt.input_snapshot?.review_type
    if (rType === 'extraction') return 'intake'
    if (rType === 'bookkeeping') return 'bookkeeping'
    if (rType === 'reconciliation') return 'reconciliation'

    if (evt.source_type === 'document') return 'intake'
    if (evt.source_type === 'journal_entry') return 'bookkeeping'
    if (evt.source_type === 'bank_transaction' || evt.source_type === 'reconciliation_match') {
      return 'reconciliation'
    }

    const t = new Date(evt.created_at).getTime()
    if (bkTs !== null && t >= bkTs) return 'bookkeeping'
    if (intakeTs !== null && t >= intakeTs) return 'intake'
    return 'intake'
  }

  // --- 1. Stage: Upload ---
  let uploadStatus: StageStatus = 'not_reached'
  if (uploadEvt) {
    const snap = uploadEvt.output_snapshot || {}
    uploadStatus = snap.status === 'failed' ? 'failed' : 'completed'
  }

  // --- 2. Stage: Intake Agent ---
  let intakeStatus: StageStatus = 'not_reached'
  let intakeReviewedInfo: ReviewedInfo | undefined = undefined
  const intakeEventId = intakeEvt?.id
  const intakeTimestamp = intakeEvt?.created_at

  if (intakeEvt) {
    const intakeSnap = intakeEvt.output_snapshot || {}
    const intakeReviews = reviewEvts.filter((e) => getReviewStage(e) === 'intake')
    const hasIntakeReject = intakeReviews.some((e) => e.event_type === 'review_item_rejected')
    const intakeResolveEvt = intakeReviews.find(
      (e) => e.event_type === 'review_item_approved' || e.event_type === 'review_item_edited'
    )

    if (intakeSnap.status === 'failed') {
      intakeStatus = 'failed'
    } else if (hasIntakeReject) {
      intakeStatus = 'rejected'
    } else {
      const extractionFlagged =
        intakeSnap.status === 'extraction_review_required' ||
        (intakeSnap.needs_review === true && !bookkeepingEvt)

      if (extractionFlagged && !intakeResolveEvt) {
        intakeStatus = 'needs_review'
      } else {
        intakeStatus = 'completed'
      }
    }

    if (intakeResolveEvt) {
      intakeReviewedInfo = {
        reviewer: intakeResolveEvt.actor_name || 'Human Reviewer',
        action: intakeResolveEvt.event_type === 'review_item_edited' ? 'edited' : 'approved',
        timestamp: intakeResolveEvt.created_at,
        eventId: intakeResolveEvt.id,
      }
    }
  }

  // --- 3. Stage: Bookkeeping Agent ---
  let bkStatus: StageStatus = 'not_reached'
  let bkReviewedInfo: ReviewedInfo | undefined = undefined
  const bkEventId = bookkeepingEvt?.id
  const bkTimestamp = bookkeepingEvt?.created_at

  if (bookkeepingEvt) {
    const bkSnap = bookkeepingEvt.output_snapshot || {}
    const bkReviews = reviewEvts.filter((e) => getReviewStage(e) === 'bookkeeping')
    const hasBkReject = bkReviews.some((e) => e.event_type === 'review_item_rejected')
    const bkResolveEvt = bkReviews.find(
      (e) => e.event_type === 'review_item_approved' || e.event_type === 'review_item_edited'
    )

    if (bkSnap.status === 'failed' || bkSnap.decision === 'failed') {
      bkStatus = 'failed'
    } else if (hasBkReject) {
      bkStatus = 'rejected'
    } else {
      const intakeSnap = intakeEvt?.output_snapshot || {}
      const bookkeepingStatus = String(bkSnap.status || '')
        .toLowerCase()
        .trim()
      const bkFlagged =
        bkSnap.needs_review === true ||
        bookkeepingStatus === 'bookkeeping_review_required' ||
        bookkeepingStatus === 'review_required' ||
        intakeSnap.status === 'bookkeeping_review_required'

      if (bkFlagged && !bkResolveEvt) {
        bkStatus = 'needs_review'
      } else {
        bkStatus = 'completed'
      }
    }

    if (bkResolveEvt) {
      bkReviewedInfo = {
        reviewer: bkResolveEvt.actor_name || 'Human Reviewer',
        action: bkResolveEvt.event_type === 'review_item_edited' ? 'edited' : 'approved',
        timestamp: bkResolveEvt.created_at,
        eventId: bkResolveEvt.id,
      }
    }
  }

  // --- 4. Stage: GL Posted ---
  let postedStatus: StageStatus = 'not_reached'
  if (postedEvt) {
    const snap = postedEvt.output_snapshot || {}
    postedStatus = snap.status === 'failed' ? 'failed' : 'completed'
  }

  // --- 5. Stage: Reconciliation Agent ---
  let reconStatus: StageStatus = 'not_reached'
  let reconReviewedInfo: ReviewedInfo | undefined = undefined
  let reconEventId = reconEvts[reconEvts.length - 1]?.id
  let reconTimestamp = reconEvts[reconEvts.length - 1]?.created_at

  let reconActorType = 'agent'
  if (reconEvts.length > 0) {
    const reconAccepted = reconEvts.find(
      (e) =>
        e.event_type === 'reconciliation_match_accepted' ||
        e.event_type === 'reconciliation_match_manual'
    )
    const reconProposed = reconEvts.find((e) => e.event_type === 'reconciliation_match_proposed')
    const reconRejected = reconEvts.find((e) => e.event_type === 'reconciliation_match_rejected')

    if (reconAccepted?.actor_type) {
      reconActorType = reconAccepted.actor_type
    } else if (reconRejected?.actor_type) {
      reconActorType = reconRejected.actor_type
    } else if (reconProposed?.actor_type) {
      reconActorType = reconProposed.actor_type
    } else if (reconEvts[reconEvts.length - 1]?.actor_type) {
      reconActorType = reconEvts[reconEvts.length - 1].actor_type
    }

    if (reconAccepted) {
      reconStatus = 'completed'
      reconEventId = reconAccepted.id
      reconTimestamp = reconAccepted.created_at
      if (
        reconAccepted.actor_type === 'human' ||
        reconAccepted.event_type === 'reconciliation_match_manual'
      ) {
        reconReviewedInfo = {
          reviewer: reconAccepted.actor_name || 'Human Reviewer',
          action: 'matched',
          timestamp: reconAccepted.created_at,
          eventId: reconAccepted.id,
        }
      }
    } else if (reconRejected) {
      reconStatus = 'rejected'
      reconEventId = reconRejected.id
      reconTimestamp = reconRejected.created_at
    } else if (reconProposed) {
      reconStatus = 'needs_review'
      reconEventId = reconProposed.id
      reconTimestamp = reconProposed.created_at
    }
  }

  const rawStages: {
    key: LifecycleStage['key']
    label: string
    subtitle: string
    icon: LucideIcon
    status: StageStatus
    actorType: string
    timestamp?: string
    eventId?: string
    reviewedInfo?: ReviewedInfo
    processingDurationMs?: unknown
  }[] = [
    {
      key: 'upload',
      label: 'Upload',
      subtitle: 'File Ingest',
      icon: UploadCloud,
      status: uploadStatus,
      actorType: uploadEvt?.actor_type || 'human',
      timestamp: uploadEvt?.created_at,
      eventId: uploadEvt?.id,
    },
    {
      key: 'intake',
      label: 'Intake Agent',
      subtitle: 'OCR & Extraction',
      icon: FileText,
      status: intakeStatus,
      actorType: intakeEvt?.actor_type || 'agent',
      timestamp: intakeTimestamp,
      eventId: intakeEventId,
      reviewedInfo: intakeReviewedInfo,
      processingDurationMs: intakeEvt?.output_snapshot?.processing_duration_ms,
    },
    {
      key: 'bookkeeping',
      label: 'Bookkeeping Agent',
      subtitle: 'COA Proposal',
      icon: Sparkles,
      status: bkStatus,
      actorType: bookkeepingEvt?.actor_type || 'agent',
      timestamp: bkTimestamp,
      eventId: bkEventId,
      reviewedInfo: bkReviewedInfo,
      processingDurationMs: bookkeepingEvt?.output_snapshot?.processing_duration_ms,
    },
    {
      key: 'posted',
      label: 'GL Posted',
      subtitle: 'Ledger Entry',
      icon: ShieldCheck,
      status: postedStatus,
      actorType: postedEvt?.actor_type || 'human',
      timestamp: postedEvt?.created_at,
      eventId: postedEvt?.id,
    },
    {
      key: 'reconciliation',
      label: 'Reconciliation Agent',
      subtitle: 'Match & Verify',
      icon: ArrowLeftRight,
      status: reconStatus,
      actorType: reconActorType,
      timestamp: reconTimestamp,
      eventId: reconEventId,
      reviewedInfo: reconReviewedInfo,
    },
  ]

  // Pipeline failure/rejection propagation & skipped detection
  let hasStoppedPrior = false

  for (let i = 0; i < rawStages.length; i++) {
    const current = rawStages[i]

    if (hasStoppedPrior) {
      current.status = 'not_reached'
      continue
    }

    if (current.status === 'failed' || current.status === 'rejected') {
      hasStoppedPrior = true
      continue
    }

    if (current.status === 'not_reached') {
      const hasLaterActiveEvents = rawStages
        .slice(i + 1)
        .some(
          (s) =>
            s.status === 'completed' ||
            s.status === 'failed' ||
            s.status === 'rejected' ||
            s.status === 'needs_review'
        )

      if (hasLaterActiveEvents) {
        current.status = 'skipped'
      }
    }
  }

  // Agent durations come from monotonic backend measurements, never event gaps.
  const finalStages: LifecycleStage[] = []

  for (let i = 0; i < rawStages.length; i++) {
    const stage = rawStages[i]
    let durationText: string | undefined = undefined

    if (
      stage.status === 'completed' ||
      stage.status === 'failed' ||
      stage.status === 'rejected' ||
      stage.status === 'needs_review'
    ) {
      if (stage.key === 'upload') {
        durationText = '0s'
      } else if (stage.key === 'intake' || stage.key === 'bookkeeping') {
        durationText = `Processing: ${formatProcessingDuration(stage.processingDurationMs)}`
      } else {
        // Stage 4 'posted' and Stage 5 'reconciliation': duration removed as per spec
        durationText = undefined
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
  const stages = deriveLifecycleStages(events)

  if (stages.length === 0 || events.length === 0) return null

  const getStageStyles = (status: StageStatus) => {
    switch (status) {
      case 'completed':
        return {
          container:
            'bg-emerald-950/30 border-emerald-500/40 text-slate-100 hover:bg-emerald-950/50 shadow-emerald-500/10 cursor-pointer',
          iconWrap: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40',
          badge: 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-mono',
          badgeText: 'Completed',
          connector: 'bg-emerald-500/60',
        }
      case 'needs_review':
        return {
          container:
            'bg-amber-950/30 border-amber-500/60 text-slate-100 hover:bg-amber-950/50 shadow-amber-500/15 ring-1 ring-amber-500/40 cursor-pointer',
          iconWrap: 'bg-amber-500/20 text-amber-400 border border-amber-500/40',
          badge: 'bg-amber-500/20 text-amber-300 border border-amber-500/30 font-mono',
          badgeText: 'Needs Review',
          connector: 'bg-amber-500/40',
        }
      case 'rejected':
        return {
          container:
            'bg-rose-950/30 border-rose-500/40 text-slate-100 hover:bg-rose-950/50 shadow-rose-500/10 cursor-pointer',
          iconWrap: 'bg-rose-500/20 text-rose-400 border border-rose-500/40',
          badge: 'bg-rose-500/20 text-rose-300 border border-rose-500/30 font-mono',
          badgeText: 'Rejected',
          connector: 'bg-rose-500/40',
        }
      case 'failed':
        return {
          container:
            'bg-red-950/40 border-red-600/50 text-slate-100 hover:bg-red-950/60 shadow-red-500/10 cursor-pointer',
          iconWrap: 'bg-red-500/20 text-red-400 border border-red-500/40',
          badge: 'bg-red-500/20 text-red-300 border border-red-500/30 font-mono',
          badgeText: 'Failed',
          connector: 'bg-red-500/40',
        }
      case 'skipped':
        return {
          container: 'bg-slate-900/40 border-slate-700/60 border-dashed text-slate-400 opacity-75',
          iconWrap: 'bg-slate-800/80 text-slate-400 border border-slate-700',
          badge: 'bg-slate-800/80 text-slate-400 border border-slate-700 border-dashed font-mono',
          badgeText: 'Skipped',
          connector: 'bg-slate-700/60 border-dashed',
        }
      default: // not_reached
        return {
          container: 'bg-slate-950/40 border-slate-800 text-slate-500 opacity-50',
          iconWrap: 'bg-slate-900 text-slate-600 border border-slate-800',
          badge: 'bg-slate-900 text-slate-500 border border-slate-800 font-mono',
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
          Document Lifecycle & Traceability
        </span>
      </div>

      {/* 5-Stage Horizontal Stepper Container */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        {stages.map((stage, idx) => {
          const style = getStageStyles(stage.status)
          const Icon = stage.icon
          const isSelected = activeEventId === stage.eventId

          return (
            <div
              key={stage.key}
              className={`relative p-3.5 rounded-xl border flex flex-col justify-between transition-all select-none ${
                style.container
              } ${isSelected ? 'ring-2 ring-indigo-500 scale-[1.02]' : ''}`}
              onClick={() => {
                if (stage.eventId && onSelectEvent) {
                  onSelectEvent(stage.eventId)
                }
              }}
            >
              {/* Top Row: Icon + Status Badge */}
              <div className="flex items-center justify-between gap-1.5 mb-2">
                <div className={`p-1.5 rounded-lg shrink-0 ${style.iconWrap}`}>
                  <Icon className="w-4 h-4" />
                </div>

                <span
                  className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider shrink-0 flex items-center gap-1 ${style.badge}`}
                >
                  {stage.status === 'needs_review' && (
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-400" />
                    </span>
                  )}
                  {style.badgeText}
                </span>
              </div>

              {/* Middle: Stage Number + Actor Tag + Name + Subtitle */}
              <div className="space-y-1">
                <div className="flex items-center justify-between gap-1">
                  <span className="text-[10px] font-mono font-bold text-slate-400 block">
                    0{idx + 1}.
                  </span>
                  {stage.actorType &&
                    (() => {
                      const meta = getActorMeta(stage.actorType)
                      const ActorIcon = meta.Icon
                      return (
                        <span
                          className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[8px] font-bold uppercase tracking-wider ${meta.badgeClass}`}
                          title={`Actor: ${meta.label}`}
                        >
                          <ActorIcon className={`w-2.5 h-2.5 ${meta.textClass}`} />
                          {meta.label}
                        </span>
                      )
                    })()}
                </div>
                <p className="text-xs font-bold leading-tight truncate text-slate-100">
                  {stage.label}
                </p>
                <p className="text-[10px] text-slate-400 truncate">{stage.subtitle}</p>

                {/* Step 3: Reviewed Indicator Badge */}
                {stage.reviewedInfo && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      if (stage.reviewedInfo?.eventId && onSelectEvent) {
                        onSelectEvent(stage.reviewedInfo.eventId)
                      }
                    }}
                    className="mt-1.5 inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[9px] font-mono font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 hover:bg-indigo-500/30 hover:border-indigo-400 transition-all cursor-pointer shadow-sm w-fit"
                    title={`Reviewed by ${stage.reviewedInfo.reviewer} (${stage.reviewedInfo.action}) at ${new Date(
                      stage.reviewedInfo.timestamp
                    ).toLocaleTimeString()}`}
                  >
                    <UserCheck className="w-2.5 h-2.5 text-indigo-400 shrink-0" />
                    <span>Reviewed</span>
                    <span className="text-slate-400 font-normal truncate max-w-[65px]">
                      • {stage.reviewedInfo.reviewer}
                    </span>
                  </button>
                )}
              </div>

              {/* Bottom: Duration & Hint */}
              <div className="pt-2 mt-2 border-t border-slate-800/80 flex items-center justify-between text-[10px] font-mono min-h-[20px]">
                {stage.durationText ? (
                  <span className="text-slate-400 flex items-center gap-1">
                    <Clock className="w-2.5 h-2.5 text-slate-500" />
                    {stage.durationText}
                  </span>
                ) : (
                  <span />
                )}

                {stage.status === 'needs_review' && (
                  <span className="text-[9px] font-semibold text-amber-400 animate-pulse">
                    Action Required
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
