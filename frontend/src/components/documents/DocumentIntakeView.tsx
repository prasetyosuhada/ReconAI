import React, { useState } from 'react'
import { DropzoneUpload } from './DropzoneUpload'
import { DocumentList } from './DocumentList'

interface DocumentIntakeViewProps {
  onSelectDocument?: (docId: string) => void
}

export const DocumentIntakeView: React.FC<DocumentIntakeViewProps> = ({ onSelectDocument }) => {
  const [refreshTrigger, setRefreshTrigger] = useState(0)

  const handleUploadSuccess = () => {
    setRefreshTrigger((prev) => prev + 1)
  }

  return (
    <div className="space-y-6">
      {/* Upload Dropzone */}
      <DropzoneUpload onUploadSuccess={handleUploadSuccess} />

      {/* Document List Repository */}
      <DocumentList refreshTrigger={refreshTrigger} onSelectDocument={onSelectDocument} />
    </div>
  )
}
