"""FastAPI Documents API Router (Upload & Management)."""

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.audit import AuditEvent
from app.models.document import Document
from app.schemas.document import (
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentResponse,
)
from app.services.document_processing import process_document_background

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}

UPLOAD_STORAGE_DIR = Path("./storage/uploads")


def _get_upload_dir() -> Path:
    """Ensure upload storage directory exists."""
    UPLOAD_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_STORAGE_DIR


@router.get(
    "",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List uploaded documents with optional status filter and pagination",
)
def list_documents(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> DocumentListResponse:
    """List uploaded documents in repository."""
    query = db.query(Document)
    if status:
        query = query.filter(Document.status == status)

    total_count = query.with_entities(func.count(Document.id)).scalar() or 0
    records = (
        query.order_by(Document.uploaded_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = [
        DocumentDetailResponse(
            id=str(d.id),
            original_filename=d.original_filename,
            stored_file_path=d.stored_file_path,
            mime_type=d.mime_type,
            file_size_bytes=d.file_size_bytes,
            document_type=d.document_type,
            status=d.status,
            uploaded_at=d.uploaded_at,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in records
    ]

    return DocumentListResponse(
        items=items,
        total=total_count,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single document details",
)
def get_document_detail(
    document_id: str,
    db: Session = Depends(get_db),
) -> DocumentDetailResponse:
    """Fetch document details by UUID."""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UUID format for document_id.",
        )

    doc = db.query(Document).filter(Document.id == doc_uuid).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document [{document_id}] not found.",
        )

    return DocumentDetailResponse(
        id=str(doc.id),
        original_filename=doc.original_filename,
        stored_file_path=doc.stored_file_path,
        mime_type=doc.mime_type,
        file_size_bytes=doc.file_size_bytes,
        document_type=doc.document_type,
        status=doc.status,
        uploaded_at=doc.uploaded_at,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload document and trigger AI processing workflow",
)
@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_type: str = Form("unknown"),
    db: Session = Depends(get_db),
) -> DocumentResponse:
    """Upload invoice/receipt document (PDF/JPEG/PNG) and trigger background intake.

    - Validates file type and size.
    - Saves file to disk storage.
    - Saves Document record in database.
    - Creates `document_uploaded` audit event.
    - Enqueues LangGraph background processing task.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a valid filename.",
        )

    content_type = file.content_type or ""
    filename_lower = file.filename.lower()
    is_valid_type = (
        content_type in ALLOWED_MIME_TYPES
        or filename_lower.endswith(".pdf")
        or filename_lower.endswith((".jpg", ".jpeg", ".png", ".webp"))
    )

    if not is_valid_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Allowed: PDF, JPEG, PNG.",
        )

    file_bytes = await file.read()
    file_size = len(file_bytes)

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # Save to disk
    storage_dir = _get_upload_dir()
    doc_uuid = uuid.uuid4()
    safe_filename = f"{doc_uuid}_{Path(file.filename).name}"
    stored_path = storage_dir / safe_filename

    with open(stored_path, "wb") as f:
        f.write(file_bytes)

    now_utc = datetime.now(UTC)
    effective_mime = (
        content_type
        if content_type in ALLOWED_MIME_TYPES
        else ("application/pdf" if filename_lower.endswith(".pdf") else "image/jpeg")
    )

    valid_doc_type = (
        document_type if document_type in ("invoice", "receipt") else "unknown"
    )

    # Save Document record to DB
    doc_record = Document(
        id=doc_uuid,
        original_filename=file.filename,
        stored_file_path=str(stored_path.resolve()),
        mime_type=effective_mime,
        file_size_bytes=file_size,
        document_type=valid_doc_type,
        status="uploaded",
        uploaded_at=now_utc,
    )
    db.add(doc_record)

    # Record Audit Event
    audit_record = AuditEvent(
        event_type="document_uploaded",
        source_type="document",
        source_id=doc_uuid,
        actor_type="human",
        actor_name="api_user",
        input_snapshot={
            "original_filename": file.filename,
            "file_size_bytes": file_size,
            "document_type": document_type,
            "mime_type": effective_mime,
        },
        output_snapshot={
            "status": "uploaded",
            "stored_file_path": str(stored_path.resolve()),
        },
    )
    db.add(audit_record)
    db.commit()
    db.refresh(doc_record)

    # Add background processing task
    background_tasks.add_task(
        process_document_background,
        document_id=str(doc_uuid),
        stored_file_path=str(stored_path.resolve()),
        mime_type=effective_mime,
        original_filename=file.filename,
        document_type=document_type,
    )

    self_link = f"{settings.API_V1_STR}/documents/{doc_uuid}"
    audit_link = (
        f"{settings.API_V1_STR}/audit-events?source_type=document&source_id={doc_uuid}"
    )

    return DocumentResponse(
        id=str(doc_record.id),
        original_filename=doc_record.original_filename,
        document_type=doc_record.document_type,
        status="extracting",
        uploaded_at=doc_record.uploaded_at,
        links={
            "self": self_link,
            "audit_events": audit_link,
        },
    )
