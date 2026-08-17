import React, { useEffect, useRef, useState } from 'react'
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Loader2,
  Sparkles,
  Terminal,
  X,
} from 'lucide-react'
import type { ReconciliationStreamEvent } from '../../services/api'
import { API_BASE_URL } from '../../services/api'

interface ReconciliationLiveStreamCardProps {
  importId: string
  statementFilename?: string
  isOpen: boolean
  onClose: () => void
  onCompleted: () => void
}

interface LogEntry {
  id: string
  time: string
  stage: ReconciliationStreamEvent['stage']
  message: string
  confidence?: number
}

export const ReconciliationLiveStreamCard: React.FC<
  ReconciliationLiveStreamCardProps
> = ({ importId, statementFilename, isOpen, onClose, onCompleted }) => {
  const [events, setEvents] = useState<LogEntry[]>([])
  const [status, setStatus] = useState<
    'connecting' | 'running' | 'completed' | 'error'
  >('connecting')
  const [percentage, setPercentage] = useState<number>(0)
  const [currentTx, setCurrentTx] = useState<{
    description?: string
    amount?: number
    current?: number
    total?: number
    stage?: string
  }>({})
  const [counts, setCounts] = useState({
    matched: 0,
    proposed: 0,
    unmatched: 0,
    total: 0,
  })
  const [isMinimized, setIsMinimized] = useState<boolean>(false)

  const logEndRef = useRef<HTMLDivElement | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  // Auto-scroll logs as new events stream in
  useEffect(() => {
    if (!isMinimized && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [events, isMinimized])

  // Establish Server-Sent Events (SSE) Stream
  useEffect(() => {
    if (!isOpen || !importId) return

    setEvents([])
    setPercentage(0)
    setStatus('connecting')
    setCounts({ matched: 0, proposed: 0, unmatched: 0, total: 0 })
    setCurrentTx({})

    const streamUrl = `${API_BASE_URL}/reconciliation/stream/${importId}`
    const es = new EventSource(streamUrl)
    eventSourceRef.current = es

    es.onopen = () => {
      setStatus('running')
    }

    es.onmessage = (event) => {
      try {
        const data: ReconciliationStreamEvent = JSON.parse(event.data)
        const nowStr = new Date().toLocaleTimeString('en-US', {
          hour12: false,
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        })

        const newLog: LogEntry = {
          id: Math.random().toString(36).substring(2, 9),
          time: nowStr,
          stage: data.stage,
          message: data.message,
          confidence: data.confidence,
        }

        setEvents((prev) => [...prev, newLog])

        if (data.percentage != null) {
          setPercentage(data.percentage)
        }

        if (data.current != null || data.total != null || data.description != null) {
          setCurrentTx({
            description: data.description,
            amount: data.amount,
            current: data.current,
            total: data.total,
            stage: data.stage,
          })
        }

        if (data.total != null) {
          setCounts((prev) => ({ ...prev, total: data.total ?? prev.total }))
        }
        if (data.matched_count != null) {
          setCounts((prev) => ({ ...prev, matched: data.matched_count ?? prev.matched }))
        }
        if (data.proposed_count != null) {
          setCounts((prev) => ({ ...prev, proposed: data.proposed_count ?? prev.proposed }))
        }
        if (data.unmatched_count != null) {
          setCounts((prev) => ({ ...prev, unmatched: data.unmatched_count ?? prev.unmatched }))
        }

        if (data.stage === 'completed') {
          setStatus('completed')
          setPercentage(100)
          es.close()
          onCompleted()
        } else if (data.stage === 'error') {
          setStatus('error')
          es.close()
        }
      } catch (err) {
        console.error('Error parsing SSE event:', err)
      }
    }

    es.onerror = (err) => {
      console.warn('SSE EventSource ended or disconnected:', err)
      // Check if we already reached completed
      setStatus((prev) => (prev === 'completed' ? 'completed' : 'error'))
      es.close()
    }

    return () => {
      es.close()
    }
  }, [isOpen, importId])

  if (!isOpen) return null

  const formatCurrency = (amount?: number) => {
    if (amount == null) return ''
    return new Intl.NumberFormat('id-ID', {
      style: 'currency',
      currency: 'IDR',
      minimumFractionDigits: 0,
    }).format(Math.abs(amount))
  }

  const getStageIcon = (stage: ReconciliationStreamEvent['stage']) => {
    switch (stage) {
      case 'exact_match_found':
      case 'already_matched':
        return <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
      case 'agent_invoked':
      case 'agent_match_accepted':
        return <Sparkles className="w-4 h-4 text-purple-400 shrink-0" />
      case 'review_queued':
        return <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
      case 'unmatched_queued':
        return <AlertCircle className="w-4 h-4 text-cyan-400 shrink-0" />
      case 'completed':
        return <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
      case 'error':
      case 'agent_error':
        return <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
      default:
        return <Activity className="w-4 h-4 text-slate-400 shrink-0" />
    }
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 w-full max-w-xl animate-in fade-in slide-in-from-bottom-5 duration-300">
      <div className="rounded-2xl bg-slate-900/95 border border-slate-700/80 shadow-2xl backdrop-blur-xl overflow-hidden flex flex-col transition-all">
        {/* Header Bar */}
        <div className="p-4 bg-gradient-to-r from-slate-900 via-slate-800 to-indigo-950/60 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="relative">
              <div className="p-2 rounded-xl bg-gradient-to-tr from-emerald-600 to-indigo-600 text-white shadow-md shadow-emerald-500/20">
                <Bot className="w-5 h-5" />
              </div>
              {status === 'running' && (
                <span className="absolute -top-0.5 -right-0.5 w-3 h-3 bg-emerald-400 rounded-full animate-ping" />
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-white tracking-tight flex items-center gap-1.5">
                  AI Reconciliation Engine
                  <span className="text-[11px] font-mono text-purple-300 font-normal">
                    (Gemini 3 Flash)
                  </span>
                </h3>
                {status === 'running' && (
                  <span className="px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-[10px] font-bold font-mono flex items-center gap-1">
                    <Loader2 className="w-2.5 h-2.5 animate-spin" /> LIVE STREAM
                  </span>
                )}
                {status === 'completed' && (
                  <span className="px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-[10px] font-bold font-mono">
                    ✓ COMPLETED
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400 mt-0.5 font-mono truncate max-w-xs">
                {statementFilename || 'Active Bank Statement Batch'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => setIsMinimized(!isMinimized)}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer"
              title={isMinimized ? 'Expand window' : 'Minimize window'}
            >
              {isMinimized ? (
                <ChevronUp className="w-4 h-4" />
              ) : (
                <ChevronDown className="w-4 h-4" />
              )}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer"
              title="Close stream"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Minimized Quick Bar */}
        {isMinimized && (
          <div className="px-4 py-3 bg-slate-950/60 flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <span className="text-slate-400 font-medium">Progress:</span>
              <span className="font-bold text-emerald-400 font-mono">
                {percentage}%
              </span>
            </div>
            <div className="flex items-center gap-3 text-[11px] font-mono">
              <span className="text-emerald-300">✓ Matched: {counts.matched}</span>
              <span className="text-amber-300">⚠️ Review: {counts.proposed}</span>
              <span className="text-cyan-300">✕ Bank Only: {counts.unmatched}</span>
            </div>
          </div>
        )}

        {/* Full Interactive Body (when not minimized) */}
        {!isMinimized && (
          <div className="p-4 space-y-4 max-h-[70vh] overflow-hidden flex flex-col">
            {/* Live Progress Bar & Stats Grid */}
            <div className="space-y-2 bg-slate-950/60 p-3.5 rounded-xl border border-slate-800/80">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400 font-medium flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5 text-emerald-400" />
                  Matching Pipeline Progress
                </span>
                <span className="font-bold text-white font-mono">{percentage}%</span>
              </div>
              <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-emerald-500 via-teal-400 to-indigo-500 transition-all duration-300"
                  style={{ width: `${percentage}%` }}
                />
              </div>

              {/* Counters Badges */}
              <div className="grid grid-cols-4 gap-2 pt-1 text-center">
                <div className="p-2 rounded-lg bg-slate-900/80 border border-slate-800">
                  <span className="text-[10px] text-slate-400 uppercase font-bold block">
                    Evaluated
                  </span>
                  <span className="text-xs font-bold text-white font-mono">
                    {currentTx.current || 0}/{counts.total || 0}
                  </span>
                </div>
                <div className="p-2 rounded-lg bg-emerald-950/40 border border-emerald-500/20">
                  <span className="text-[10px] text-emerald-400 uppercase font-bold block">
                    Matched
                  </span>
                  <span className="text-xs font-bold text-emerald-300 font-mono">
                    {counts.matched}
                  </span>
                </div>
                <div className="p-2 rounded-lg bg-amber-950/40 border border-amber-500/20">
                  <span className="text-[10px] text-amber-400 uppercase font-bold block">
                    Needs Review
                  </span>
                  <span className="text-xs font-bold text-amber-300 font-mono">
                    {counts.proposed}
                  </span>
                </div>
                <div className="p-2 rounded-lg bg-cyan-950/40 border border-cyan-500/20">
                  <span className="text-[10px] text-cyan-400 uppercase font-bold block">
                    Bank Only
                  </span>
                  <span className="text-xs font-bold text-cyan-300 font-mono">
                    {counts.unmatched}
                  </span>
                </div>
              </div>
            </div>

            {/* Currently Active Transaction Highlight (if running) */}
            {status === 'running' && currentTx.description && (
              <div className="p-3 rounded-xl bg-slate-950/80 border border-indigo-500/30 space-y-1.5 animate-pulse">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-wider flex items-center gap-1">
                    <Sparkles className="w-3 h-3 text-indigo-400" /> Active Reasoning
                  </span>
                  {currentTx.amount != null && (
                    <span className="font-mono font-bold text-white text-xs">
                      {formatCurrency(currentTx.amount)}
                    </span>
                  )}
                </div>
                <p className="text-xs font-semibold text-slate-200 line-clamp-1">
                  {currentTx.description}
                </p>
              </div>
            )}

            {/* Live Terminal / Log Stream Feed */}
            <div className="space-y-1.5 flex-1 min-h-0 flex flex-col">
              <div className="flex items-center justify-between text-[11px] text-slate-400 font-medium px-1">
                <span className="flex items-center gap-1">
                  <Terminal className="w-3 h-3 text-slate-500" /> Live Execution Stream
                </span>
                <span>{events.length} events logged</span>
              </div>

              <div className="flex-1 overflow-y-auto max-h-48 rounded-xl bg-slate-950/90 border border-slate-800 p-3 font-mono text-xs space-y-2 scrollbar-thin">
                {events.length === 0 ? (
                  <div className="py-6 text-center text-slate-500 text-[11px] flex items-center justify-center gap-2">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    Connecting to Reconciliation Agent stream...
                  </div>
                ) : (
                  events.map((evt) => (
                    <div
                      key={evt.id}
                      className="flex items-start gap-2 leading-relaxed animate-in fade-in duration-150"
                    >
                      <span className="text-[10px] text-slate-500 shrink-0 mt-0.5">
                        [{evt.time}]
                      </span>
                      {getStageIcon(evt.stage)}
                      <span className="text-slate-300 text-[11px] break-words">
                        {evt.message}
                      </span>
                    </div>
                  ))
                )}
                <div ref={logEndRef} />
              </div>
            </div>

            {/* Completion or Action Footer */}
            {status === 'completed' && (
              <div className="p-3.5 rounded-xl bg-emerald-950/60 border border-emerald-500/40 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
                  <div>
                    <p className="text-xs font-bold text-white">
                      Reconciliation Complete!
                    </p>
                    <p className="text-[11px] text-emerald-300">
                      Statement data successfully updated and balanced.
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={onClose}
                  className="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs shadow-md transition-colors cursor-pointer shrink-0"
                >
                  View Workspace
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
