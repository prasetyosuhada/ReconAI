import React, { useRef, useState } from 'react'
import { AlertCircle, CheckCircle2, FileText, Loader2, UploadCloud, X } from 'lucide-react'
import { uploadDocument } from '../../services/api'

interface DropzoneUploadProps {
  onUploadSuccess: () => void
}

export const DropzoneUpload: React.FC<DropzoneUploadProps> = ({ onUploadSuccess }) => {
  const [isDragging, setIsDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)

  const validateFile = (file: File): boolean => {
    setErrorMsg(null)
    setSuccessMsg(null)

    const allowedTypes = ['application/pdf', 'image/png', 'image/jpeg', 'image/jpg']
    if (!allowedTypes.includes(file.type)) {
      setErrorMsg('Only PDF, PNG, and JPEG files are supported.')
      return false
    }

    const maxSize = 15 * 1024 * 1024 // 15MB
    if (file.size > maxSize) {
      setErrorMsg('File size exceeds maximum limit of 15MB.')
      return false
    }

    return true
  }

  const handleFileSelect = (file: File) => {
    if (validateFile(file)) {
      setSelectedFile(file)
    }
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelect(e.dataTransfer.files[0])
    }
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFileSelect(e.target.files[0])
    }
  }

  const handleUploadSubmit = async () => {
    if (!selectedFile) return

    setUploading(true)
    setErrorMsg(null)
    setSuccessMsg(null)

    try {
      const res = await uploadDocument(selectedFile)
      setSuccessMsg(
        `Document "${res.document.original_filename}" uploaded successfully! AI extraction pipeline triggered.`
      )
      setSelectedFile(null)
      onUploadSuccess()
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Upload failed. Please try again.'
      setErrorMsg(message)
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="p-6 rounded-2xl bg-slate-800/40 border border-slate-700/50 shadow-xl backdrop-blur-sm space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-bold text-white flex items-center gap-2">
            <UploadCloud className="w-5 h-5 text-indigo-400" />
            Document Intake & OCR Upload
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Upload receipt or invoice (PDF, PNG, JPEG) to start automated extraction.
          </p>
        </div>
        <span className="text-[11px] font-semibold text-indigo-400 bg-indigo-500/10 px-2.5 py-1 rounded-full border border-indigo-500/20">
          Max 15MB
        </span>
      </div>

      {/* Drag & Drop Area */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !uploading && fileInputRef.current?.click()}
        className={`relative cursor-pointer rounded-xl border-2 border-dashed p-8 text-center transition-all duration-200 ${
          isDragging
            ? 'border-indigo-500 bg-indigo-500/10 shadow-lg shadow-indigo-500/10 scale-[1.01]'
            : selectedFile
              ? 'border-indigo-500/50 bg-slate-900/60'
              : 'border-slate-700 hover:border-slate-500 bg-slate-900/40 hover:bg-slate-900/60'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg"
          className="hidden"
          onChange={handleInputChange}
          disabled={uploading}
        />

        {selectedFile ? (
          <div className="flex flex-col items-center justify-center space-y-3">
            <div className="p-3 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
              <FileText className="w-8 h-8" />
            </div>
            <div>
              <p className="text-sm font-semibold text-white">{selectedFile.name}</p>
              <p className="text-xs text-slate-400">
                {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB • Ready for processing
              </p>
            </div>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                setSelectedFile(null)
              }}
              className="inline-flex items-center gap-1 text-xs text-rose-400 hover:text-rose-300 font-medium px-2 py-1 rounded bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 transition-all"
            >
              <X className="w-3.5 h-3.5" /> Remove file
            </button>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center space-y-3">
            <div className="p-3 rounded-full bg-slate-800 text-slate-400 border border-slate-700">
              <UploadCloud className="w-8 h-8 text-indigo-400" />
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-200">
                Drag and drop your file here, or{' '}
                <span className="text-indigo-400 underline underline-offset-2">browse</span>
              </p>
              <p className="text-xs text-slate-400 mt-1">Supports PDF, PNG, and JPEG documents</p>
            </div>
          </div>
        )}
      </div>

      {/* Action Controls & Banners */}
      {selectedFile && (
        <div className="flex justify-end pt-2">
          <button
            type="button"
            onClick={handleUploadSubmit}
            disabled={uploading}
            className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600 text-white font-semibold text-sm transition-all shadow-md shadow-indigo-600/30 flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {uploading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Uploading & Processing...
              </>
            ) : (
              <>
                <UploadCloud className="w-4 h-4" />
                Upload & Process Document
              </>
            )}
          </button>
        </div>
      )}

      {/* Feedback Messages */}
      {errorMsg && (
        <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
          <span>{errorMsg}</span>
        </div>
      )}

      {successMsg && (
        <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
          <span>{successMsg}</span>
        </div>
      )}
    </div>
  )
}
