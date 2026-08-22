import React, { useEffect, useState } from 'react'
import { AlertCircle, FileText, Filter, History, Loader2, RefreshCw, Search } from 'lucide-react'
import { AuditTimeline } from './AuditTimeline'
import { AuditStatusStrip } from './AuditStatusStrip'
import { AuditLifecycleStepper } from './AuditLifecycleStepper'
import type {
  AuditEventResponse,
  DocumentAuditTraceabilityResponse,
  DocumentResponse,
} from '../../services/api'
import {
  fetchAuditEvents,
  fetchDocumentAuditTraceability,
  fetchDocuments,
} from '../../services/api'

export const AuditTraceabilityView: React.FC = () => {
  const [documents, setDocuments] = useState<DocumentResponse[]>([])
  const [selectedDocId, setSelectedDocId] = useState<string>('')
  const [docAudit, setDocAudit] = useState<DocumentAuditTraceabilityResponse | null>(null)
  const [allEvents, setAllEvents] = useState<AuditEventResponse[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [highlightedEventId, setHighlightedEventId] = useState<string | null>(null)

  const [actorFilter, setActorFilter] = useState<string>('')
  const [eventTypeFilter, setEventTypeFilter] = useState<string>('')

  // Load available documents for selector
  useEffect(() => {
    const loadDocList = async () => {
      try {
        const res = await fetchDocuments({ limit: 50 })
        setDocuments(res.items)
        if (res.items.length > 0 && !selectedDocId) {
          setSelectedDocId(res.items[0].id)
        }
      } catch (err: unknown) {
        console.error('Failed to fetch document list for audit selector:', err)
      }
    }
    loadDocList()
  }, [])

  // Load audit data
  const loadAuditData = async () => {
    setLoading(true)
    setError(null)
    try {
      if (selectedDocId) {
        const res = await fetchDocumentAuditTraceability(selectedDocId)
        setDocAudit(res)
      } else {
        const res = await fetchAuditEvents({
          actor_type: actorFilter || undefined,
          event_type: eventTypeFilter || undefined,
          limit: 50,
        })
        setAllEvents(res.items)
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch audit log')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAuditData()
  }, [selectedDocId, actorFilter, eventTypeFilter])

  const displayedEvents = selectedDocId ? docAudit?.timeline || [] : allEvents

  const filteredEvents = displayedEvents.filter((evt) => {
    if (actorFilter && evt.actor_type.toLowerCase() !== actorFilter.toLowerCase()) return false
    if (eventTypeFilter && !evt.event_type.toLowerCase().includes(eventTypeFilter.toLowerCase()))
      return false
    return true
  })

  const handleSelectTransitionEvent = (eventId: string) => {
    setHighlightedEventId(eventId)
    const el = document.getElementById(`audit-event-${eventId}`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
    setTimeout(() => {
      setHighlightedEventId((prev) => (prev === eventId ? null : prev))
    }, 3000)
  }

  return (
    <div className="space-y-6">
      {/* Header & Filter Controls Card */}
      <div className="p-6 rounded-2xl bg-slate-800/40 border border-slate-700/50 shadow-xl backdrop-blur-sm space-y-4">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
              <History className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white flex items-center gap-2">
                Audit Trail & End-to-End Traceability
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Complete chronological record of document intake, OCR extractions, LLM rationale,
                and human approvals.
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={loadAuditData}
            disabled={loading}
            className="p-2.5 rounded-xl bg-slate-900/80 hover:bg-slate-800 border border-slate-700/60 text-slate-300 hover:text-white transition-all disabled:opacity-50 cursor-pointer"
            title="Refresh audit timeline"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {/* Filter Toolbar */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2">
          {/* Document Selector */}
          <div>
            <label className="block text-[11px] font-semibold text-slate-400 mb-1">
              Trace Document Timeline
            </label>
            <div className="relative">
              <FileText className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
              <select
                value={selectedDocId}
                onChange={(e) => setSelectedDocId(e.target.value)}
                className="w-full pl-9 pr-8 py-2 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-slate-100 focus:outline-none focus:border-indigo-500 appearance-none cursor-pointer"
              >
                <option value="">View All System Audit Events</option>
                {documents.map((d) => (
                  <option key={d.id} value={d.id}>
                    📄 {d.original_filename} ({d.status})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Actor Filter */}
          <div>
            <label className="block text-[11px] font-semibold text-slate-400 mb-1">
              Actor Type
            </label>
            <div className="relative">
              <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
              <select
                value={actorFilter}
                onChange={(e) => setActorFilter(e.target.value)}
                className="w-full pl-9 pr-8 py-2 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-slate-100 focus:outline-none focus:border-indigo-500 appearance-none cursor-pointer"
              >
                <option value="">All Actors (Agent, Human, System)</option>
                <option value="agent">AI Agents</option>
                <option value="human">Human Reviewers</option>
                <option value="system">System Engine</option>
              </select>
            </div>
          </div>

          {/* Search Event Type */}
          <div>
            <label className="block text-[11px] font-semibold text-slate-400 mb-1">
              Search Event Type
            </label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
              <input
                type="text"
                placeholder="e.g. extraction, bookkeeping..."
                value={eventTypeFilter}
                onChange={(e) => setEventTypeFilter(e.target.value)}
                className="w-full pl-9 pr-3 py-2 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              />
            </div>
          </div>
        </div>

        {/* Selected Document Info Banner */}
        {selectedDocId && docAudit && (
          <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
            <div>
              <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-wider block">
                Source Document Audit Context
              </span>
              <p className="font-bold text-slate-100 text-sm">{docAudit.filename}</p>
              <p className="text-slate-400 font-mono text-[11px] mt-0.5">
                ID: {docAudit.document_id}
              </p>
            </div>

            <div className="flex items-center gap-3">
              <div className="text-right">
                <span className="text-slate-400 text-[11px] block">Current Status</span>
                <span className="font-bold text-emerald-400 uppercase">
                  {docAudit.current_status}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Accounting Pipeline Lifecycle Stepper (§5.1) */}
        {selectedDocId && displayedEvents.length > 0 && (
          <AuditLifecycleStepper
            events={displayedEvents}
            onSelectEvent={handleSelectTransitionEvent}
            activeEventId={highlightedEventId}
          />
        )}

        {/* Status Transition History Strip (§5.4) */}
        {selectedDocId && displayedEvents.length > 0 && (
          <AuditStatusStrip
            events={displayedEvents}
            onSelectEvent={handleSelectTransitionEvent}
            activeEventId={highlightedEventId}
          />
        )}
      </div>

      {/* Main Timeline Card */}
      <div className="p-6 rounded-2xl bg-slate-800/40 border border-slate-700/50 shadow-xl backdrop-blur-sm space-y-4">
        {error && (
          <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {loading ? (
          <div className="py-16 text-center text-slate-400 space-y-2">
            <Loader2 className="w-8 h-8 animate-spin text-indigo-400 mx-auto" />
            <p className="text-xs">Building chronological audit timeline...</p>
          </div>
        ) : filteredEvents.length === 0 ? (
          <div className="py-16 text-center text-slate-400 space-y-2 bg-slate-900/40 rounded-xl border border-slate-800">
            <History className="w-10 h-10 text-slate-600 mx-auto" />
            <p className="text-sm font-semibold text-slate-300">No Audit Events Found</p>
            <p className="text-xs text-slate-500">
              No audit log matches your current document and filter selection.
            </p>
          </div>
        ) : (
          <AuditTimeline events={filteredEvents} highlightedEventId={highlightedEventId} />
        )}
      </div>
    </div>
  )
}
