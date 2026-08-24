export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export interface ReconciliationStreamEvent {
  stage:
    | 'init'
    | 'candidates_loaded'
    | 'evaluating'
    | 'already_matched'
    | 'exact_match_found'
    | 'agent_invoked'
    | 'agent_match_accepted'
    | 'review_queued'
    | 'unmatched_queued'
    | 'agent_error'
    | 'completed'
    | 'error'
  message: string
  percentage?: number
  current?: number
  total?: number
  matched_count?: number
  proposed_count?: number
  unmatched_count?: number
  tx_id?: string
  description?: string
  amount?: number
  matched_je_id?: string
  confidence?: number
  rationale?: string
}

export interface DocumentStreamEvent {
  stage:
    | 'init'
    | 'ocr_started'
    | 'ocr_extracted'
    | 'coa_loaded'
    | 'intake_agent'
    | 'intake_done'
    | 'bookkeeping_done'
    | 'review_queued'
    | 'journal_created'
    | 'completed'
    | 'error'
  message: string
  percentage?: number
  vendor_name?: string
  total_amount?: number
  currency?: string
  confidence_score?: number
  status?: string
  text_preview?: string
}

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
  id: string
  original_filename: string
  document_type: string
  status: string
  uploaded_at: string
  links?: Record<string, string>
  document?: DocumentResponse
  message?: string
}

export interface DocumentExtractionResponse {
  id: string
  document_id: string
  vendor_name?: string | null
  transaction_date?: string | null
  subtotal_amount?: number | null
  tax_amount?: number | null
  total_amount?: number | null
  currency: string
  line_items?: Record<string, any> | any[] | null
  provider_metadata?: Record<string, any> | null
  confidence_score: number
  rationale?: string | null
  status: string
  created_at: string
  updated_at: string
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

export interface BankStatementImportListResponse {
  items: BankStatementImportResponse[]
  total: number
  limit: number
  offset: number
}

export interface ReconciliationMatchResponse {
  id: string
  bank_transaction_id: string
  journal_entry_id?: string
  status: string // proposed, accepted, rejected, matched
  match_type?: string // exact, fuzzy, manual, unmatched
  confidence_score?: number
  amount_score?: number
  date_score?: number
  vendor_score?: number
  rationale?: string
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

export interface ReconciliationSummaryResponse {
  bank_statement_import_id: string
  statement_period_start?: string
  statement_period_end?: string
  bank_statement_balance: number
  gl_balance: number
  difference: number
  is_balanced: boolean
  status: string
  total_transactions: number
  matched_count: number
  proposed_count: number
  unmatched_count: number
  gl_only_count: number
  progress_percentage: number
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
  rationale?: string
  human_action?: string
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
  document_id?: string | null
  filename?: string | null
  current_status?: string | null
  uploaded_at?: string | null
  timeline: AuditEventResponse[]
  resolved_entity_type?: 'document' | 'journal_entry' | 'bank_transaction' | string | null
  resolved_entity_id?: string | null
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

export async function fetchLatestDocumentExtraction(
  documentId: string
): Promise<DocumentExtractionResponse> {
  const response = await fetch(`${API_BASE_URL}/documents/${documentId}/extractions/latest`)
  if (!response.ok) {
    throw new Error(`Failed to fetch latest extraction for document ${documentId}`)
  }
  return response.json()
}

// Review Items API
export async function fetchReviewItems(params?: {
  status?: string
  review_type?: string
  priority?: string
  search?: string
  limit?: number
  offset?: number
}): Promise<ReviewItemListResponse> {
  const query = new URLSearchParams()
  if (params?.status) query.append('status', params.status)
  if (params?.review_type) query.append('review_type', params.review_type)
  if (params?.priority) query.append('priority', params.priority)
  if (params?.search) query.append('search', params.search)
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

export function notifyReviewQueueUpdated() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('review-queue-updated'))
  }
}

export async function approveReviewItem(
  reviewItemId: string,
  notes?: string
): Promise<{ message: string; review_item_id: string; status: string }> {
  const response = await fetch(`${API_BASE_URL}/review-items/${reviewItemId}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resolution_note: notes || 'Approved via Review Queue UI' }),
  })

  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to approve review item')
  }

  const result = await response.json()
  notifyReviewQueueUpdated()
  return result
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
      resolution_note: notes || 'Edited via Review Detail Modal',
    }),
  })

  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to edit review item')
  }

  const result = await response.json()
  notifyReviewQueueUpdated()
  return result
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

  const result = await response.json()
  notifyReviewQueueUpdated()
  return result
}

// General Ledger API
export async function fetchJournalEntries(params?: {
  status?: string
  document_id?: string
  search?: string
  limit?: number
  offset?: number
}): Promise<JournalEntryListResponse> {
  const query = new URLSearchParams()
  if (params?.status) query.append('status', params.status)
  if (params?.document_id) query.append('document_id', params.document_id)
  if (params?.search) query.append('search', params.search)
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

export interface PostJournalEntryResponse {
  id: string
  status: string
  posted_at: string
  trial_balance_status: string
}

export async function postJournalEntry(
  journalEntryId: string
): Promise<PostJournalEntryResponse> {
  const response = await fetch(
    `${API_BASE_URL}/ledger/journal-entries/${journalEntryId}/post`,
    { method: 'POST' }
  )
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to post journal entry')
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
export async function fetchBankStatementImports(params?: {
  limit?: number
  offset?: number
}): Promise<BankStatementImportListResponse> {
  const query = new URLSearchParams()
  if (params?.limit) query.append('limit', params.limit.toString())
  if (params?.offset) query.append('offset', params.offset.toString())

  const url = `${API_BASE_URL}/bank-statements${query.toString() ? `?${query.toString()}` : ''}`
  const response = await fetch(url)

  if (!response.ok) {
    throw new Error('Failed to fetch bank statement imports')
  }

  return response.json()
}

export async function fetchBankTransactionDetail(
  transactionId: string
): Promise<BankTransactionResponse> {
  const response = await fetch(`${API_BASE_URL}/bank-statements/transactions/${transactionId}`)
  if (!response.ok) {
    throw new Error(`Failed to fetch bank transaction ${transactionId}`)
  }
  return response.json()
}

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
  params?:
    | string
    | {
        search?: string
        status?: string
        bank_statement_import_id?: string
        limit?: number
        offset?: number
      }
): Promise<BankTransactionListResponse> {
  if (typeof params === 'string') {
    const response = await fetch(`${API_BASE_URL}/bank-statements/${params}/transactions`)
    if (!response.ok) {
      throw new Error(`Failed to fetch transactions for import ${params}`)
    }
    return response.json()
  }

  const query = new URLSearchParams()
  if (params?.search) query.append('search', params.search)
  if (params?.status) query.append('status', params.status)
  if (params?.bank_statement_import_id)
    query.append('bank_statement_import_id', params.bank_statement_import_id)
  if (params?.limit) query.append('limit', params.limit.toString())
  if (params?.offset) query.append('offset', params.offset.toString())

  const url = `${API_BASE_URL}/bank-statements/transactions${query.toString() ? `?${query.toString()}` : ''}`
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error('Failed to fetch bank transactions')
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

  const result = await response.json()
  notifyReviewQueueUpdated()
  return result
}

export interface SuggestedJournalLine {
  account_code: string
  account_name: string
  description?: string | null
  debit_amount: number
  credit_amount: number
}

export interface AdjustmentSuggestionResponse {
  bank_transaction_id: string
  transaction_description: string
  transaction_date: string
  transaction_amount: number
  currency: string
  confidence_score: number
  rationale: string
  is_balanced: boolean
  uses_sensitive_account: boolean
  risk_flags: string[]
  suggested_lines: SuggestedJournalLine[]
  agent_name: string
}

export async function suggestAdjustmentJournal(
  bankTransactionId: string
): Promise<AdjustmentSuggestionResponse> {
  const response = await fetch(`${API_BASE_URL}/reconciliation/suggest-adjustment`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bank_transaction_id: bankTransactionId }),
  })

  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to get COA suggestion from BookkeepingAgent')
  }

  return response.json()
}

export interface CreateAdjustmentJournalResponse {
  journal_entry_id: string
  bank_transaction_id: string
  reconciliation_match_id: string
  status: string
  total_debit: number
  total_credit: number
  message: string
}

export async function createAdjustmentJournalEntry(payload: {
  bank_transaction_id: string
  entry_date?: string
  description?: string
  lines?: SuggestedJournalLine[]
}): Promise<CreateAdjustmentJournalResponse> {
  const response = await fetch(`${API_BASE_URL}/reconciliation/create-adjustment`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to create and post adjusting journal entry')
  }

  const result = await response.json()
  notifyReviewQueueUpdated()
  return result
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

export interface ChartOfAccountResponse {
  id: string
  account_code: string
  account_name: string
  account_type: string
  is_active: boolean
  is_sensitive: boolean
}

export interface ChartOfAccountListResponse {
  items: ChartOfAccountResponse[]
  total: number
  limit: number
  offset: number
}

export async function fetchChartOfAccounts(): Promise<ChartOfAccountListResponse> {
  const response = await fetch(`${API_BASE_URL}/ledger/chart-of-accounts?limit=100`)
  if (!response.ok) {
    throw new Error('Failed to fetch chart of accounts')
  }
  return response.json()
}

export async function acceptReconciliationMatch(
  matchId: string,
  note?: string
): Promise<{ id: string; status: string; resolved_at: string; message: string }> {
  const response = await fetch(`${API_BASE_URL}/reconciliation/${matchId}/accept`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resolution_note: note || 'Accepted via Reconciliation UI' }),
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to accept reconciliation match')
  }
  const result = await response.json()
  notifyReviewQueueUpdated()
  return result
}

export async function rejectReconciliationMatch(
  matchId: string,
  note?: string
): Promise<{ id: string; status: string; resolved_at: string; message: string }> {
  const response = await fetch(`${API_BASE_URL}/reconciliation/${matchId}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resolution_note: note || 'Rejected via Reconciliation UI' }),
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to reject reconciliation match')
  }
  const result = await response.json()
  notifyReviewQueueUpdated()
  return result
}

export async function fetchReconciliationSummary(
  importId: string
): Promise<ReconciliationSummaryResponse> {
  const response = await fetch(`${API_BASE_URL}/reconciliation/summary/${importId}`)
  if (!response.ok) {
    throw new Error(`Failed to fetch reconciliation summary for import ${importId}`)
  }
  return response.json()
}

export async function manualMatchReconciliation(
  bankTransactionId: string,
  journalEntryId: string,
  note?: string
): Promise<{ id: string; status: string; resolved_at: string; message: string }> {
  const response = await fetch(`${API_BASE_URL}/reconciliation/manual-match`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      bank_transaction_id: bankTransactionId,
      journal_entry_id: journalEntryId,
      resolution_note: note || 'Manually matched in Reconciliation UI',
    }),
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to manually link match')
  }
  const result = await response.json()
  notifyReviewQueueUpdated()
  return result
}


// Audit Log & Traceability APIs
export async function fetchAuditEvents(params?: {
  source_type?: string
  source_id?: string
  event_type?: string
  actor_type?: string
  start_date?: string
  end_date?: string
  search?: string
  limit?: number
  offset?: number
}): Promise<AuditEventListResponse> {
  const query = new URLSearchParams()
  if (params?.source_type) query.append('source_type', params.source_type)
  if (params?.source_id) query.append('source_id', params.source_id)
  if (params?.event_type) query.append('event_type', params.event_type)
  if (params?.actor_type) query.append('actor_type', params.actor_type)
  if (params?.start_date) query.append('start_date', params.start_date)
  if (params?.end_date) query.append('end_date', params.end_date)
  if (params?.search) query.append('search', params.search)
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

export async function fetchJournalEntryAuditTraceability(
  journalEntryId: string
): Promise<DocumentAuditTraceabilityResponse> {
  const response = await fetch(`${API_BASE_URL}/audit-log/journal-entry/${journalEntryId}`)
  if (!response.ok) {
    throw new Error(`Failed to fetch audit log for journal entry ${journalEntryId}`)
  }
  return response.json()
}

export async function fetchBankTransactionAuditTraceability(
  bankTransactionId: string
): Promise<DocumentAuditTraceabilityResponse> {
  const response = await fetch(`${API_BASE_URL}/audit-log/bank-transaction/${bankTransactionId}`)
  if (!response.ok) {
    throw new Error(`Failed to fetch audit log for bank transaction ${bankTransactionId}`)
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
    pendingReviewCount: reviewData.status === 'fulfilled' ? reviewData.value.total : 0,
    trialBalance: trialBalance.status === 'fulfilled' ? trialBalance.value : null,
  }
}
