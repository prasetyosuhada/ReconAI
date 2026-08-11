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
