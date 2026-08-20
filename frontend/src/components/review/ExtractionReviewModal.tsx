import React, { useEffect, useState } from 'react'
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  CircleDollarSign,
  ClipboardCheck,
  ExternalLink,
  FileText,
  Info,
  Loader2,
  Plus,
  ShieldAlert,
  Sparkles,
  Trash2,
} from 'lucide-react'
import type {
  ChartOfAccountResponse,
  DocumentExtractionResponse,
  JournalLineEditPayload,
  ReviewItemResponse,
} from '../../services/api'
import {
  approveReviewItem,
  editReviewItem,
  fetchChartOfAccounts,
  fetchLatestDocumentExtraction,
  rejectReviewItem,
} from '../../services/api'

interface ExtractionReviewModalProps {
  item: ReviewItemResponse | null
  onClose: () => void
  onResolved: () => void
}

interface ExtractionDraftPayload {
  document_type: string
  transaction_date: string
  vendor_name: string
  payment_status: string
  currency: string
  subtotal_amount: string
  tax_amount: string
  total_amount: string
  line_items: Record<string, any>[]
}

export const ExtractionReviewModal: React.FC<ExtractionReviewModalProps> = ({
  item,
  onClose,
  onResolved,
}) => {
  const [latestExtraction, setLatestExtraction] = useState<DocumentExtractionResponse | null>(null)
  const [extractionLoading, setExtractionLoading] = useState<boolean>(false)
  const [dbCOA, setDbCOA] = useState<ChartOfAccountResponse[]>([])

  useEffect(() => {
    fetchChartOfAccounts()
      .then((res) => {
        if (res.items && res.items.length > 0) {
          setDbCOA(res.items)
        }
      })
      .catch((err) => {
        console.error('Failed to fetch COA from database:', err)
      })
  }, [])

  // Extraction payload states
  const originalPayload = item?.original_payload || {}
  const dbExtractionPayload: Record<string, any> = latestExtraction
    ? {
        ...latestExtraction,
        invoice_date: latestExtraction.transaction_date,
      }
    : {}
  const extractionPayload: Record<string, any> = {
    ...originalPayload,
    ...dbExtractionPayload,
  }
  const extractedVendor = extractionPayload.vendor_name || extractionPayload.merchant_name || 'N/A'
  const extractedDate = extractionPayload.invoice_date || extractionPayload.transaction_date || ''
  const extractedTotal = extractionPayload.total_amount || extractionPayload.amount || 0
  const extractedTax = extractionPayload.tax_amount || 0
  const extractedSubtotal =
    extractionPayload.subtotal_amount ||
    Math.max(Number(extractedTotal || 0) - Number(extractedTax || 0), 0)
  const extractedCurrency = extractionPayload.currency || 'IDR'
  const extractedRationale = extractionPayload.rationale || ''
  const documentType = extractionPayload.document_type || 'Invoice / Receipt'
  const sourceFilename =
    extractionPayload.original_filename ||
    extractionPayload.filename ||
    extractionPayload.document_filename ||
    item?.title?.replace(/^Review Needed:\s*/i, '') ||
    'Source document'
  const sourcePath =
    extractionPayload.document_url ||
    extractionPayload.source_url ||
    extractionPayload.file_url ||
    extractionPayload.stored_file_path ||
    ''
  const paymentStatus =
    originalPayload.payment_status ||
    originalPayload.payment_status_label ||
    (Number(extractedTotal) > 0 ? 'paid' : 'unknown')
  const rawLineItems = extractionPayload.line_items || extractionPayload.items
  const lineItems = Array.isArray(rawLineItems)
    ? rawLineItems
    : Array.isArray(rawLineItems?.items)
      ? rawLineItems.items
      : Array.isArray(rawLineItems?.line_items)
        ? rawLineItems.line_items
        : []
  const warnings =
    (Array.isArray(extractionPayload.warnings) && extractionPayload.warnings) ||
    (Array.isArray(item?.risk_flags) && item?.risk_flags) ||
    []
  const isExtractionReview = item?.review_type === 'extraction'

  // Editable Journal Entry States
  const defaultLines: JournalLineEditPayload[] = item?.edited_payload?.lines ||
    originalPayload.lines ||
    originalPayload.journal_lines || [
      {
        account_code: '5100',
        account_name: 'Office Supplies Expense',
        debit_amount: Number(extractedTotal) || 0,
        credit_amount: 0,
        description: `Expense: ${extractedVendor}`,
      },
      {
        account_code: '1010',
        account_name: 'Bank Account',
        debit_amount: 0,
        credit_amount: Number(extractedTotal) || 0,
        description: `Payment to ${extractedVendor}`,
      },
    ]

  const [entryDate, setEntryDate] = useState<string>(
    item?.edited_payload?.entry_date || extractedDate || new Date().toISOString().split('T')[0]
  )
  const [description, setDescription] = useState<string>(
    item?.edited_payload?.description || item?.title || `Journal for ${extractedVendor}`
  )
  const [lines, setLines] = useState<JournalLineEditPayload[]>(defaultLines)
  const [rejectionReason, setRejectionReason] = useState<string>('')
  const [showRejectInput, setShowRejectInput] = useState<boolean>(false)
  const [isEditing, setIsEditing] = useState<boolean>(false)
  const [extractionDraft, setExtractionDraft] = useState<ExtractionDraftPayload>({
    document_type: 'invoice',
    transaction_date: '',
    vendor_name: '',
    payment_status: 'unknown',
    currency: 'IDR',
    subtotal_amount: '',
    tax_amount: '',
    total_amount: '',
    line_items: [],
  })

  const [submitting, setSubmitting] = useState<boolean>(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  useEffect(() => {
    let ignore = false
    const documentId =
      originalPayload.document_id ||
      originalPayload.source_document_id ||
      (item?.source_type === 'document' ? item.source_id : undefined)

    setLatestExtraction(null)
    if (!documentId) {
      setExtractionLoading(false)
      return
    }

    setExtractionLoading(true)
    fetchLatestDocumentExtraction(String(documentId))
      .then((extraction) => {
        if (!ignore) {
          setLatestExtraction(extraction)
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          console.warn('Failed to load latest document extraction:', err)
        }
      })
      .finally(() => {
        if (!ignore) {
          setExtractionLoading(false)
        }
      })

    return () => {
      ignore = true
    }
  }, [item])

  useEffect(() => {
    setErrorMsg(null)
  }, [lines, entryDate, description])

  useEffect(() => {
    if (!item) return

    const payloadLines =
      item.edited_payload?.lines || originalPayload.lines || originalPayload.journal_lines
    setEntryDate(
      item.edited_payload?.entry_date || extractedDate || new Date().toISOString().split('T')[0]
    )
    setDescription(
      item.edited_payload?.description || item.title || `Journal for ${extractedVendor}`
    )
    setLines(
      payloadLines || [
        {
          account_code: '5100',
          account_name: 'Office Supplies Expense',
          debit_amount: Number(extractedTotal) || 0,
          credit_amount: 0,
          description: `Expense: ${extractedVendor}`,
        },
        {
          account_code: '1010',
          account_name: 'Bank Account',
          debit_amount: 0,
          credit_amount: Number(extractedTotal) || 0,
          description: `Payment to ${extractedVendor}`,
        },
      ]
    )
    setExtractionDraft({
      document_type:
        item.edited_payload?.document_type ||
        extractionPayload.document_type ||
        originalPayload.document_type ||
        'invoice',
      transaction_date:
        item.edited_payload?.transaction_date ||
        item.edited_payload?.invoice_date ||
        extractedDate ||
        '',
      vendor_name:
        item.edited_payload?.vendor_name ||
        extractionPayload.vendor_name ||
        extractionPayload.merchant_name ||
        '',
      payment_status:
        item.edited_payload?.payment_status ||
        extractionPayload.payment_status ||
        originalPayload.payment_status ||
        'unknown',
      currency: item.edited_payload?.currency || extractedCurrency || 'IDR',
      subtotal_amount: String(item.edited_payload?.subtotal_amount ?? extractedSubtotal ?? ''),
      tax_amount: String(item.edited_payload?.tax_amount ?? extractedTax ?? ''),
      total_amount: String(item.edited_payload?.total_amount ?? extractedTotal ?? ''),
      line_items: item.edited_payload?.line_items || lineItems,
    })
  }, [item, latestExtraction])

  if (!item) return null

  // Balance calculation
  const totalDebits = lines.reduce((acc, l) => acc + (Number(l.debit_amount) || 0), 0)
  const totalCredits = lines.reduce((acc, l) => acc + (Number(l.credit_amount) || 0), 0)
  const balanceDiff = Math.abs(totalDebits - totalCredits)
  const isBalanced = balanceDiff < 0.01

  const handleLineChange = (
    index: number,
    field: keyof JournalLineEditPayload,
    value: string | number
  ) => {
    const updated = [...lines]
    updated[index] = {
      ...updated[index],
      [field]: field === 'debit_amount' || field === 'credit_amount' ? Number(value) || 0 : value,
    }
    setLines(updated)
  }

  const handleAddLine = () => {
    const defaultAcct =
      dbCOA.find((c) => c.account_type === 'expense') ||
      dbCOA[0] || {
        account_code: '5900',
        account_name: 'Miscellaneous Expense',
      }
    setLines([
      ...lines,
      {
        account_code: defaultAcct.account_code,
        account_name: defaultAcct.account_name,
        debit_amount: 0,
        credit_amount: 0,
        description: '',
      },
    ])
  }

  const handleRemoveLine = (index: number) => {
    if (lines.length <= 2) {
      alert('A valid journal entry must contain at least 2 lines (Double-Entry).')
      return
    }
    setLines(lines.filter((_, i) => i !== index))
  }

  const handleExtractionFieldChange = (field: keyof ExtractionDraftPayload, value: string) => {
    setExtractionDraft((draft) => ({ ...draft, [field]: value }))
  }

  const handleExtractionLineChange = (index: number, field: string, value: string) => {
    setExtractionDraft((draft) => {
      const updatedLines = [...draft.line_items]
      updatedLines[index] = {
        ...updatedLines[index],
        [field]:
          field === 'quantity' || field === 'unit_price' || field === 'amount'
            ? value === ''
              ? null
              : Number(value)
            : value,
      }
      return { ...draft, line_items: updatedLines }
    })
  }

  const handleAddExtractionLine = () => {
    setExtractionDraft((draft) => ({
      ...draft,
      line_items: [
        ...draft.line_items,
        {
          description: '',
          quantity: 1,
          unit_price: 0,
          amount: 0,
        },
      ],
    }))
  }

  const handleRemoveExtractionLine = (index: number) => {
    setExtractionDraft((draft) => ({
      ...draft,
      line_items: draft.line_items.filter((_, i) => i !== index),
    }))
  }

  const handleApproveAsIs = async () => {
    setSubmitting(true)
    setErrorMsg(null)
    try {
      await approveReviewItem(item.id, 'Approved as-is via Review Detail Modal')
      onResolved()
      onClose()
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to approve item')
    } finally {
      setSubmitting(false)
    }
  }

  const handleSaveAndApprove = async () => {
    if (isExtractionReview) {
      const toNumberOrNull = (value: string) => (value === '' ? null : Number(value))
      const editedPayload = {
        document_type: extractionDraft.document_type,
        vendor_name: extractionDraft.vendor_name || null,
        transaction_date: extractionDraft.transaction_date || null,
        invoice_date: extractionDraft.transaction_date || null,
        subtotal_amount: toNumberOrNull(extractionDraft.subtotal_amount),
        tax_amount: toNumberOrNull(extractionDraft.tax_amount),
        total_amount: toNumberOrNull(extractionDraft.total_amount),
        currency: extractionDraft.currency || 'IDR',
        payment_status: extractionDraft.payment_status || 'unknown',
        line_items: extractionDraft.line_items,
      }

      setSubmitting(true)
      setErrorMsg(null)
      try {
        await editReviewItem(
          item.id,
          editedPayload,
          'Corrected extracted fields via Review Detail Modal'
        )
        onResolved()
        onClose()
      } catch (err: unknown) {
        setErrorMsg(err instanceof Error ? err.message : 'Failed to save extracted fields')
      } finally {
        setSubmitting(false)
      }
      return
    }

    if (!isBalanced) {
      setErrorMsg(
        `Double-entry unbalanced! Debits (${totalDebits.toLocaleString()}) must equal Credits (${totalCredits.toLocaleString()}).`
      )
      return
    }

    setSubmitting(true)
    setErrorMsg(null)

    const editedPayload = {
      entry_date: entryDate,
      description,
      lines,
    }

    try {
      await editReviewItem(item.id, editedPayload, 'Edited and approved via Review Detail Modal')
      onResolved()
      onClose()
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to save edited entry')
    } finally {
      setSubmitting(false)
    }
  }

  const handleReject = async () => {
    if (!rejectionReason.trim()) {
      alert('Please provide a reason for rejecting this item.')
      return
    }

    setSubmitting(true)
    setErrorMsg(null)
    try {
      await rejectReviewItem(item.id, rejectionReason)
      onResolved()
      onClose()
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to reject item')
    } finally {
      setSubmitting(false)
    }
  }

  const confPercent = Math.round(
    Number(latestExtraction?.confidence_score ?? item.confidence_score ?? 0) * 100
  )
  const arithmeticOk =
    Number(extractedSubtotal) > 0 && Number(extractedTotal) > 0
      ? Math.abs(Number(extractedSubtotal) + Number(extractedTax || 0) - Number(extractedTotal)) <
        0.05
      : isBalanced
  const taxOk = Number(extractedTax || 0) >= 0
  const paymentOk = String(paymentStatus).toLowerCase() === 'paid'
  const statusText = item.status === 'pending' ? 'Needs Review' : item.status.replace('_', ' ')
  const statusTone =
    item.status === 'pending'
      ? 'bg-amber-500/10 text-amber-300 border-amber-500/20'
      : item.status === 'posted'
        ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20'
        : 'bg-slate-800 text-slate-300 border-slate-700'

  const formatMoney = (value: unknown) =>
    `${extractedCurrency} ${Number(value || 0).toLocaleString('id-ID')}`

  const labelize = (value: string) =>
    value
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (char) => char.toUpperCase())
      .trim()

  const getLineDescription = (line: Record<string, any>, index: number) =>
    line.description || line.name || line.item || line.account_name || `Line item ${index + 1}`

  const getLineAmount = (line: Record<string, any>) =>
    line.amount ?? line.total ?? line.line_total ?? line.debit_amount ?? line.credit_amount ?? 0

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-md flex items-center justify-center p-3 sm:p-4 overflow-y-auto">
      <div className="relative max-w-7xl w-full max-h-[94vh] bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col my-auto">
        {/* Header */}
        <div className="px-4 sm:px-6 py-4 bg-slate-950/90 border-b border-slate-800 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              onClick={onClose}
              className="p-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white transition-all shrink-0"
              title="Back to documents"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div className="min-w-0">
              <p className="text-[11px] uppercase tracking-wider text-slate-500 font-bold">
                Documents
              </p>
              <h3 className="text-base sm:text-lg font-bold text-white truncate">
                {sourceFilename}
              </h3>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 sm:justify-end">
            <span
              className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-xs font-bold capitalize ${statusTone}`}
            >
              <span className="w-2 h-2 rounded-full bg-current" />
              {statusText}
            </span>
            <span className="px-2.5 py-1 rounded-lg text-[11px] font-bold bg-slate-800/80 text-slate-300 border border-slate-700 uppercase tracking-wider">
              {item.priority} Priority
            </span>
          </div>
        </div>

        {/* Modal Scrollable Body */}
        <div className="flex-1 overflow-y-auto">
          <div className="grid grid-cols-1 xl:grid-cols-[minmax(220px,0.9fr)_minmax(420px,1.55fr)_minmax(260px,0.95fr)]">
            {/* Left Column: Source Document */}
            <section className="min-h-[280px] xl:min-h-[620px] border-b xl:border-b-0 xl:border-r border-slate-800 bg-slate-950/40 p-4 sm:p-5">
              <div className="h-full rounded-xl border border-slate-800 bg-slate-950/70 overflow-hidden flex flex-col">
                <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">
                      Source Document
                    </p>
                    <p className="text-xs font-semibold text-slate-200 truncate">
                      {sourceFilename}
                    </p>
                  </div>
                  <FileText className="w-4 h-4 text-indigo-300 shrink-0" />
                </div>
                <div className="flex-1 p-4 flex flex-col items-center justify-center text-center">
                  <div className="w-full max-w-[210px] aspect-[3/4] rounded-lg bg-slate-100 text-slate-900 shadow-xl shadow-black/30 border border-slate-700 overflow-hidden flex flex-col">
                    <div className="h-8 bg-slate-200 border-b border-slate-300 flex items-center px-3 gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-rose-400" />
                      <span className="w-2 h-2 rounded-full bg-amber-400" />
                      <span className="w-2 h-2 rounded-full bg-emerald-400" />
                    </div>
                    <div className="flex-1 p-4 text-left space-y-3">
                      <div className="h-3 w-2/3 bg-slate-800 rounded" />
                      <div className="space-y-1.5">
                        <div className="h-2 w-full bg-slate-300 rounded" />
                        <div className="h-2 w-5/6 bg-slate-300 rounded" />
                        <div className="h-2 w-4/6 bg-slate-300 rounded" />
                      </div>
                      <div className="mt-5 space-y-2">
                        <div className="flex justify-between gap-3">
                          <div className="h-2 w-20 bg-slate-300 rounded" />
                          <div className="h-2 w-12 bg-slate-400 rounded" />
                        </div>
                        <div className="flex justify-between gap-3">
                          <div className="h-2 w-16 bg-slate-300 rounded" />
                          <div className="h-2 w-14 bg-slate-400 rounded" />
                        </div>
                      </div>
                      <div className="pt-4 mt-4 border-t border-slate-300 flex justify-between">
                        <div className="h-2.5 w-12 bg-slate-700 rounded" />
                        <div className="h-2.5 w-16 bg-slate-700 rounded" />
                      </div>
                    </div>
                  </div>

                  <p className="text-xs text-slate-400 mt-4 max-w-[260px]">
                    Original document preview is displayed as a reference while the reviewer verifies
                    extracted fields.
                  </p>

                  {sourcePath && (
                    <a
                      href={sourcePath}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 text-xs font-semibold text-indigo-300 transition-all"
                    >
                      Open Source
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  )}
                </div>
              </div>
            </section>

            {/* Middle Column: Extracted Information */}
            <section className="border-b xl:border-b-0 xl:border-r border-slate-800 bg-slate-900 p-4 sm:p-6">
              <div className="flex items-center justify-between gap-4 mb-6">
                <div>
                  <p className="text-xs font-bold text-indigo-300 uppercase tracking-wider flex items-center gap-2">
                    <ClipboardCheck className="w-4 h-4 text-indigo-400" />
                    Extracted Information
                  </p>
                  <p className="text-xs text-slate-500 mt-1">
                    {extractionLoading
                      ? 'Loading latest extraction results...'
                      : 'AI extraction results requiring verification before proceeding.'}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setIsEditing((value) => !value)}
                  className="px-3 py-1.5 rounded-lg bg-slate-950 hover:bg-slate-800 border border-slate-700 text-slate-200 text-xs font-semibold transition-all"
                >
                  {isEditing ? 'Hide Editor' : 'Edit Fields'}
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-5">
                <div className="space-y-1">
                  <span className="text-[11px] text-slate-500 font-semibold uppercase tracking-wider">
                    Document Type
                  </span>
                  {isEditing && isExtractionReview ? (
                    <select
                      value={extractionDraft.document_type}
                      onChange={(e) => handleExtractionFieldChange('document_type', e.target.value)}
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm font-semibold text-slate-100 focus:outline-none focus:border-indigo-500"
                    >
                      <option value="invoice">Invoice</option>
                      <option value="receipt">Receipt</option>
                      <option value="unknown">Unknown</option>
                    </select>
                  ) : (
                    <p className="text-sm font-semibold text-slate-100 capitalize">
                      {labelize(String(documentType))}
                    </p>
                  )}
                </div>
                <div className="space-y-1">
                  <span className="text-[11px] text-slate-500 font-semibold uppercase tracking-wider">
                    Invoice Date
                  </span>
                  {isEditing && isExtractionReview ? (
                    <input
                      type="date"
                      value={extractionDraft.transaction_date}
                      onChange={(e) =>
                        handleExtractionFieldChange('transaction_date', e.target.value)
                      }
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm font-semibold text-slate-100 focus:outline-none focus:border-indigo-500"
                    />
                  ) : (
                    <p className="text-sm font-semibold text-slate-100">{extractedDate || 'N/A'}</p>
                  )}
                </div>
                <div className="space-y-1 sm:col-span-2">
                  <span className="text-[11px] text-slate-500 font-semibold uppercase tracking-wider">
                    Vendor
                  </span>
                  {isEditing && isExtractionReview ? (
                    <input
                      type="text"
                      value={extractionDraft.vendor_name}
                      onChange={(e) => handleExtractionFieldChange('vendor_name', e.target.value)}
                      placeholder="Vendor name"
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-base font-bold text-white focus:outline-none focus:border-indigo-500"
                    />
                  ) : (
                    <p className="text-base font-bold text-white">{extractedVendor}</p>
                  )}
                </div>
                <div>
                  <span className="block text-[11px] text-slate-500 font-semibold uppercase tracking-wider">
                    Payment Status
                  </span>
                  {isEditing && isExtractionReview ? (
                    <select
                      value={extractionDraft.payment_status}
                      onChange={(e) =>
                        handleExtractionFieldChange('payment_status', e.target.value)
                      }
                      className="mt-1 w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm font-bold text-slate-100 focus:outline-none focus:border-indigo-500"
                    >
                      <option value="unknown">Unknown</option>
                      <option value="paid">Paid</option>
                      <option value="unpaid">Unpaid</option>
                    </select>
                  ) : (
                    <p
                      className={`mt-1.5 flex items-center gap-2 text-sm font-bold capitalize ${
                        paymentOk ? 'text-emerald-300' : 'text-amber-300'
                      }`}
                    >
                      <span
                        className={`w-3 h-3 rounded-full ${
                          paymentOk ? 'bg-emerald-400' : 'bg-amber-400'
                        }`}
                      />
                      {labelize(String(paymentStatus))}
                    </p>
                  )}
                </div>
                <div className="space-y-1">
                  <span className="text-[11px] text-slate-500 font-semibold uppercase tracking-wider">
                    Currency
                  </span>
                  {isEditing && isExtractionReview ? (
                    <input
                      type="text"
                      value={extractionDraft.currency}
                      onChange={(e) =>
                        handleExtractionFieldChange('currency', e.target.value.toUpperCase())
                      }
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm font-semibold text-slate-100 focus:outline-none focus:border-indigo-500"
                    />
                  ) : (
                    <p className="text-sm font-semibold text-slate-100">{extractedCurrency}</p>
                  )}
                </div>
              </div>

              <div className="mt-8 space-y-3">
                <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider">
                  Line Items
                </h4>
                <div className="rounded-xl border border-slate-800 bg-slate-950/50 overflow-hidden">
                  {isEditing && isExtractionReview ? (
                    <div className="divide-y divide-slate-800/80">
                      {extractionDraft.line_items.map((line, index) => (
                        <div
                          key={`editable-line-${index}`}
                          className="px-4 py-3 grid grid-cols-1 sm:grid-cols-[minmax(0,1.5fr)_70px_110px_110px_36px] gap-2"
                        >
                          <input
                            type="text"
                            value={line.description || line.name || line.item || ''}
                            onChange={(e) =>
                              handleExtractionLineChange(index, 'description', e.target.value)
                            }
                            placeholder="Description"
                            className="px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-100 focus:outline-none focus:border-indigo-500"
                          />
                          <input
                            type="number"
                            step="any"
                            value={line.quantity ?? ''}
                            onChange={(e) =>
                              handleExtractionLineChange(index, 'quantity', e.target.value)
                            }
                            placeholder="Qty"
                            className="px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-100 focus:outline-none focus:border-indigo-500"
                          />
                          <input
                            type="number"
                            step="any"
                            value={line.unit_price ?? ''}
                            onChange={(e) =>
                              handleExtractionLineChange(index, 'unit_price', e.target.value)
                            }
                            placeholder="Unit price"
                            className="px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-100 focus:outline-none focus:border-indigo-500"
                          />
                          <input
                            type="number"
                            step="any"
                            value={line.amount ?? ''}
                            onChange={(e) =>
                              handleExtractionLineChange(index, 'amount', e.target.value)
                            }
                            placeholder="Amount"
                            className="px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-100 focus:outline-none focus:border-indigo-500"
                          />
                          <button
                            type="button"
                            onClick={() => handleRemoveExtractionLine(index)}
                            className="p-2 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
                            title="Delete line item"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ))}
                      <div className="px-4 py-3">
                        <button
                          type="button"
                          onClick={handleAddExtractionLine}
                          className="px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-300 text-xs font-semibold inline-flex items-center gap-1 transition-all"
                        >
                          <Plus className="w-3.5 h-3.5" />
                          Add Line Item
                        </button>
                      </div>
                    </div>
                  ) : lineItems.length > 0 ? (
                    <div className="divide-y divide-slate-800/80">
                      {lineItems.map((line: Record<string, any>, index: number) => (
                        <div
                          key={`${getLineDescription(line, index)}-${index}`}
                          className="px-4 py-3 flex items-start justify-between gap-4 text-sm"
                        >
                          <div className="min-w-0">
                            <p className="font-medium text-slate-100 truncate">
                              {getLineDescription(line, index)}
                            </p>
                            {(line.quantity || line.unit_price) && (
                              <p className="text-[11px] text-slate-500 mt-0.5">
                                Qty {line.quantity || '-'} x {formatMoney(line.unit_price || 0)}
                              </p>
                            )}
                          </div>
                          <span className="font-mono text-slate-200 shrink-0">
                            {formatMoney(getLineAmount(line))}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="px-4 py-5 text-xs text-slate-500">
                      No structured line items in payload. Reviewer can still validate or add items
                      in the editor.
                    </div>
                  )}
                </div>
              </div>

              <div className="mt-6 ml-auto w-full sm:max-w-sm space-y-2 text-sm">
                <div className="flex items-center justify-between text-slate-400">
                  <span>Subtotal</span>
                  {isEditing && isExtractionReview ? (
                    <input
                      type="number"
                      step="any"
                      value={extractionDraft.subtotal_amount}
                      onChange={(e) =>
                        handleExtractionFieldChange('subtotal_amount', e.target.value)
                      }
                      className="w-40 px-3 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-right font-mono text-slate-100 focus:outline-none focus:border-indigo-500"
                    />
                  ) : (
                    <span className="font-mono text-slate-200">
                      {formatMoney(extractedSubtotal)}
                    </span>
                  )}
                </div>
                <div className="flex items-center justify-between text-slate-400">
                  <span>Tax</span>
                  {isEditing && isExtractionReview ? (
                    <input
                      type="number"
                      step="any"
                      value={extractionDraft.tax_amount}
                      onChange={(e) => handleExtractionFieldChange('tax_amount', e.target.value)}
                      className="w-40 px-3 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-right font-mono text-slate-100 focus:outline-none focus:border-indigo-500"
                    />
                  ) : (
                    <span className="font-mono text-slate-200">{formatMoney(extractedTax)}</span>
                  )}
                </div>
                <div className="border-t border-slate-700 pt-3 flex items-center justify-between">
                  <span className="font-bold text-white uppercase tracking-wide">Total</span>
                  {isEditing && isExtractionReview ? (
                    <input
                      type="number"
                      step="any"
                      value={extractionDraft.total_amount}
                      onChange={(e) => handleExtractionFieldChange('total_amount', e.target.value)}
                      className="w-40 px-3 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-right font-mono text-lg font-bold text-emerald-300 focus:outline-none focus:border-indigo-500"
                    />
                  ) : (
                    <span className="font-mono text-lg font-bold text-emerald-300">
                      {formatMoney(extractedTotal)}
                    </span>
                  )}
                </div>
              </div>

              {isEditing && !isExtractionReview && (
                <div className="mt-6 p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-4">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-bold text-indigo-300 uppercase tracking-wider flex items-center gap-1.5">
                      <FileText className="w-4 h-4 text-indigo-400" />
                      Editable Journal Entry Payload
                    </h4>
                    <span
                      className={`px-2.5 py-0.5 rounded-full border text-[11px] font-bold flex items-center gap-1 ${
                        isBalanced
                          ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
                          : 'bg-rose-500/10 border-rose-500/20 text-rose-400'
                      }`}
                    >
                      {isBalanced ? (
                        <CheckCircle2 className="w-3 h-3" />
                      ) : (
                        <AlertTriangle className="w-3 h-3" />
                      )}
                      {isBalanced ? 'Balanced' : `Delta ${balanceDiff.toLocaleString()}`}
                    </span>
                  </div>

                  {/* Form Controls: Date & Description */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div>
                      <label className="block text-[11px] font-semibold text-slate-400 mb-1">
                        Entry Date
                      </label>
                      <input
                        type="date"
                        value={entryDate}
                        onChange={(e) => setEntryDate(e.target.value)}
                        className="w-full px-3 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-100 focus:outline-none focus:border-indigo-500"
                      />
                    </div>
                    <div className="sm:col-span-2">
                      <label className="block text-[11px] font-semibold text-slate-400 mb-1">
                        Journal Description / Memo
                      </label>
                      <input
                        type="text"
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        className="w-full px-3 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-100 focus:outline-none focus:border-indigo-500"
                      />
                    </div>
                  </div>

                  {/* Lines Table */}
                  <div className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-900/60">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-950 text-slate-400 border-b border-slate-800 font-semibold uppercase text-[10px]">
                        <tr>
                          <th className="py-2.5 px-3 w-56">Account (COA)</th>
                          <th className="py-2.5 px-3">Line Memo</th>
                          <th className="py-2.5 px-3 text-right w-36">Debit ({extractedCurrency})</th>
                          <th className="py-2.5 px-3 text-right w-36">Credit ({extractedCurrency})</th>
                          <th className="py-2.5 px-3 text-center w-12">Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/80">
                        {lines.map((line, idx) => (
                          <tr key={idx} className="hover:bg-slate-900 transition-colors">
                            <td className="py-2 px-3">
                              <select
                                value={line.account_code}
                                onChange={(e) => {
                                  const newCode = e.target.value
                                  const found = dbCOA.find((c) => c.account_code === newCode)
                                  handleLineChange(idx, 'account_code', newCode)
                                  if (found) {
                                    handleLineChange(idx, 'account_name', found.account_name)
                                  }
                                }}
                                className="w-full px-2 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-100 focus:outline-none focus:border-indigo-500 transition-colors"
                              >
                                <option value="" disabled>Select COA Account...</option>
                                {dbCOA.map((coa) => (
                                  <option key={coa.account_code} value={coa.account_code}>
                                    [{coa.account_code}] {coa.account_name} ({coa.account_type})
                                  </option>
                                ))}
                              </select>
                            </td>
                            <td className="py-2 px-3">
                              <input
                                type="text"
                                value={line.description || ''}
                                onChange={(e) =>
                                  handleLineChange(idx, 'description', e.target.value)
                                }
                                placeholder="Line memo"
                                className="w-full px-2 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-100 focus:outline-none focus:border-indigo-500"
                              />
                            </td>
                            <td className="py-2 px-3">
                              <input
                                type="number"
                                step="any"
                                value={line.debit_amount || ''}
                                onChange={(e) =>
                                  handleLineChange(idx, 'debit_amount', e.target.value)
                                }
                                className="w-full px-2 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-emerald-400 font-bold text-right font-mono focus:outline-none focus:border-indigo-500"
                              />
                            </td>
                            <td className="py-2 px-3">
                              <input
                                type="number"
                                step="any"
                                value={line.credit_amount || ''}
                                onChange={(e) =>
                                  handleLineChange(idx, 'credit_amount', e.target.value)
                                }
                                className="w-full px-2 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-indigo-400 font-bold text-right font-mono focus:outline-none focus:border-indigo-500"
                              />
                            </td>
                            <td className="py-2 px-3 text-center">
                              <button
                                type="button"
                                onClick={() => handleRemoveLine(idx)}
                                disabled={lines.length <= 2}
                                className="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                                title={lines.length <= 2 ? 'Minimum 2 lines required' : 'Delete line'}
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Add Line & Balance Summary */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
                    <button
                      type="button"
                      onClick={handleAddLine}
                      className="px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-300 text-xs font-semibold flex items-center gap-1 transition-all w-fit"
                    >
                      <Plus className="w-3.5 h-3.5" /> Add Line Item
                    </button>

                    <div className="flex flex-wrap items-center gap-4 text-xs font-mono">
                      <div>
                        <span className="text-slate-500">Debits: </span>
                        <span className="font-bold text-emerald-400">
                          {totalDebits.toLocaleString()}
                        </span>
                      </div>
                      <div>
                        <span className="text-slate-500">Credits: </span>
                        <span className="font-bold text-indigo-400">
                          {totalCredits.toLocaleString()}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </section>

            {/* Right Column: AI Insights */}
            <section className="bg-slate-950/55 p-4 sm:p-5">
              <div className="space-y-6">
                <div>
                  <p className="text-xs font-bold text-indigo-300 uppercase tracking-wider flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-indigo-400" />
                    AI Insights
                  </p>
                  <p className="text-xs text-slate-500 mt-1">
                    Automated validation signals and items requiring attention.
                  </p>
                </div>

                <div className="space-y-2">
                  <div className="flex items-end justify-between gap-3">
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                      AI Confidence
                    </span>
                    <span className="text-lg font-bold text-white">{confPercent}%</span>
                  </div>
                  <div className="w-full bg-slate-800 h-2.5 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        confPercent >= 85
                          ? 'bg-emerald-400'
                          : confPercent >= 70
                            ? 'bg-amber-400'
                            : 'bg-rose-400'
                      }`}
                      style={{ width: `${confPercent}%` }}
                    />
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="flex items-start gap-3 text-sm">
                    <CheckCircle2
                      className={`w-4 h-4 mt-0.5 shrink-0 ${
                        arithmeticOk ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    />
                    <div>
                      <p className="font-semibold text-slate-100">Arithmetic Check</p>
                      <p className="text-xs text-slate-500">
                        {arithmeticOk
                          ? 'Subtotal + tax matches total.'
                          : 'Total needs manual check.'}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-start gap-3 text-sm">
                    <CheckCircle2
                      className={`w-4 h-4 mt-0.5 shrink-0 ${
                        taxOk ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    />
                    <div>
                      <p className="font-semibold text-slate-100">Tax Check</p>
                      <p className="text-xs text-slate-500">
                        {taxOk ? 'Tax amount is readable.' : 'Tax field needs review.'}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-start gap-3 text-sm">
                    <CircleDollarSign
                      className={`w-4 h-4 mt-0.5 shrink-0 ${
                        paymentOk ? 'text-emerald-400' : 'text-amber-400'
                      }`}
                    />
                    <div>
                      <p className="font-semibold text-slate-100">Payment Status</p>
                      <p className="text-xs text-slate-500">
                        {paymentOk
                          ? 'Marked as paid from extracted data.'
                          : 'Payment status is uncertain.'}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-start gap-3 text-sm">
                    <ShieldAlert
                      className={`w-4 h-4 mt-0.5 shrink-0 ${
                        warnings.length > 0 ? 'text-amber-400' : 'text-emerald-400'
                      }`}
                    />
                    <div>
                      <p className="font-semibold text-slate-100">Guardrail Flags</p>
                      <p className="text-xs text-slate-500">
                        {warnings.length > 0
                          ? `${warnings.length} item needs attention.`
                          : 'No guardrail flags detected.'}
                      </p>
                    </div>
                  </div>
                </div>

                {warnings.length > 0 && (
                  <div className="rounded-xl bg-amber-500/10 border border-amber-500/20 p-3 space-y-2">
                    {warnings.map((flag: string) => (
                      <div key={flag} className="flex items-start gap-2 text-xs text-amber-200">
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-400 mt-0.5 shrink-0" />
                        <span>{labelize(String(flag))}</span>
                      </div>
                    ))}
                  </div>
                )}

                {extractedRationale && (
                  <div className="text-xs text-indigo-300 bg-indigo-500/10 p-3 rounded-xl border border-indigo-500/20 flex items-start gap-2">
                    <Sparkles className="w-4 h-4 shrink-0 text-indigo-400 mt-0.5" />
                    <span>{extractedRationale}</span>
                  </div>
                )}

                <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-3 text-xs text-slate-300 leading-relaxed">
                  <div className="flex items-start gap-2">
                    <Info className="w-4 h-4 text-indigo-400 mt-0.5 shrink-0" />
                    <span>{item.suggested_action || 'No AI suggested action.'}</span>
                  </div>
                </div>
              </div>
            </section>
          </div>
        </div>

        {/* Error Banner inside Modal */}
        {errorMsg && (
          <div className="px-6 py-2.5 bg-rose-500/10 border-t border-rose-500/20 text-rose-300 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* Footer Action Bar */}
        <div className="px-4 sm:px-6 py-4 bg-slate-950/90 border-t border-slate-800 flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-4">
          <p className="text-xs text-slate-400 max-w-xl">
            AI extracted this document. Review highlighted fields, then confirm or edit before
            proceeding to the next workflow stage.
          </p>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
            {showRejectInput ? (
              <div className="flex items-center gap-2 w-full sm:w-auto">
                <input
                  type="text"
                  placeholder="e.g. Blurry scan, illegible amounts..."
                  value={rejectionReason}
                  onChange={(e) => setRejectionReason(e.target.value)}
                  className="min-w-0 flex-1 sm:w-64 px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-100 focus:outline-none focus:border-rose-500"
                />
                <button
                  type="button"
                  onClick={handleReject}
                  disabled={submitting}
                  className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-semibold text-xs transition-all flex items-center gap-1 whitespace-nowrap"
                >
                  {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  Reject
                </button>
                <button
                  type="button"
                  onClick={() => setShowRejectInput(false)}
                  className="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 text-xs"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setShowRejectInput(true)}
                className="px-4 py-2 rounded-xl bg-rose-600/10 hover:bg-rose-600/20 border border-rose-500/20 text-rose-300 font-semibold text-xs transition-all"
              >
                Reject Item
              </button>
            )}

            <button
              type="button"
              onClick={() => setIsEditing((value) => !value)}
              className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 font-semibold text-xs transition-all"
            >
              {isEditing ? 'Review Summary' : 'Edit Fields'}
            </button>

            <button
              type="button"
              onClick={isEditing ? handleSaveAndApprove : handleApproveAsIs}
              disabled={submitting || (isEditing && !isExtractionReview && !isBalanced)}
              className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs transition-all shadow-lg shadow-emerald-600/20 flex items-center justify-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <CheckCircle2 className="w-3.5 h-3.5" />
              )}
              {isEditing
                ? isExtractionReview
                  ? 'Save Fields & Continue'
                  : 'Save Edits & Post'
                : 'Confirm Extraction'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
