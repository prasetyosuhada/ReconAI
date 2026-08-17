import React, { useState } from 'react'
import { DropzoneUpload } from './DropzoneUpload'
import { DocumentList } from './DocumentList'
import { DocumentLiveStreamCard } from './DocumentLiveStreamCard'

interface DocumentIntakeViewProps {
  onSelectDocument?: (docId: string) => void
}

export const DocumentIntakeView: React.FC<DocumentIntakeViewProps> = ({ onSelectDocument }) => {
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [streamingDoc, setStreamingDoc] = useState<{ id: string; filename: string } | null>(null)

  const handleUploadSuccess = () => {
    setRefreshTrigger((prev) => prev + 1)
  }

  const handleStartStream = (documentId: string, filename: string) => {
    setStreamingDoc({ id: documentId, filename })
  }

  const handleStreamCompleted = () => {
    setRefreshTrigger((prev) => prev + 1)
  }

  return (
    <div className="space-y-6">
      {/* Upload Dropzone */}
      <DropzoneUpload
        onUploadSuccess={handleUploadSuccess}
        onStartStream={handleStartStream}
      />

      {/* Document List Repository */}
      <DocumentList refreshTrigger={refreshTrigger} onSelectDocument={onSelectDocument} />

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

