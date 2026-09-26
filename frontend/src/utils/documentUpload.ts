export const MAX_DOCUMENT_UPLOAD_BYTES = 10 * 1024 * 1024
export const DOCUMENT_UPLOAD_ACCEPT = '.pdf,.png,.jpg,.jpeg,.webp'

const ALLOWED_MIME_TYPES = new Set([
  'application/pdf',
  'image/png',
  'image/jpeg',
  'image/jpg',
  'image/webp',
])

// Match the API's MIME-or-extension admission policy. Content validation stays server-side.
export function validateDocumentUpload(file: Pick<File, 'name' | 'type' | 'size'>): string | null {
  if (!ALLOWED_MIME_TYPES.has(file.type) && !/\.(pdf|png|jpe?g|webp)$/i.test(file.name)) {
    return 'Only PDF, PNG, JPEG, and WebP files are supported.'
  }
  if (file.size > MAX_DOCUMENT_UPLOAD_BYTES) {
    return 'File size exceeds maximum limit of 10 MB.'
  }
  if (file.size === 0) {
    return 'The selected file is empty.'
  }
  return null
}
