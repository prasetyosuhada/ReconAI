"""End-to-End (E2E) Happy Path Workflow Integration Test.

Tests full automated cycle:
Upload -> Auto Extract -> Review Approval -> Auto Bookkeeping -> Ledger Posting -> Bank Reconciliation -> Audit Trail
"""

import io
import uuid
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.agents.schemas import BookkeepingOutcome
from app.models.audit import AuditEvent
from app.models.coa import ChartOfAccount
from app.models.document import Document, DocumentExtraction
from app.models.journal import JournalEntry
from app.models.review import ReviewItem
from app.services.accounting import (
    post_journal_entry_to_ledger,
    validate_double_entry,
)
from app.services.reconciliation import execute_reconciliation_workflow


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
            account_code="1400",
            account_name="PPN Masukan (Input VAT)",
            account_type="asset",
            normal_balance="debit",
            is_active=True,
        ),
        ChartOfAccount(
            account_code="2000",
            account_name="Accounts Payable",
            account_type="liability",
            normal_balance="credit",
            is_active=True,
        ),
        ChartOfAccount(
            account_code="5100",
            account_name="Software Subscriptions",
            account_type="expense",
            normal_balance="debit",
            is_active=True,
        ),
    ]
    for acc in accounts:
        db.add(acc)
    db.commit()


def test_e2e_happy_path_workflow(client, db_session):
    """Execute complete E2E Happy Path pipeline."""
    seed_coa_accounts(db_session)

    # -------------------------------------------------------------
    # STEP 1: Document Upload
    # -------------------------------------------------------------
    pdf_path = Path("/home/pras/recon-ai/demo-data/invoices/invoice_01_aws_cloud.pdf")
    if pdf_path.exists():
        file_content = pdf_path.read_bytes()
    else:
        file_content = b"%PDF-1.4 AWS Cloud Services Subscription IDR 1500000"

    file_tuple = (
        "invoice_01_aws_cloud.pdf",
        io.BytesIO(file_content),
        "application/pdf",
    )

    with patch("app.api.v1.documents.process_document_background"):
        upload_res = client.post(
            "/api/v1/documents/upload",
            files={"file": file_tuple},
            data={"document_type": "invoice"},
        )

    assert upload_res.status_code == 201
    doc_data = upload_res.json()
    doc_id_str = doc_data["id"]
    doc_id = uuid.UUID(doc_id_str)

    assert doc_data["original_filename"] == "invoice_01_aws_cloud.pdf"
    assert doc_data["status"] == "extracting"

    # Verify Document stored in DB
    doc_obj = db_session.query(Document).filter(Document.id == doc_id).first()
    assert doc_obj is not None

    # -------------------------------------------------------------
    # STEP 2: Document Intake & Extraction (AI Agent Node)
    # -------------------------------------------------------------
    extraction = DocumentExtraction(
        id=uuid.uuid4(),
        document_id=doc_id,
        vendor_name="Amazon Web Services Inc.",
        transaction_date=date(2026, 8, 1),
        subtotal_amount=1351351.0,
        tax_amount=148649.0,
        total_amount=1500000.0,
        currency="IDR",
        confidence_score=0.96,
        status="extracted",
    )
    db_session.add(extraction)

    # Add audit event for extraction
    audit_intake = AuditEvent(
        id=uuid.uuid4(),
        event_type="extraction_completed",
        source_type="document",
        source_id=doc_id,
        actor_type="agent",
        actor_name="Document Intake Agent",
        confidence_score=0.96,
        output_snapshot={
            "vendor_name": "Amazon Web Services Inc.",
            "total_amount": 1500000.0,
        },
    )
    db_session.add(audit_intake)

    # Add ReviewItem for human verification queue
    review_item = ReviewItem(
        id=uuid.uuid4(),
        review_type="extraction",
        status="pending",
        priority="normal",
        source_type="document",
        source_id=doc_id,
        title="Verify AWS Invoice Extraction",
        summary="Extraction for Amazon Web Services Inc. total IDR 1,500,000",
        original_payload={
            "vendor_name": "Amazon Web Services Inc.",
            "total_amount": 1500000.0,
        },
    )
    db_session.add(review_item)
    db_session.commit()

    # -------------------------------------------------------------
    # STEP 3: Human Review Queue Approval
    # -------------------------------------------------------------
    bookkeeping_outcome = BookkeepingOutcome(
        entry_date="2026-08-01",
        entry_description="AWS Cloud Services Subscription",
        journal_lines=[
            {
                "account_code": "5100",
                "account_name": "Software Subscriptions",
                "debit_amount": 1351351.0,
                "credit_amount": 0.0,
            },
            {
                "account_code": "1400",
                "account_name": "PPN Masukan (Input VAT)",
                "debit_amount": 148649.0,
                "credit_amount": 0.0,
            },
            {
                "account_code": "2000",
                "account_name": "Accounts Payable",
                "debit_amount": 0.0,
                "credit_amount": 1500000.0,
            },
        ],
        total_debit=1500000.0,
        total_credit=1500000.0,
        is_balanced=True,
        confidence_score=0.95,
        rationale="AWS cloud expense and input VAT classification.",
        status="ready_to_post",
        needs_review=False,
    )
    with patch(
        "app.api.v1.review_items.classify_bookkeeping",
        return_value=bookkeeping_outcome,
    ):
        approve_res = client.post(
            f"/api/v1/review-items/{review_item.id}/approve",
            json={"reviewer_notes": "Extraction verified clean."},
        )
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "approved"

    # -------------------------------------------------------------
    # STEP 4: Auto Bookkeeping Agent & Double-Entry Guardrail
    # -------------------------------------------------------------
    je = db_session.query(JournalEntry).filter(JournalEntry.document_id == doc_id).one()

    # Test Deterministic Double-Entry Validation
    val_res = validate_double_entry(je.lines)
    assert val_res.is_valid is True
    assert val_res.difference == 0.0

    # -------------------------------------------------------------
    # STEP 5: Post Journal Entry to Ledger & Verify Trial Balance
    # -------------------------------------------------------------
    post_res = post_journal_entry_to_ledger(je, db_session)
    assert post_res.success is True
    assert je.status == "posted"

    tb_res = client.get("/api/v1/ledger/trial-balance")
    assert tb_res.status_code == 200
    tb_data = tb_res.json()
    assert tb_data["status"] == "balanced"
    assert tb_data["total_debits"] == 1500000.0
    assert tb_data["total_credits"] == 1500000.0
    assert tb_data["difference"] == 0.0

    # -------------------------------------------------------------
    # STEP 6: Bank Statement Import & Reconciliation Engine
    # -------------------------------------------------------------
    csv_bytes = (
        b"transaction_date,description,amount,currency,reference_number\n"
        b"2026-08-01,PAYMENT AWS CLOUD SERVICES INC,-1500000,IDR,REF-AWS-98123\n"
    )

    bank_csv_tuple = ("mock_bank_statement.csv", io.BytesIO(csv_bytes), "text/csv")
    bank_res = client.post("/api/v1/bank/upload-mock", files={"file": bank_csv_tuple})
    assert bank_res.status_code == 201
    import_id = bank_res.json()["id"]

    mock_graph = MagicMock()
    mock_graph.invoke.return_value = {
        "candidate_matches": [],
        "status": "unmatched_review_required",
        "needs_review": True,
    }

    # Run Reconciliation Engine
    with (
        patch("app.services.reconciliation.SessionLocal", return_value=db_session),
        patch(
            "app.services.reconciliation.reconciliation_graph",
            mock_graph,
        ),
    ):
        execute_reconciliation_workflow(import_id)

    # Query matches via API
    matches_res = client.get(
        f"/api/v1/reconciliation/matches?bank_statement_import_id={import_id}"
    )
    assert matches_res.status_code == 200
    match_items = matches_res.json()["items"]
    assert len(match_items) >= 1

    aws_match = next(
        (m for m in match_items if m["bank_transaction"]["amount"] == -1500000.0), None
    )
    assert aws_match is not None
    assert aws_match["status"] in ["proposed", "accepted", "matched"]
    assert aws_match["confidence_score"] == 1.0

    # -------------------------------------------------------------
    # STEP 7: Audit Log Traceability Verification
    # -------------------------------------------------------------
    audit_res = client.get(f"/api/v1/audit-log/{doc_id_str}")
    assert audit_res.status_code == 200
    audit_data = audit_res.json()

    assert audit_data["document_id"] == doc_id_str
    assert len(audit_data["timeline"]) >= 1
    assert any(
        e["event_type"] == "extraction_completed" for e in audit_data["timeline"]
    )

    print("\n✅ E2E Happy Path Workflow Test Passed Successfully!")
