import React, { useEffect, useRef, useState } from 'react'
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  FileSpreadsheet,
  FileText,
  Loader2,
  Sparkles,
  Terminal,
  X,
} from 'lucide-react'
import type { DocumentStreamEvent } from '../../services/api'
import { API_BASE_URL } from '../../services/api'

interface DocumentLiveStreamCardProps {
  documentId: string
  filename?: string
  isOpen: boolean
  onClose: () => void
  onCompleted: () => void
}

interface LogEntry {
  id: string
  time: string
  stage: DocumentStreamEvent['stage']
  message: string
}

export const DocumentLiveStreamCard: React.FC<DocumentLiveStreamCardProps> = ({
  documentId,
  filename,
  isOpen,
  onClose,
  onCompleted,
}) => {
  const [events, setEvents] = useState<LogEntry[]>([])
  const [status, setStatus] = useState<'connecting' | 'running' | 'completed' | 'error'>(
    'connecting'
  )
  const [percentage, setPercentage] = useState<number>(0)
  const [extractedData, setExtractedData] = useState<{
    vendor_name?: string
    total_amount?: number
    currency?: string
    confidence_score?: number
    text_preview?: string
  }>({})
  const [isMinimized, setIsMinimized] = useState<boolean>(false)

  const logEndRef = useRef<HTMLDivElement | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  // Auto-scroll logs as new events stream in
  useEffect(() => {
    if (!isMinimized && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [events, isMinimized])

  // Establish SSE connection
  useEffect(() => {
    if (!isOpen || !documentId) return

    setEvents([])
    setPercentage(0)
    setStatus('connecting')
    setExtractedData({})

    const streamUrl = `${API_BASE_URL}/documents/stream/${documentId}`
    const es = new EventSource(streamUrl)
    eventSourceRef.current = es

    es.onopen = () => {
      setStatus('running')
    }

    es.onmessage = (event) => {
      try {
        const data: DocumentStreamEvent = JSON.parse(event.data)
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
        }

        setEvents((prev) => [...prev, newLog])

        if (data.percentage != null) {
          setPercentage(data.percentage)
        }

        if (
          data.vendor_name ||
          data.total_amount != null ||
          data.confidence_score != null ||
          data.text_preview
        ) {
          setExtractedData((prev) => ({
            vendor_name: data.vendor_name ?? prev.vendor_name,
            total_amount: data.total_amount ?? prev.total_amount,
            currency: data.currency ?? prev.currency ?? 'IDR',
            confidence_score: data.confidence_score ?? prev.confidence_score,
            text_preview: data.text_preview ?? prev.text_preview,
          }))
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
      setStatus((prev) => (prev === 'completed' ? 'completed' : 'error'))
      es.close()
    }

    return () => {
      es.close()
    }
  }, [isOpen, documentId, onCompleted])

  if (!isOpen) return null

  const formatCurrency = (amount?: number, curr = 'IDR') => {
    if (amount == null) return '-'
    return new Intl.NumberFormat('id-ID', {
      style: 'currency',
      currency: curr,
      minimumFractionDigits: 0,
    }).format(amount)
  }

  const getStageIcon = (stage: DocumentStreamEvent['stage']) => {
    switch (stage) {
      case 'ocr_started':
      case 'ocr_extracted':
        return <FileText className="w-4 h-4 text-cyan-400 shrink-0" />
      case 'coa_loaded':
        return <FileSpreadsheet className="w-4 h-4 text-blue-400 shrink-0" />
      case 'intake_agent':
      case 'intake_done':
        return <Sparkles className="w-4 h-4 text-purple-400 shrink-0" />
      case 'bookkeeping_done':
      case 'journal_created':
        return <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
      case 'review_queued':
        return <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
      case 'completed':
        return <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
      case 'error':
        return <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
      default:
        return <Activity className="w-4 h-4 text-slate-400 shrink-0" />
    }
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 w-full max-w-xl animate-in fade-in slide-in-from-bottom-5 duration-300">
      <div className="rounded-2xl bg-slate-900/95 border border-slate-700/80 shadow-2xl backdrop-blur-xl overflow-hidden flex flex-col transition-all">
        {/* Header */}
        <div className="p-4 bg-gradient-to-r from-slate-900 via-slate-800 to-indigo-950/60 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="relative">
              <div className="p-2 rounded-xl bg-gradient-to-tr from-indigo-600 to-purple-600 text-white shadow-md shadow-indigo-500/20">
                <Bot className="w-5 h-5" />
              </div>
              {status === 'running' && (
                <span className="absolute -top-0.5 -right-0.5 w-3 h-3 bg-indigo-400 rounded-full animate-ping" />
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-white tracking-tight flex items-center gap-1.5">
                  Document AI Pipeline
                  <span className="text-[11px] font-mono text-purple-300 font-normal">
                    (Gemini 3 Flash)
                  </span>
                </h3>
                {status === 'running' && (
                  <span className="px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 text-[10px] font-bold font-mono flex items-center gap-1">
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
                {filename || 'Uploaded Document'}
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
              <span className="text-slate-400 font-medium">Pipeline Progress:</span>
              <span className="font-bold text-indigo-400 font-mono">{percentage}%</span>
            </div>
            <div className="flex items-center gap-3 text-[11px] font-mono">
              <span className="text-slate-300">
                {extractedData.vendor_name || 'Extracting entities...'}
              </span>
              {extractedData.total_amount != null && (
                <span className="text-emerald-400 font-bold">
                  {formatCurrency(extractedData.total_amount, extractedData.currency)}
                </span>
              )}
            </div>
          </div>
        )}

        {/* Full Interactive Body */}
        {!isMinimized && (
          <div className="p-4 space-y-4 max-h-[70vh] overflow-hidden flex flex-col">
            {/* Live Progress Bar & Pipeline Steps */}
            <div className="space-y-2 bg-slate-950/60 p-3.5 rounded-xl border border-slate-800/80">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400 font-medium flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5 text-indigo-400" />
                  LangGraph Agent Workflow
                </span>
                <span className="font-bold text-white font-mono">{percentage}%</span>
              </div>
              <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-indigo-500 via-purple-500 to-emerald-400 transition-all duration-300"
                  style={{ width: `${percentage}%` }}
                />
              </div>

              {/* Pipeline Step Chips */}
              <div className="grid grid-cols-4 gap-1.5 pt-1 text-center text-[10px] font-medium">
                <div
                  className={`p-1.5 rounded-lg border ${
                    percentage >= 25
                      ? 'bg-cyan-950/40 border-cyan-500/30 text-cyan-300'
                      : 'bg-slate-900/50 border-slate-800 text-slate-500'
                  }`}
                >
                  1. OCR & Text
                </div>
                <div
                  className={`p-1.5 rounded-lg border ${
                    percentage >= 60
                      ? 'bg-purple-950/40 border-purple-500/30 text-purple-300'
                      : 'bg-slate-900/50 border-slate-800 text-slate-500'
                  }`}
                >
                  2. Intake Agent
                </div>
                <div
                  className={`p-1.5 rounded-lg border ${
                    percentage >= 85
                      ? 'bg-blue-950/40 border-blue-500/30 text-blue-300'
                      : 'bg-slate-900/50 border-slate-800 text-slate-500'
                  }`}
                >
                  3. Bookkeeping Agent
                </div>
                <div
                  className={`p-1.5 rounded-lg border ${
                    percentage >= 95
                      ? 'bg-emerald-950/40 border-emerald-500/30 text-emerald-300'
                      : 'bg-slate-900/50 border-slate-800 text-slate-500'
                  }`}
                >
                  4. Guardrails & Save
                </div>
              </div>
            </div>

            {/* Live Extracted Entity Summary Box */}
            {(extractedData.vendor_name || extractedData.total_amount != null) && (
              <div className="p-3 rounded-xl bg-slate-950/80 border border-purple-500/30 grid grid-cols-3 gap-2 animate-in fade-in duration-200">
                <div>
                  <span className="text-[10px] text-slate-400 uppercase font-bold block">
                    Vendor
                  </span>
                  <span className="text-xs font-bold text-white truncate block">
                    {extractedData.vendor_name || '-'}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-slate-400 uppercase font-bold block">
                    Total Amount
                  </span>
                  <span className="text-xs font-bold text-emerald-400 font-mono block">
                    {formatCurrency(extractedData.total_amount, extractedData.currency)}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-slate-400 uppercase font-bold block">
                    Confidence
                  </span>
                  <span className="text-xs font-bold text-purple-300 font-mono block">
                    {extractedData.confidence_score != null
                      ? `${(extractedData.confidence_score * 100).toFixed(0)}%`
                      : '-'}
                  </span>
                </div>
              </div>
            )}

            {/* Live Terminal Log Stream Feed */}
            <div className="space-y-1.5 flex-1 min-h-0 flex flex-col">
              <div className="flex items-center justify-between text-[11px] text-slate-400 font-medium px-1">
                <span className="flex items-center gap-1">
                  <Terminal className="w-3 h-3 text-slate-500" /> Live Execution Stream
                </span>
                <span>{events.length} events</span>
              </div>

              <div className="flex-1 overflow-y-auto max-h-44 rounded-xl bg-slate-950/90 border border-slate-800 p-3 font-mono text-xs space-y-2 scrollbar-thin">
                {events.length === 0 ? (
                  <div className="py-6 text-center text-slate-500 text-[11px] flex items-center justify-center gap-2">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    Connecting to Document Intake stream...
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
                      <span className="text-slate-300 text-[11px] break-words">{evt.message}</span>
                    </div>
                  ))
                )}
                <div ref={logEndRef} />
              </div>
            </div>

            {/* Completion Footer */}
            {status === 'completed' && (
              <div className="p-3.5 rounded-xl bg-emerald-950/60 border border-emerald-500/40 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
                  <div>
                    <p className="text-xs font-bold text-white">Document Processing Complete!</p>
                    <p className="text-[11px] text-emerald-300">
                      Extraction, Bookkeeping, and Guardrails verified.
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={onClose}
                  className="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs shadow-md transition-colors cursor-pointer shrink-0"
                >
                  View Document
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
