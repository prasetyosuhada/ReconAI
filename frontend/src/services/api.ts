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
