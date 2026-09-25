import React from 'react'
import { AlertTriangle, FileText, Info, ShieldAlert } from 'lucide-react'

interface ExtractionReviewContextProps {
  metadata: Record<string, unknown> | null
  fallbackRiskFlags?: string[]
  loading: boolean
}

const EXTRACTION_METHOD_LABELS: Record<string, string> = {
  pdf_text: 'PDF embedded text',
  pdf_vision: 'PDF page vision',
  pdf_hybrid: 'PDF text and vision',
  scanned_pdf_fallback: 'PDF content unavailable',
  image_vision: 'Image vision',
  file_not_found: 'Source file unavailable',
  unsupported: 'Unsupported source',
}

const humanize = (value: string) =>
  value.replace(/_/g, ' ').replace(/\b\w/g, (character) => character.toUpperCase())

const toStringList = (value: unknown): string[] | null => {
  if (!Array.isArray(value)) return null
  return value.filter((item): item is string => typeof item === 'string' && item.length > 0)
}

const toPageList = (value: unknown): number[] | null => {
  if (!Array.isArray(value)) return null
  return [...new Set(value.map(Number).filter((page) => Number.isInteger(page) && page > 0))].sort(
    (first, second) => first - second
  )
}

const toPositiveInteger = (value: unknown): number | null => {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

const ListValue: React.FC<{ items: string[] | number[] | null; emptyLabel: string }> = ({
  items,
  emptyLabel,
}) => {
  if (items === null) return <span className="text-slate-500">Not recorded</span>
  if (items.length === 0) return <span className="text-slate-500">{emptyLabel}</span>
  return <span className="font-mono text-slate-300">{items.join(', ')}</span>
}

export const ExtractionReviewContext: React.FC<ExtractionReviewContextProps> = ({
  metadata,
  fallbackRiskFlags = [],
  loading,
}) => {
  if (loading) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3 text-xs text-slate-500">
        Loading extraction context…
      </div>
    )
  }

  if (!metadata) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3 text-xs text-slate-500 flex gap-2">
        <Info className="w-4 h-4 shrink-0 text-slate-400" aria-hidden="true" />
        <span>Extraction diagnostics are not available for this review item.</span>
      </div>
    )
  }

  const sourcePageCount = toPositiveInteger(metadata.source_page_count)
  const processedPageCount = toPositiveInteger(metadata.processed_page_count)
  const pageLimitApplied = metadata.page_limit_applied === true
  const textPages = toPageList(metadata.text_page_numbers)
  const visionPages = toPageList(metadata.vision_page_numbers)
  const renderedPages = toPageList(metadata.rendered_page_numbers)
  const warnings = toStringList(metadata.warnings)
  const lowConfidenceFields = toStringList(metadata.low_confidence_fields)
  const recordedRiskFlags = toStringList(metadata.risk_flags)
  const riskFlags = recordedRiskFlags ?? (fallbackRiskFlags.length > 0 ? fallbackRiskFlags : null)
  const recordedMethod =
    typeof metadata.extraction_method === 'string' ? metadata.extraction_method : null
  const extractionMethod = recordedMethod
    ? EXTRACTION_METHOD_LABELS[recordedMethod] || humanize(recordedMethod)
    : 'Not recorded'
  const processedPartially =
    pageLimitApplied ||
    (sourcePageCount !== null &&
      processedPageCount !== null &&
      processedPageCount < sourcePageCount) ||
    (riskFlags || []).some((flag) => flag.toLowerCase().includes('partial'))

  const partialMessage =
    sourcePageCount !== null && processedPageCount !== null
      ? `Only ${processedPageCount} of ${sourcePageCount} source pages were processed.`
      : 'Only part of this source document was processed.'

  return (
    <section className="space-y-3" aria-label="Extraction context">
      <div>
        <p className="text-xs font-bold text-indigo-300 uppercase tracking-wider flex items-center gap-2">
          <FileText className="w-4 h-4 text-indigo-400" aria-hidden="true" />
          Extraction Context
        </p>
        <p className="text-xs text-slate-500 mt-1">
          Recorded processing facts from the document intake pipeline.
        </p>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900/80 divide-y divide-slate-800 text-xs">
        <div className="px-3 py-2.5 flex items-center justify-between gap-3">
          <span className="text-slate-500">Method</span>
          <span className="text-right font-semibold text-slate-200">{extractionMethod}</span>
        </div>
        <div className="px-3 py-2.5 flex items-center justify-between gap-3">
          <span className="text-slate-500">Source pages</span>
          <span className="font-mono text-slate-300">{sourcePageCount ?? 'Not recorded'}</span>
        </div>
        <div className="px-3 py-2.5 flex items-center justify-between gap-3">
          <span className="text-slate-500">Processed pages</span>
          <span className="font-mono text-slate-300">{processedPageCount ?? 'Not recorded'}</span>
        </div>
        <div className="px-3 py-2.5 space-y-1">
          <span className="text-slate-500">Text pages</span>
          <div>
            <ListValue items={textPages} emptyLabel="None" />
          </div>
        </div>
        <div className="px-3 py-2.5 space-y-1">
          <span className="text-slate-500">Vision pages</span>
          <div>
            <ListValue items={visionPages} emptyLabel="None" />
          </div>
        </div>
        <div className="px-3 py-2.5 space-y-1">
          <span className="text-slate-500">Rendered pages</span>
          <div>
            <ListValue items={renderedPages} emptyLabel="None" />
          </div>
        </div>
      </div>

      {processedPartially && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-100 flex gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400" aria-hidden="true" />
          <span>{partialMessage}</span>
        </div>
      )}

      <ContextList
        icon={<AlertTriangle className="w-3.5 h-3.5 text-amber-400" aria-hidden="true" />}
        title="Warnings"
        items={warnings}
        emptyLabel="No warnings recorded."
      />
      <ContextList
        icon={<Info className="w-3.5 h-3.5 text-indigo-400" aria-hidden="true" />}
        title="Low-confidence fields"
        items={lowConfidenceFields}
        emptyLabel="No low-confidence fields recorded."
      />
      <ContextList
        icon={<ShieldAlert className="w-3.5 h-3.5 text-amber-400" aria-hidden="true" />}
        title="Risk flags"
        items={riskFlags}
        emptyLabel="No risk flags recorded."
      />
    </section>
  )
}

interface ContextListProps {
  icon: React.ReactNode
  title: string
  items: string[] | null
  emptyLabel: string
}

const ContextList: React.FC<ContextListProps> = ({ icon, title, items, emptyLabel }) => (
  <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3 space-y-2">
    <p className="text-[11px] uppercase tracking-wider font-semibold text-slate-400 flex items-center gap-1.5">
      {icon}
      {title}
    </p>
    {items === null ? (
      <p className="text-xs text-slate-500">Not recorded.</p>
    ) : items.length > 0 ? (
      <ul className="space-y-1.5">
        {items.map((item) => (
          <li key={item} className="text-xs text-slate-300 break-words">
            {humanize(item)}
          </li>
        ))}
      </ul>
    ) : (
      <p className="text-xs text-slate-500">{emptyLabel}</p>
    )}
  </div>
)
