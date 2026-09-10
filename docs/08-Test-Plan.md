# Test Plan & Evaluation Strategy
## ReconAI — Agentic AI Platform for Accounting Automation

**Version:** 1.0  
**Status:** Draft  
**Related Documents:** `docs/01-PRD.md`, `docs/04-Agent-Design.md`, `docs/10-Hybrid-Document-Extraction.md`
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

### 3.2 Frontend (Vite/React)
- **UI Components:** Test document upload drag-and-drop, review queue rendering, and approval/rejection button actions.
- **Human-in-the-Loop Flow:** Ensure the UI correctly reflects the "Awaiting Review" state and updates optimistically when a user approves a suggestion.

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
