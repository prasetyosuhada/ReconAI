import React, { useEffect, useMemo, useState } from 'react'
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileText,
  ImageIcon,
  Loader2,
} from 'lucide-react'
import { API_BASE_URL } from '../../services/api'

type SourceState =
  | { kind: 'missing-id' }
  | { kind: 'loading' }
  | { kind: 'ready'; mimeType: string; objectUrl: string }
  | { kind: 'unavailable' }
  | { kind: 'unsupported' }
  | { kind: 'render-failed' }
  | { kind: 'error' }

interface SourceErrorResponse {
  error?: {
    code?: string
  }
}

interface SourceDocumentViewerProps {
  documentId: string | null
  filename: string
  pageCount: number | null
}

const IMAGE_MIME_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp'])

const getSourceContentUrl = (documentId: string) =>
  `${API_BASE_URL}/documents/${encodeURIComponent(documentId)}/content`

const getErrorState = (response: Response, payload: SourceErrorResponse): SourceState => {
  if (response.status === 410 || payload.error?.code === 'source_content_unavailable') {
    return { kind: 'unavailable' }
  }
  if (response.status === 415 || payload.error?.code === 'unsupported_source_media_type') {
    return { kind: 'unsupported' }
  }
  return { kind: 'error' }
}

export const SourceDocumentViewer: React.FC<SourceDocumentViewerProps> = ({
  documentId,
  filename,
  pageCount,
}) => {
  const [sourceState, setSourceState] = useState<SourceState>(
    documentId ? { kind: 'loading' } : { kind: 'missing-id' }
  )
  const [pdfPage, setPdfPage] = useState(1)
  const contentUrl = useMemo(
    () => (documentId ? getSourceContentUrl(documentId) : null),
    [documentId]
  )

  useEffect(() => {
    if (!contentUrl) {
      setSourceState({ kind: 'missing-id' })
      return
    }

    const controller = new AbortController()
    let active = true
    let objectUrl: string | null = null

    setPdfPage(1)
    setSourceState({ kind: 'loading' })

    const loadSource = async () => {
      try {
        const response = await fetch(contentUrl, { signal: controller.signal })
        if (!response.ok) {
          const payload = (await response.json().catch(() => ({}))) as SourceErrorResponse
          if (active) setSourceState(getErrorState(response, payload))
          return
        }

        const mimeType = (response.headers.get('content-type') || '').split(';')[0].toLowerCase()
        if (mimeType !== 'application/pdf' && !IMAGE_MIME_TYPES.has(mimeType)) {
          if (active) setSourceState({ kind: 'unsupported' })
          return
        }

        const sourceBlob = await response.blob()
        if (!active) return
        objectUrl = URL.createObjectURL(new Blob([sourceBlob], { type: mimeType }))
        setSourceState({ kind: 'ready', mimeType, objectUrl })
      } catch (error: unknown) {
        if (error instanceof DOMException && error.name === 'AbortError') return
        if (active) setSourceState({ kind: 'error' })
      }
    }

    void loadSource()

    return () => {
      active = false
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [contentUrl])

  const isPdf = sourceState.kind === 'ready' && sourceState.mimeType === 'application/pdf'
  const isImage = sourceState.kind === 'ready' && IMAGE_MIME_TYPES.has(sourceState.mimeType)

  const errorCopy =
    sourceState.kind === 'missing-id'
      ? 'No source document is linked to this review item.'
      : sourceState.kind === 'unavailable'
        ? 'The original file is unavailable. Review the extracted fields with the available evidence.'
        : sourceState.kind === 'unsupported'
          ? 'This source file type is not supported for inline review.'
          : sourceState.kind === 'render-failed'
            ? 'Your browser could not render this source file inline. Open the source in a new tab.'
            : 'The source document could not be loaded. Try opening it in a new tab.'

  return (
    <div className="h-full rounded-xl border border-slate-800 bg-slate-950/70 overflow-hidden flex flex-col">
      <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">
            Source Document
          </p>
          <p className="text-xs font-semibold text-slate-200 truncate">{filename}</p>
        </div>
        <FileText className="w-4 h-4 text-indigo-300 shrink-0" aria-hidden="true" />
      </div>

      <div className="flex-1 min-h-[220px] bg-slate-950 flex flex-col">
        {sourceState.kind === 'loading' && (
          <div className="flex-1 flex flex-col items-center justify-center gap-3 px-6 text-center">
            <Loader2 className="w-7 h-7 animate-spin text-indigo-400" aria-hidden="true" />
            <p className="text-sm font-semibold text-slate-200">Loading source document…</p>
          </div>
        )}

        {isPdf && (
          <>
            <iframe
              key={pdfPage}
              src={`${sourceState.objectUrl}#page=${pdfPage}`}
              title={`${filename}, page ${pdfPage}`}
              className="flex-1 min-h-[360px] w-full bg-slate-900"
              onError={() => setSourceState({ kind: 'render-failed' })}
            />
            {pageCount ? (
              <div className="shrink-0 px-3 py-2 border-t border-slate-800 bg-slate-900 flex items-center justify-between gap-2">
                <button
                  type="button"
                  onClick={() => setPdfPage((page) => Math.max(1, page - 1))}
                  disabled={pdfPage === 1}
                  className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
                  aria-label="Show previous PDF page"
                >
                  <ChevronLeft className="w-3.5 h-3.5" aria-hidden="true" />
                  Previous
                </button>
                <span className="text-xs font-semibold text-slate-400" aria-live="polite">
                  Page {pdfPage} of {pageCount}
                </span>
                <button
                  type="button"
                  onClick={() => setPdfPage((page) => Math.min(pageCount, page + 1))}
                  disabled={pdfPage >= pageCount}
                  className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
                  aria-label="Show next PDF page"
                >
                  Next
                  <ChevronRight className="w-3.5 h-3.5" aria-hidden="true" />
                </button>
              </div>
            ) : (
              <p className="shrink-0 px-3 py-2 border-t border-slate-800 bg-slate-900 text-center text-[11px] text-slate-500">
                Use the PDF viewer controls to navigate available pages.
              </p>
            )}
          </>
        )}

        {isImage && (
          <div className="flex-1 min-h-[360px] flex items-center justify-center overflow-auto p-3">
            <img
              src={sourceState.objectUrl}
              alt={`Source document: ${filename}`}
              className="max-h-[560px] max-w-full object-contain"
              onError={() => setSourceState({ kind: 'render-failed' })}
            />
          </div>
        )}

        {['missing-id', 'unavailable', 'unsupported', 'render-failed', 'error'].includes(
          sourceState.kind
        ) && (
          <div className="flex-1 flex flex-col items-center justify-center gap-3 px-6 text-center">
            {sourceState.kind === 'unsupported' ? (
              <ImageIcon className="w-7 h-7 text-amber-300" aria-hidden="true" />
            ) : (
              <AlertCircle className="w-7 h-7 text-amber-300" aria-hidden="true" />
            )}
            <p className="max-w-xs text-sm leading-relaxed text-slate-300">{errorCopy}</p>
          </div>
        )}
      </div>

      {contentUrl && (
        <div className="shrink-0 px-3 py-3 border-t border-slate-800 bg-slate-950/80">
          <a
            href={contentUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold text-indigo-300 border border-slate-700 bg-slate-900 hover:bg-slate-800 transition-colors"
          >
            Open Source
            <ExternalLink className="w-3.5 h-3.5" aria-hidden="true" />
          </a>
        </div>
      )}
    </div>
  )
}
