# Test Plan & Evaluation Strategy
## ReconAI — Agentic AI Platform for Accounting Automation

**Version:** 1.0  
**Status:** Draft  
**Related Documents:** `docs/01-PRD.md`, `docs/04-Agent-Design.md`, `docs/10-Hybrid-Document-Extraction.md`, `docs/12-Source-Backed-Human-Review.md` (Planned — Epic 15)
**Document Owner:** Prasetyo Suhada

---

## 1. Overview

This document outlines the testing and evaluation strategy for ReconAI. Because the system combines non-deterministic AI agents (LLMs) with strict, deterministic accounting rules, the testing approach is split into two main pillars:
1. **Traditional Software Testing (Deterministic):** Unit and integration tests for API endpoints, database operations, and hardcoded accounting logic.
2. **AI Agent Evaluation (Non-Deterministic):** Accuracy and behavior testing against a "golden dataset" to ensure the agents output reliable, high-confidence results and correctly route edge cases to human review.

---

## 2. Test Data Strategy

To ensure consistent testing, the following datasets will be prepared and version-controlled:

- **Sample Documents:** A controlled dataset of 20-30 varied invoices and receipts (PDFs, JPEGs).
  - Include high-quality digital PDFs.
  - Include scanned and mixed PDFs, PNG/WebP images, and low-quality/blurry photos.
  - Include multi-page, corrupt, encrypted, and over-limit cases.
- **Generated Extraction Fixtures:** Unit and integration tests create deterministic
  digital/scanned/mixed PDFs and low-detail images at runtime, avoiding external LLM
  calls while exercising the real local extraction path.
- **Mock Bank Statements:** CSV files containing bank transactions that correspond to the sample documents.
  - **Exact Matches:** Perfect 1:1 match on amount, date, and vendor.
  - **Fuzzy Matches:** Slight date drift (± 2 days) or minor vendor name variations (e.g., "AWS" vs "Amazon Web Services").
  - **Unmatched Items:** Transactions with no corresponding ledger entry.
- **Golden Dataset:** A set of pre-defined expected outputs (ground truth) for extraction, categorization, and reconciliation to measure agent accuracy programmatically.

---

## 3. Traditional Testing (Deterministic)

### 3.1 Backend & Orchestration (FastAPI + LangGraph)
- **API Endpoints:** 
  - Test `/api/v1/documents/upload`, `/api/v1/documents/stream/{id}`, review, and
    reconciliation endpoints for expected HTTP status codes, payload validation, and
    error handling.
- **Document Content Preparation:**
  - Verify digital PDF text retention, scanned-page rendering, mixed per-page
    classification, ordered visual pages, MIME preservation, and resource bounds.
- **Safe Failure and Routing:**
  - Verify missing/corrupt/encrypted content skips the LLM and persists an extraction
    review without creating a journal entry.
- **Deterministic Extraction Validation:**
  - Verify essential fields, finite/non-negative values, exact dates and currency codes,
    subtotal/tax/total consistency, line-item sums, confidence caps, and risk flags.
- **Accounting Engine (Critical):** 
  - **Double-Entry Validation:** Assert that any function creating a journal entry fails if Debits ≠ Credits.
  - **Trial Balance:** Verify that ledger posting correctly updates the running balance.
- **Database Operations:** Test CRUD operations for documents, journal entries, and the audit log.
- **State Management:** Ensure LangGraph maintains context correctly between the Intake, Bookkeeping, and Reconciliation nodes.
- **Source-Backed Review (Planned — Epic 15):** Verify controlled source delivery,
  extraction correction validation, pending-state preservation on failure, and atomic,
  idempotent continuation after a valid human decision.

### 3.2 Frontend (Vite/React)
- **UI Components:** Test document upload drag-and-drop, review queue rendering, and approval/rejection button actions.
- **Human-in-the-Loop Flow:** Ensure the UI correctly reflects the "Awaiting Review" state and updates optimistically when a user approves a suggestion.
- **Extraction Review Workspace (Planned — Epic 15):** Verify PDF/image evidence,
  source and content-quality states, diagnostic metadata, editable field validation,
  and duplicate-submit protection.

Frontend component testing remains planned; no Vitest/React Testing Library suite is
currently configured. Frontend verification currently uses format, lint, and production
build checks.

---

## 4. AI Agent Evaluation Strategy

Because LLM outputs can vary, we will evaluate the agents based on accuracy metrics against the Golden Dataset.

### 4.1 Document Intake Agent
- **Metric:** Extraction Accuracy (Precision & Recall).
- **Test:** Run the agent against the 20-30 sample documents.
- **Criteria:** 
  - **High Accuracy:** Subtotal, Tax, and Total Amount must have 95%+ accuracy. Vendor Name & Date > 90%.
  - **Confidence Calibration:** Ensure low-quality documents correctly produce low confidence scores (e.g., < 0.8) and successfully trigger the human review queue.

These are evaluation targets, not current measured results. The deterministic extraction
matrix mocks the LLM boundary and therefore must not be reported as OCR/model accuracy.

### 4.2 Bookkeeping Agent
- **Metric:** Categorization Accuracy & Rationale Quality.
- **Test:** Pass perfectly extracted data (from the Golden Dataset) to the Bookkeeping Agent.
- **Criteria:**
  - Suggested COA (Chart of Accounts) matches the ground truth for at least 85% of standard transactions.
  - The natural-language rationale is logically sound and references standard accounting principles (e.g., "This is an AWS invoice, categorized as Software Subscriptions").

### 4.3 Reconciliation Agent
- **Metric:** Match Rate & False Positives.
- **Test:** Run the mock bank statements against posted ledger entries.
- **Criteria:**
  - 100% of exact matches are identified and assigned high confidence.
  - Fuzzy matches are successfully flagged for human review (not auto-approved).
  - **0% False Positives:** The agent must never auto-reconcile a transaction that does not belong to the ledger entry.

### 4.4 Implemented Hybrid Extraction Matrix

`backend/tests/test_document_extraction_matrix.py` provides the focused unit,
integration, and regression matrix:

| Condition | Assertions |
|---|---|
| Digital multi-page PDF | Text retained in order; no unnecessary visual pages. |
| Scanned multi-page PDF | Every page rendered to bounded PNG in page order. |
| Mixed PDF | Text and vision page numbers remain correctly classified. |
| Image and blurry/low-detail input | Actual bytes and MIME reach vision; low confidence routes to review. |
| Corrupt/encrypted PDF | Safe unreadable result, no LLM call, persisted Human Review, no journal. |
| Processing limits | Default page truncation and rendered-pixel boundary remain enforced. |
| Multimodal payload | All visual pages use MIME-correct data URLs and filename is excluded as evidence. |

### 4.5 Source-Backed Human Review Matrix (Planned — Epic 15)

These tests do not exist yet. They are the acceptance matrix for Tasks 15.2–15.7 and
must not be reported as implemented coverage until the corresponding suites pass.

| Area | Planned Verification |
|---|---|
| Source endpoint | PDF/JPEG/PNG/WebP bytes, validated MIME, safe inline filename and headers, malformed UUID, missing row/file, unsupported type, traversal, and symlink escape. |
| Review detail contract | Safe `source_document` descriptor plus normalized extraction method, source/processed page counts, page sets, warnings, low-confidence fields, and risk flags; no internal path or raw provider payload. |
| Approve as-is | Valid extraction continues once; invalid persisted extraction returns field errors, remains pending, and does not call Bookkeeping. |
| Edit and Continue | Allowlisted valid correction continues; invalid date/currency/numeric/required fields or inconsistent amounts return `422` and remain pending. |
| Provenance | Original confidence and provider metadata remain intact; human changes and resolution context are auditable. |
| Transaction rollback | Bookkeeping or persistence failure leaves review, document, journal, downstream review, and audit state consistent. |
| Idempotency | Repeated resolution produces one downstream outcome and a stable conflict response. |
| PostgreSQL concurrency | Two simultaneous valid resolutions produce one winner with no duplicate journal, review, status, or audit side effects. |
| Evidence UI | Multi-page PDF navigation, image scaling, loading/missing/blocked/unsupported/render-failure states, and Open Source action. |
| Context and form UI | Partial-processing notice, warnings/risk/low-confidence metadata, field-associated errors, retained correction draft, keyboard use, and in-flight action disabling. |
| Regression | Existing digital/scanned/mixed/corrupt/encrypted/partial extraction, bookkeeping, audit, and non-extraction review behavior remains valid. |

---

## 5. End-to-End (E2E) Workflow Testing

To validate the entire system, the following E2E scenarios must pass:

**Scenario: The Happy Path with Human Review**
1. Upload `demo-data/invoices/invoice_02_office_supplies.pdf`.
2. Verify Text & Vision preparation and Document Intake produce valid structured fields.
3. Verify a valid high-confidence extraction continues to Bookkeeping.
4. Verify Bookkeeping drafts a journal entry and pauses for Review when required.
5. User approves the review item via UI.
6. Verify entry is posted to the Ledger and Trial Balance remains balanced.
7. Upload `demo-data/bank_statements/mock_bank_statement_august_2026.csv`.
8. Verify Reconciliation Agent matches the entry correctly.
9. Separately verify a low-quality or unreadable document routes to extraction review.
10. Check **Audit Log** for agent confidence, extraction metadata, and human actions.

**Planned Epic 15 extension:** repeat the extraction-review portion with a multi-page PDF
and an image, compare fields with the real stored source, submit one invalid correction
and confirm it remains pending, then submit a valid correction twice and confirm only one
downstream result and complete audit trace exist.

---

## 6. Tools & Frameworks

- **Backend Testing:** `pytest` for unit and integration testing.
- **Frontend Testing:** Format, ESLint, and Vite production build today; Vitest and React Testing Library are planned.
- **LLM Evaluation:** Custom Python scripts (or evaluation frameworks like `LangSmith` / `DeepEval` / `Ragas`) to automate running agents against the Golden Dataset, calculating accuracy metrics, and checking for regressions when prompts are updated.

Focused extraction verification:

```bash
cd backend
uv run pytest -q \
  tests/test_document_extraction.py \
  tests/test_document_extraction_matrix.py \
  tests/test_document_intake_agent.py \
  tests/test_extraction_validation.py \
  tests/test_orchestrator.py \
  tests/test_document_metadata.py
```

For UI/API fixture preparation, expected metadata, safe-failure checks, and a reusable
evidence checklist, follow
[`docs/11-Hybrid-Extraction-Manual-Test.md`](11-Hybrid-Extraction-Manual-Test.md).
