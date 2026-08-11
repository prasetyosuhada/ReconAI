"""Background service for document intake & bookkeeping processing."""

import logging
from typing import Any

from app.agents.orchestrator import document_processing_graph
from app.db.session import SessionLocal
from app.models.audit import AuditEvent
from app.models.document import Document

logger = logging.getLogger(__name__)


def process_document_background(
    document_id: str,
    stored_file_path: str,
    mime_type: str,
    original_filename: str,
    document_type: str = "unknown",
) -> None:
    """Execute LangGraph document intake & bookkeeping workflow asynchronously.

    Args:
        document_id: UUID string of the Document database record.
        stored_file_path: Absolute disk path where uploaded file is stored.
        mime_type: File content-type (e.g. application/pdf, image/png).
        original_filename: Original name of the uploaded file.
        document_type: Document classification e.g. invoice, receipt, unknown.
    """
    logger.info("Starting background processing for document ID: %s", document_id)
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.error(
                "Document %s not found in DB during background processing.",
                document_id,
            )
            return

        doc.status = "extracting"
        db.commit()

        initial_state: dict[str, Any] = {
            "document_id": document_id,
            "original_filename": original_filename,
            "mime_type": mime_type,
            "stored_file_path": stored_file_path,
            "status": "extracting",
        }

        # Run compiled LangGraph StateGraph workflow
        final_state = document_processing_graph.invoke(initial_state)

        final_status = final_state.get("status", "extracted")
        doc.status = final_status
        db.commit()

        # Record audit event
        audit = AuditEvent(
            event_type="extraction_completed",
            source_type="document",
            source_id=doc.id,
            actor_type="agent",
            actor_name="DocumentProcessingGraph",
            input_snapshot={
                "document_id": document_id,
                "original_filename": original_filename,
            },
            output_snapshot={
                "status": final_status,
                "confidence_score": final_state.get("confidence_score", 0.0),
                "needs_review": final_state.get("needs_review", False),
            },
            confidence_score=final_state.get("confidence_score", 0.0),
            rationale=final_state.get("rationale"),
        )
        db.add(audit)
        db.commit()
        logger.info(
            "Completed background processing for document %s with status: %s",
            document_id,
            final_status,
        )

    except Exception as e:
        logger.error(
            "Error processing document %s in background: %s",
            document_id,
            str(e),
            exc_info=True,
        )
        db.rollback()
        try:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if doc:
                doc.status = "failed"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
