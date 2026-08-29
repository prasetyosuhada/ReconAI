import React, { useCallback, useEffect, useState } from 'react'
import { DropzoneUpload } from './DropzoneUpload'
import { DocumentList } from './DocumentList'
import { DocumentLiveStreamCard } from './DocumentLiveStreamCard'
import type { DocumentResponse } from '../../services/api'
import { fetchDocuments, notifyReviewQueueUpdated } from '../../services/api'

interface DocumentIntakeViewProps {
  onSelectDocument?: (docId: string) => void
}

export const DocumentIntakeView: React.FC<DocumentIntakeViewProps> = ({ onSelectDocument }) => {
  const [documents, setDocuments] = useState<DocumentResponse[]>([])
  const [total, setTotal] = useState<number>(0)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [page, setPage] = useState<number>(1)
  const [pageSize, setPageSize] = useState<number>(10)
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [streamingDoc, setStreamingDoc] = useState<{ id: string; filename: string } | null>(null)

  const loadDocuments = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetchDocuments({
        status: statusFilter || undefined,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      })
      setDocuments(res.items)
      setTotal(res.total)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load documents'
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [statusFilter, page, pageSize])

  useEffect(() => {
    loadDocuments()
  }, [loadDocuments, refreshTrigger])

  const handleUploadSuccess = () => {
    setRefreshTrigger((prev) => prev + 1)
  }

  const handleStartStream = (documentId: string, filename: string) => {
    setStreamingDoc({ id: documentId, filename })
  }

  const handleStreamCompleted = useCallback(() => {
    setRefreshTrigger((prev) => prev + 1)
    notifyReviewQueueUpdated()
  }, [])

  const handleStatusFilterChange = (newStatus: string) => {
    setStatusFilter(newStatus)
    setPage(1)
  }

  return (
    <div className="space-y-6">
      {/* Upload Dropzone */}
      <DropzoneUpload onUploadSuccess={handleUploadSuccess} onStartStream={handleStartStream} />

      {/* Document List Repository with Pagination */}
      <DocumentList
        documents={documents}
        total={total}
        loading={loading}
        error={error}
        statusFilter={statusFilter}
        onStatusFilterChange={handleStatusFilterChange}
        page={page}
        pageSize={pageSize}
        onPageChange={setPage}
        onPageSizeChange={(newSize) => {
          setPageSize(newSize)
          setPage(1)
        }}
        onRefresh={loadDocuments}
        onSelectDocument={onSelectDocument}
      />

      {/* Real-time SSE Document AI Pipeline Execution Stream Card */}
      <DocumentLiveStreamCard
        documentId={streamingDoc?.id || ''}
        filename={streamingDoc?.filename}
        isOpen={Boolean(streamingDoc)}
        onClose={() => setStreamingDoc(null)}
        onCompleted={handleStreamCompleted}
      />
    </div>
  )
}
