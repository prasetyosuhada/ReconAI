const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export interface DocumentResponse {
  id: string
  original_filename: string
  stored_file_path: string
  mime_type: string
  file_size_bytes: number
  document_type: string
  status: string
  uploaded_at: string
  created_at: string
  updated_at: string
}

export interface DocumentListResponse {
  items: DocumentResponse[]
  total: number
  limit: number
  offset: number
}

export interface DocumentUploadResponse {
  document: DocumentResponse
  message: string
  status: string
}

// Review Item Interfaces
export interface JournalLineEditPayload {
  account_code: string
  account_name?: string
  debit_amount: number
  credit_amount: number
  description?: string
}

export interface ReviewItemResponse {
  id: string
  review_type: string // extraction, bookkeeping, reconciliation, validation
  status: string // pending, posted, rejected
  priority: string // high, normal, low
  source_type: string
  source_id: string
  title: string
  summary: string
  suggested_action?: string
  original_payload?: Record<string, any>
  edited_payload?: Record<string, any>
  confidence_score?: number
  risk_flags?: string[]
  reviewed_by?: string
  reviewed_at?: string
  created_at: string
  updated_at: string
}

export interface ReviewItemListResponse {
  items: ReviewItemResponse[]
  total: number
  limit: number
  offset: number
}

// Ledger & Trial Balance Interfaces
export interface JournalLineResponse {
  id: string
  line_number: number
  account_id: string
  account_code: string
  account_name: string
  debit_amount: number
  credit_amount: number
  description?: string
}

export interface JournalEntryResponse {
  id: string
  document_id?: string
  extraction_id?: string
  entry_date: string
  description: string
  status: string // draft, review_required, approved, posted, rejected
  agent_name?: string
  confidence_score?: number
  rationale?: string
  risk_flags?: string[]
  total_debit: number
  total_credit: number
  posted_at?: string
  created_at: string
  updated_at?: string
  lines?: JournalLineResponse[]
}

export interface JournalEntryListResponse {
  items: JournalEntryResponse[]
  total: number
  limit: number
  offset: number
}

export interface TrialBalanceAccountBalance {
  account_code: string
  account_name: string
  account_type: string
  debit_balance: number
  credit_balance: number
}

export interface TrialBalanceResponse {
  as_of_date: string
  status: string // balanced, unbalanced
  total_debits: number
  total_credits: number
  difference: number
  accounts: TrialBalanceAccountBalance[]
}

// Bank & Reconciliation Interfaces
export interface BankTransactionResponse {
  id: string
  bank_statement_import_id: string
  transaction_date: string
  description: string
  amount: number
  currency: string
  reference_number?: string
  status: string // imported, matched, unmatched
  created_at: string
}

export interface BankTransactionListResponse {
  items: BankTransactionResponse[]
  total: number
  limit: number
  offset: number
}

export interface BankStatementImportResponse {
  id: string
  original_filename: string
  status: string
  row_count: number
  imported_at: string
  links?: Record<string, string>
}

export interface ReconciliationMatchResponse {
  id: string
  bank_transaction_id: string
  journal_entry_id?: string
  status: string // proposed, accepted, rejected
  confidence_score?: number
  match_rule_type?: string
  match_explanation?: string
  matched_at?: string
  bank_transaction?: BankTransactionResponse
  journal_entry?: JournalEntryResponse
}

export interface ReconciliationMatchListResponse {
  items: ReconciliationMatchResponse[]
  total: number
  limit: number
  offset: number
}

// Audit Trail & Traceability Interfaces
export interface AuditEventResponse {
  id: string
  event_type: string
  source_type: string
  source_id: string
  actor_type: string // agent, human, system
  actor_name: string
  confidence_score?: number
  input_snapshot?: Record<string, any>
  output_snapshot?: Record<string, any>
  created_at: string
}

export interface AuditEventListResponse {
  items: AuditEventResponse[]
  total: number
  limit: number
  offset: number
}

export interface DocumentAuditTraceabilityResponse {
  document_id: string
  filename: string
  current_status: string
  uploaded_at: string
  timeline: AuditEventResponse[]
}

export async function uploadDocument(file: File): Promise<DocumentUploadResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${API_BASE_URL}/documents/upload`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || 'Failed to upload document')
  }

  return response.json()
}

export async function fetchDocuments(params?: {
  status?: string
  limit?: number
  offset?: number
}): Promise<DocumentListResponse> {
  const query = new URLSearchParams()
  if (params?.status) query.append('status', params.status)
  if (params?.limit) query.append('limit', params.limit.toString())
  if (params?.offset) query.append('offset', params.offset.toString())

  const url = `${API_BASE_URL}/documents${query.toString() ? `?${query.toString()}` : ''}`
  const response = await fetch(url)

  if (!response.ok) {
    throw new Error('Failed to fetch document list')
  }

  return response.json()
}

// Review Items API
export async function fetchReviewItems(params?: {
  status?: string
  review_type?: string
  limit?: number
  offset?: number
}): Promise<ReviewItemListResponse> {
  const query = new URLSearchParams()
  if (params?.status) query.append('status', params.status)
  if (params?.review_type) query.append('review_type', params.review_type)
  if (params?.limit) query.append('limit', params.limit.toString())
  if (params?.offset) query.append('offset', params.offset.toString())

  const url = `${API_BASE_URL}/review-items${query.toString() ? `?${query.toString()}` : ''}`
  const response = await fetch(url)

  if (!response.ok) {
    throw new Error('Failed to fetch review items')
  }

  return response.json()
}

export async function fetchReviewItemDetail(reviewItemId: string): Promise<ReviewItemResponse> {
  const response = await fetch(`${API_BASE_URL}/review-items/${reviewItemId}`)
  if (!response.ok) {
    throw new Error(`Failed to fetch review item ${reviewItemId}`)
  }
  return response.json()
}

export async function approveReviewItem(
  reviewItemId: string,
  notes?: string
): Promise<{ message: string; review_item_id: string; status: string }> {
  const response = await fetch(`${API_BASE_URL}/review-items/${reviewItemId}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reviewer_notes: notes || 'Approved via Review Queue UI' }),
  })

  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to approve review item')
  }

  return response.json()
}

export async function editReviewItem(
  reviewItemId: string,
  editedPayload: Record<string, any>,
  notes?: string
): Promise<{ message: string; review_item_id: string; status: string }> {
  const response = await fetch(`${API_BASE_URL}/review-items/${reviewItemId}/edit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      edited_payload: editedPayload,
      reviewer_notes: notes || 'Edited via Review Detail Modal',
    }),
  })

  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to edit review item')
  }

  return response.json()
}

export async function rejectReviewItem(
  reviewItemId: string,
  reason?: string
): Promise<{ message: string; review_item_id: string; status: string }> {
  const response = await fetch(`${API_BASE_URL}/review-items/${reviewItemId}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rejection_reason: reason || 'Rejected via Review Queue UI' }),
  })

  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to reject review item')
  }

  return response.json()
}

// General Ledger API
export async function fetchJournalEntries(params?: {
  status?: string
  document_id?: string
  limit?: number
  offset?: number
}): Promise<JournalEntryListResponse> {
  const query = new URLSearchParams()
  if (params?.status) query.append('status', params.status)
  if (params?.document_id) query.append('document_id', params.document_id)
  if (params?.limit) query.append('limit', params.limit.toString())
  if (params?.offset) query.append('offset', params.offset.toString())

  const url = `${API_BASE_URL}/ledger${query.toString() ? `?${query.toString()}` : ''}`
  const response = await fetch(url)

  if (!response.ok) {
    throw new Error('Failed to fetch journal entries')
  }

  return response.json()
}

export async function fetchJournalEntryDetail(
  journalEntryId: string
): Promise<JournalEntryResponse> {
  const response = await fetch(`${API_BASE_URL}/ledger/journal-entries/${journalEntryId}`)
  if (!response.ok) {
    throw new Error(`Failed to fetch journal entry ${journalEntryId}`)
  }
  return response.json()
}

export async function fetchTrialBalance(asOfDate?: string): Promise<TrialBalanceResponse> {
  const query = new URLSearchParams()
  if (asOfDate) query.append('as_of_date', asOfDate)

  const url = `${API_BASE_URL}/ledger/trial-balance${query.toString() ? `?${query.toString()}` : ''}`
  const response = await fetch(url)

  if (!response.ok) {
    throw new Error('Failed to fetch trial balance')
  }

  return response.json()
}

// Bank Statement & Reconciliation APIs
export async function uploadBankStatementCSV(file: File): Promise<BankStatementImportResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${API_BASE_URL}/bank/upload-mock`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || 'Failed to upload bank statement CSV')
  }

  return response.json()
}

export async function fetchBankTransactions(
  importId: string
): Promise<BankTransactionListResponse> {
  const response = await fetch(`${API_BASE_URL}/bank-statements/${importId}/transactions`)
  if (!response.ok) {
    throw new Error(`Failed to fetch transactions for import ${importId}`)
  }
  return response.json()
}

export async function runReconciliationWorkflow(
  importId: string
): Promise<{ bank_statement_import_id: string; status: string; message: string }> {
  const response = await fetch(`${API_BASE_URL}/reconcile/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bank_statement_import_id: importId }),
  })

  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to run reconciliation workflow')
  }

  return response.json()
}

export async function fetchReconciliationMatches(params?: {
  bank_statement_import_id?: string
  status?: string
}): Promise<ReconciliationMatchListResponse> {
  const query = new URLSearchParams()
  if (params?.bank_statement_import_id)
    query.append('bank_statement_import_id', params.bank_statement_import_id)
  if (params?.status) query.append('status', params.status)

  const url = `${API_BASE_URL}/reconciliation/matches${query.toString() ? `?${query.toString()}` : ''}`
  const response = await fetch(url)

  if (!response.ok) {
    throw new Error('Failed to fetch reconciliation matches')
  }

  return response.json()
}

// Audit Log & Traceability APIs
export async function fetchAuditEvents(params?: {
  source_type?: string
  source_id?: string
  event_type?: string
  actor_type?: string
  limit?: number
  offset?: number
}): Promise<AuditEventListResponse> {
  const query = new URLSearchParams()
  if (params?.source_type) query.append('source_type', params.source_type)
  if (params?.source_id) query.append('source_id', params.source_id)
  if (params?.event_type) query.append('event_type', params.event_type)
  if (params?.actor_type) query.append('actor_type', params.actor_type)
  if (params?.limit) query.append('limit', params.limit.toString())
  if (params?.offset) query.append('offset', params.offset.toString())

  const url = `${API_BASE_URL}/audit-events${query.toString() ? `?${query.toString()}` : ''}`
  const response = await fetch(url)

  if (!response.ok) {
    throw new Error('Failed to fetch audit events')
  }

  return response.json()
}

export async function fetchDocumentAuditTraceability(
  documentId: string
): Promise<DocumentAuditTraceabilityResponse> {
  const response = await fetch(`${API_BASE_URL}/audit-log/${documentId}`)
  if (!response.ok) {
    throw new Error(`Failed to fetch audit log for document ${documentId}`)
  }
  return response.json()
}

// ─── Dashboard Stats ──────────────────────────────────────────────────────────

export interface DashboardStats {
  totalDocuments: number
  pendingReviewCount: number
  trialBalance: TrialBalanceResponse | null
}

export async function fetchDashboardStats(): Promise<DashboardStats> {
  const [docsData, reviewData, trialBalance] = await Promise.allSettled([
    fetchDocuments({ limit: 1 }),
    fetchReviewItems({ status: 'pending', limit: 1 }),
    fetchTrialBalance(),
  ])

  return {
    totalDocuments: docsData.status === 'fulfilled' ? docsData.value.total : 0,
    pendingReviewCount:
      reviewData.status === 'fulfilled' ? reviewData.value.total : 0,
    trialBalance:
      trialBalance.status === 'fulfilled' ? trialBalance.value : null,
  }
}
