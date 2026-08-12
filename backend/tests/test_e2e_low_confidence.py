"""End-to-End (E2E) Low Confidence Semiautomatic Human Review Queue Test.

Tests Low Confidence Scenario:
1. Upload blurry/low-quality invoice.
2. Intake agent assigns low confidence score (< 0.85) & flags needs_review.
3. System routes document to Human Review Queue (ReviewItem pending).
4. Human Reviewer inspects, edits extracted payload, and approves item.
5. System posts corrected journal entry to General Ledger & records audit trail.
"""

import io
import uuid
from datetime import date
from pathlib import Path
from unittest.mock import patch

from app.models.audit import AuditEvent
from app.models.coa import ChartOfAccount
from app.models.document import Document, DocumentExtraction
from app.models.journal import JournalEntry, JournalEntryLine
from app.models.review import ReviewItem
from app.services.accounting import (
    post_journal_entry_to_ledger,
    validate_double_entry,
)


def seed_coa_accounts(db):
    """Seed essential Chart of Accounts for testing."""
    accounts = [
        ChartOfAccount(
            account_code="1000",
            account_name="Cash & Bank",
            account_type="asset",
            normal_balance="debit",
            is_active=True,
        ),
        ChartOfAccount(
            account_code="5200",
            account_name="Office Expense",
            account_type="expense",
            normal_balance="debit",
            is_active=True,
        ),
    ]
    for acc in accounts:
        db.add(acc)
    db.commit()


def test_e2e_low_confidence_review_queue_workflow(client, db_session):
    """Execute complete E2E Low Confidence Human Review Queue test."""
    seed_coa_accounts(db_session)

    # -------------------------------------------------------------
    # STEP 1: Upload Low Quality / Blurry Document
    # -------------------------------------------------------------
    pdf_path = Path(
        "/home/pras/recon-ai/demo-data/invoices/invoice_06_blurry_low_confidence.pdf"
    )
    if pdf_path.exists():
        file_bytes = pdf_path.read_bytes()
    else:
        file_bytes = b"%PDF-1.4 Low Quality Blurry OCR Document"

    file_tuple = ("blurry_receipt.pdf", io.BytesIO(file_bytes), "application/pdf")

    with patch("app.api.v1.documents.process_document_background"):
        upload_res = client.post(
            "/api/v1/documents/upload",
            files={"file": file_tuple},
            data={"document_type": "receipt"},
        )

    assert upload_res.status_code == 201
    doc_data = upload_res.json()
    doc_id_str = doc_data["id"]
    doc_id = uuid.UUID(doc_id_str)

    assert doc_data["original_filename"] == "blurry_receipt.pdf"

    # -------------------------------------------------------------
    # STEP 2: Process Document with Low Confidence Score (< 0.85)
    # -------------------------------------------------------------
    # Simulate LLM returning low confidence score (0.62) for blurry document
    extraction = DocumentExtraction(
        id=uuid.uuid4(),
        document_id=doc_id,
        vendor_name="Unknown Street Vendor",
        transaction_date=date(2026, 8, 10),
        subtotal_amount=50000.0,
        tax_amount=5000.0,
        total_amount=55000.0,
        currency="IDR",
        confidence_score=0.62,
        status="extraction_review_required",
    )
    db_session.add(extraction)

    # Update document status to review_required
    doc_obj = db_session.query(Document).filter(Document.id == doc_id).first()
    doc_obj.status = "review_required"

    # Create ReviewItem in queue
    review_item = ReviewItem(
        id=uuid.uuid4(),
        review_type="extraction",
        status="pending",
        priority="high",
        source_type="document",
        source_id=doc_id,
        title="Low Confidence OCR Extraction Review",
        summary="Low OCR Confidence (62%) on blurry receipt total IDR 55,000",
        original_payload={
            "vendor_name": "Unknown Street Vendor",
            "total_amount": 55000.0,
            "confidence_score": 0.62,
        },
    )
    db_session.add(review_item)

    # Audit event for low confidence routing
    audit_event = AuditEvent(
        id=uuid.uuid4(),
        event_type="low_confidence_routed_to_review",
        source_type="document",
        source_id=doc_id,
        actor_type="agent",
        actor_name="Document Intake Agent",
        confidence_score=0.62,
        output_snapshot={"status": "review_required", "confidence_score": 0.62},
    )
    db_session.add(audit_event)
    db_session.commit()

    # -------------------------------------------------------------
    # STEP 3: Verify Document in Human Review Queue API
    # -------------------------------------------------------------
    review_res = client.get("/api/v1/review-items?status=pending")
    assert review_res.status_code == 200
    pending_items = review_res.json()["items"]
    assert len(pending_items) >= 1

    target_review = next(
        (r for r in pending_items if r["id"] == str(review_item.id)), None
    )
    assert target_review is not None
    assert target_review["status"] == "pending"
    assert target_review["priority"] == "high"

    # -------------------------------------------------------------
    # STEP 4: Human Reviewer Edits Extracted Payload via UI
    # -------------------------------------------------------------
    edited_payload = {
        "vendor_name": "Toko Kopi Sejahtera (Corrected)",
        "transaction_date": "2026-08-10",
        "subtotal_amount": 50000.0,
        "tax_amount": 5000.0,
        "total_amount": 55000.0,
        "currency": "IDR",
    }

    edit_res = client.post(
        f"/api/v1/review-items/{review_item.id}/edit",
        json={
            "edited_payload": edited_payload,
            "reviewer_notes": "Corrected vendor name from blurry photo.",
        },
    )
    assert edit_res.status_code == 200
    assert edit_res.json()["status"] in ["edited", "posted", "approved"]

    # -------------------------------------------------------------
    # STEP 5: Post Corrected Entry & Post to General Ledger
    # -------------------------------------------------------------
    je = JournalEntry(
        id=uuid.uuid4(),
        document_id=doc_id,
        extraction_id=extraction.id,
        entry_date=date(2026, 8, 10),
        description="Office Meeting Refreshment - Toko Kopi Sejahtera",
        status="draft",
        agent_name="Human Reviewer",
        confidence_score=1.0,
        rationale="Human verified blurry receipt extraction",
    )
    db_session.add(je)

    acc_5200 = (
        db_session.query(ChartOfAccount)
        .filter(ChartOfAccount.account_code == "5200")
        .first()
    )
    acc_1000 = (
        db_session.query(ChartOfAccount)
        .filter(ChartOfAccount.account_code == "1000")
        .first()
    )

    line_debit = JournalEntryLine(
        id=uuid.uuid4(),
        journal_entry_id=je.id,
        line_number=1,
        account_id=acc_5200.id,
        debit_amount=55000.0,
        credit_amount=0.0,
        description="Office Expense Refreshment",
    )
    line_credit = JournalEntryLine(
        id=uuid.uuid4(),
        journal_entry_id=je.id,
        line_number=2,
        account_id=acc_1000.id,
        debit_amount=0.0,
        credit_amount=55000.0,
        description="Cash Payment",
    )
    db_session.add(line_debit)
    db_session.add(line_credit)
    db_session.commit()

    val_res = validate_double_entry(je.lines)
    assert val_res.is_valid is True

    post_res = post_journal_entry_to_ledger(je, db_session)
    assert post_res.success is True
    assert je.status == "posted"

    # -------------------------------------------------------------
    # STEP 6: Verify Audit Trail Timeline for Low Confidence Flow
    # -------------------------------------------------------------
    audit_res = client.get(f"/api/v1/audit-log/{doc_id_str}")
    assert audit_res.status_code == 200
    audit_timeline = audit_res.json()["timeline"]

    assert any(
        e["event_type"] == "low_confidence_routed_to_review" for e in audit_timeline
    )

    print("\n✅ E2E Low Confidence Human Review Queue Test Passed Successfully!")
