# Test Plan & Evaluation Strategy
## ReconAI — Agentic AI Platform for Accounting Automation

**Version:** 1.0  
**Status:** Draft  
**Related Documents:** `docs/01-PRD.md`, `docs/04-Agent-Design.md`, `docs/10-Hybrid-Document-Extraction.md`, `docs/12-Source-Backed-Human-Review.md` (Implemented — Epic 15)
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
- **Source-Backed Review (Implemented — Epic 15):** Verify controlled source delivery,
  extraction correction validation, pending-state preservation on failure, and atomic,
  idempotent continuation after a valid human decision.

### 3.2 Frontend (Vite/React)

Vitest and React Testing Library run component tests in jsdom. `npm test` first checks
TypeScript types for application and test files, then runs the suite. External API
responses are mocked at `fetch`; the real review API adapter handles `422`, `409`, and
`503` envelopes in modal tests.

- `SourceDocumentViewer.test.tsx`: PDF page URL and bounded navigation (including the
  one-page regression and unknown count), keyboard activation, image rendering,
  loading/error states, Open Source and object URL cleanup.
- `ExtractionReviewContext.test.tsx`: warnings, low-confidence/risk metadata, partial
  coverage, and absent versus empty diagnostics.
- `ExtractionReviewModal.test.tsx`: valid confirmation, invalid approve/edit, accessible
  field errors, retained draft and corrected retry, one in-flight submission, conflict,
  recoverable failure, reject conflict, and unknown payment state.
- `documentUpload.test.ts`: supported types, 10 MB boundary, empty and unsupported files.

The tests do not render native PDF plugin pixels or run the live backend/LLM. Full
responsive layout, native PDF behavior (especially corrupt/encrypted files), and modal
focus/accessibility need manual browser verification. There is no measured coverage
percentage or agent-accuracy benchmark from these tests.

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

### 4.5 Source-Backed Human Review Matrix (Implemented — Epic 15)

The following implemented suites exercise the Epic 15 acceptance boundaries:

| Area | Automated evidence |
|---|---|
| Source endpoint | `backend/tests/test_documents_api.py`: PDF/JPEG/PNG/WebP, MIME/signature, inline headers/range responses, missing row/file, traversal and symlink escape. |
| Separate evidence reads | `test_review_workflow_regression.py`: review source ID, latest extraction metadata and byte endpoint for actual digital/scanned multi-page PDF, PNG and missing source. No combined evidence descriptor is implemented. |
| Approve/edit validation and provenance | `test_review_correction_validation.py`: typed/monetary errors, persisted precedence, metadata protection and corrected retry. |
| Transaction rollback and idempotency | `test_review_continuation.py`: classification, persistence, audit and commit failures, plus all decision retry combinations. |
| PostgreSQL concurrency | `test_review_continuation_postgres.py`: independent sessions, observed row-lock wait, one winner, reject races and rollback. Skips without the explicit PostgreSQL test URL. |
| Evidence/context/form UI | The component suites in §3.2; mocked API responses and jsdom DOM interactions. |
| Regression | Full backend suite retains hybrid extraction, bookkeeping, audit and non-extraction review checks. |

The API journey test starts with a seeded pending review and real generated source files;
it does not replace the existing upload/intake integration tests. It confirms invalid
approve/edit does not mutate state, valid correction creates one downstream result,
subsequent approve/edit/reject returns `409`, and original metadata/confidence is retained.

Production authorization, removal of legacy document path fields, source-access/failure
audit events, and native PDF rendering are not implied by these passes. See
`12-Source-Backed-Human-Review.md` for implementation differences from the initial design.

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

**Manual Epic 15 browser extension (not recorded as executed):** repeat the extraction-review portion with a multi-page PDF
and an image, compare fields with the real stored source, submit one invalid correction
and confirm it remains pending, then submit a valid correction twice and confirm only one
downstream result and complete audit trace exist.

---

## 6. Tools & Frameworks

- **Backend Testing:** `pytest` for unit and integration testing.
- **Frontend Testing:** Vitest, React Testing Library, user-event and jsdom; TypeScript checks, Oxlint, Prettier and Vite production build.
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


### 6.1 Review regression commands

```bash
cd frontend
npm ci
npm test
npm run lint
npm run format:check
npm run build
```

```bash
cd backend
DATABASE_URL="sqlite:///:memory:" .venv/bin/pytest -q
```

For PostgreSQL concurrency coverage, set `RECONAI_TEST_POSTGRES_URL` in the test process
environment before running pytest (see `09-Setup-Guide.md`). Each race test creates and
drops only its own random schema. A SQLite-only run skips these tests and must not be
reported as concurrency verification. All automated review tests stub external LLM calls.


### 6.2 Verified run — 2026-09-26 (Task 15.8)

| Check | Result |
|---|---|
| Full backend suite | 248 passed, 0 failed, 0 skipped; includes 4 new source/review journey cases. |
| PostgreSQL concurrency/rollback subset (included above) | 10 passed using isolated PostgreSQL schemas and real independent sessions. |
| Frontend `npm test` | TypeScript check passed; 33 tests passed (24 component tests and 9 upload validation cases). |
| Frontend lint / format check / production build | All passed. |
| Ruff lint / format for new backend regression file | Both passed. |
| `git diff --check` | Passed. |

The backend run used a unique temporary root because the existing pytest temp directory
belonged to another OS user. No application data was reset. Existing Starlette TestClient
`httpx` deprecation and Vite's bundle-size advisory remain. No manual/live-browser run,
coverage percentage, or external LLM benchmark was recorded; manual checklist boxes stay
unchecked until a tester supplies evidence.
