import React, { useEffect, useState } from 'react'
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  FileCheck,
  FileCode,
  FileText,
  Filter,
  Image as ImageIcon,
  Loader2,
  RefreshCw,
} from 'lucide-react'
import { fetchDocuments } from '../../services/api'
import type { DocumentResponse } from '../../services/api'

interface DocumentListProps {
  refreshTrigger: number
  onSelectDocument?: (docId: string) => void
}

export const DocumentList: React.FC<DocumentListProps> = ({ refreshTrigger, onSelectDocument }) => {
  const [documents, setDocuments] = useState<DocumentResponse[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('')

  const loadDocuments = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetchDocuments({
        status: statusFilter || undefined,
        limit: 50,
      })
      setDocuments(res.items)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load documents'
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadDocuments()
  }, [refreshTrigger, statusFilter])

  const getStatusBadge = (status: string) => {
    switch (status.toLowerCase()) {
      case 'uploaded':
      case 'processing':
      case 'extracting':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-medium animate-pulse">
            <Loader2 className="w-3 h-3 animate-spin" />
            {status}
          </span>
        )
      case 'extracted':
      case 'posted':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-medium">
            <CheckCircle2 className="w-3 h-3" />
            {status}
          </span>
        )
      case 'review_required':
      case 'extraction_review_required':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs font-medium">
            <Clock className="w-3 h-3" />
            Needs Review
          </span>
        )
      case 'rejected':
      case 'failed':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs font-medium">
            <AlertCircle className="w-3 h-3" />
            {status}
          </span>
        )
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-800 border border-slate-700 text-slate-300 text-xs font-medium">
            {status}
          </span>
        )
    }
  }

  const getFileIcon = (mimeType: string) => {
    if (mimeType.includes('image')) {
      return <ImageIcon className="w-4 h-4 text-emerald-400" />
    }
    return <FileText className="w-4 h-4 text-indigo-400" />
  }

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <div className="p-6 rounded-2xl bg-slate-800/40 border border-slate-700/50 shadow-xl backdrop-blur-sm space-y-4 animate-fade-in">
      {/* Header & Filter Controls */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h3 className="text-lg font-bold text-white flex items-center gap-2">
            <FileCheck className="w-5 h-5 text-indigo-400" />
            Uploaded Documents Repository
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            List of ingested invoices and receipts undergoing agentic bookkeeping.
          </p>
        </div>

        <div className="flex items-center gap-3 w-full sm:w-auto">
          {/* Status Filter */}
          <div className="relative flex-1 sm:flex-none">
            <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="w-full sm:w-auto pl-8 pr-8 py-1.5 bg-slate-900/80 border border-slate-700/60 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-indigo-500/50 transition-all appearance-none cursor-pointer"
            >
              <option value="">All Statuses</option>
              <option value="uploaded">Uploaded</option>
              <option value="processing">Processing</option>
              <option value="extracted">Extracted</option>
              <option value="review_required">Review Required</option>
              <option value="posted">Posted</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>

          {/* Refresh Button */}
          <button
            type="button"
            onClick={loadDocuments}
            disabled={loading}
            className="p-2 rounded-xl bg-slate-900/80 hover:bg-slate-800 border border-slate-700/60 text-slate-300 hover:text-white transition-all disabled:opacity-50"
            title="Refresh document list"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
          <span>{error}</span>
        </div>
      )}

      {/* Table Container */}
      <div className="overflow-x-auto rounded-xl border border-slate-800/80 bg-slate-950/40">
        <table className="w-full text-left text-xs text-slate-300">
          <thead className="bg-slate-900/80 text-slate-400 border-b border-slate-800 font-semibold uppercase tracking-wider text-[10px]">
            <tr>
              <th className="py-3 px-4">Filename</th>
              <th className="py-3 px-4">Type</th>
              <th className="py-3 px-4">Status</th>
              <th className="py-3 px-4">Size</th>
              <th className="py-3 px-4">Uploaded At</th>
              <th className="py-3 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 font-medium">
            {loading ? (
              /* Skeleton Loader Rows */
              [1, 2, 3].map((idx) => (
                <tr key={idx} className="animate-pulse">
                  <td className="py-3.5 px-4">
                    <div className="h-4 bg-slate-800/80 rounded w-48" />
                  </td>
                  <td className="py-3.5 px-4">
                    <div className="h-4 bg-slate-800/80 rounded w-16" />
                  </td>
                  <td className="py-3.5 px-4">
                    <div className="h-4 bg-slate-800/80 rounded w-20" />
                  </td>
                  <td className="py-3.5 px-4">
                    <div className="h-4 bg-slate-800/80 rounded w-12" />
                  </td>
                  <td className="py-3.5 px-4">
                    <div className="h-4 bg-slate-800/80 rounded w-28" />
                  </td>
                  <td className="py-3.5 px-4 text-right">
                    <div className="h-6 bg-slate-800/80 rounded w-24 ml-auto" />
                  </td>
                </tr>
              ))
            ) : documents.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-12 text-center text-slate-400 space-y-2">
                  <FileText className="w-10 h-10 text-slate-600 mx-auto" />
                  <p className="text-sm font-semibold text-slate-300">No documents found</p>
                  <p className="text-xs text-slate-500">
                    Upload a receipt or invoice above to get started.
                  </p>
                </td>
              </tr>
            ) : (
              documents.map((doc) => (
                <tr key={doc.id} className="hover:bg-slate-900/60 transition-colors">
                  <td className="py-3.5 px-4">
                    <div className="flex items-center gap-2.5">
                      <div className="p-2 rounded-lg bg-slate-900 border border-slate-800">
                        {getFileIcon(doc.mime_type)}
                      </div>
                      <span className="font-semibold text-slate-100 truncate max-w-xs">
                        {doc.original_filename}
                      </span>
                    </div>
                  </td>

                  <td className="py-3.5 px-4 capitalize">
                    <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700/50">
                      {doc.document_type || 'Unknown'}
                    </span>
                  </td>

                  <td className="py-3.5 px-4">{getStatusBadge(doc.status)}</td>

                  <td className="py-3.5 px-4 text-slate-400 font-mono">
                    {formatFileSize(doc.file_size_bytes)}
                  </td>

                  <td className="py-3.5 px-4 text-slate-400">
                    {new Date(doc.uploaded_at || doc.created_at).toLocaleString()}
                  </td>

                  <td className="py-3.5 px-4 text-right">
                    <button
                      type="button"
                      onClick={() => onSelectDocument?.(doc.id)}
                      className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/40 border border-indigo-500/30 text-indigo-300 text-xs font-semibold transition-all hover:scale-105 active:scale-95"
                    >
                      <FileCode className="w-3.5 h-3.5" />
                      Trace Audit
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
