# Test Plan & Evaluation Strategy
## ReconAI — Agentic AI Platform for Accounting Automation

**Version:** 1.0  
**Status:** Draft  
**Related Documents:** `docs/01-PRD.md`, `docs/04-Agent-Design.md`  
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
  - Include low-quality/blurry photos.
  - Include edge cases (e.g., multiple tax rates, multi-page invoices).
- **Mock Bank Statements:** CSV files containing bank transactions that correspond to the sample documents.
  - **Exact Matches:** Perfect 1:1 match on amount, date, and vendor.
  - **Fuzzy Matches:** Slight date drift (± 2 days) or minor vendor name variations (e.g., "AWS" vs "Amazon Web Services").
  - **Unmatched Items:** Transactions with no corresponding ledger entry.
- **Golden Dataset:** A set of pre-defined expected outputs (ground truth) for extraction, categorization, and reconciliation to measure agent accuracy programmatically.

---

## 3. Traditional Testing (Deterministic)

### 3.1 Backend & Orchestration (FastAPI + LangGraph)
- **API Endpoints:** 
  - Test `/api/upload`, `/api/review`, `/api/reconcile` for expected HTTP status codes, payload validation, and error handling.
- **Accounting Engine (Critical):** 
  - **Double-Entry Validation:** Assert that any function creating a journal entry fails if Debits ≠ Credits.
  - **Trial Balance:** Verify that ledger posting correctly updates the running balance.
- **Database Operations:** Test CRUD operations for documents, journal entries, and the audit log.
- **State Management:** Ensure LangGraph maintains context correctly between the Intake, Bookkeeping, and Reconciliation nodes.

### 3.2 Frontend (Vite/React)
- **UI Components:** Test document upload drag-and-drop, review queue rendering, and approval/rejection button actions.
- **Human-in-the-Loop Flow:** Ensure the UI correctly reflects the "Awaiting Review" state and updates optimistically when a user approves a suggestion.

---

## 4. AI Agent Evaluation Strategy

Because LLM outputs can vary, we will evaluate the agents based on accuracy metrics against the Golden Dataset.

### 4.1 Document Intake Agent
- **Metric:** Extraction Accuracy (Precision & Recall).
- **Test:** Run the agent against the 20-30 sample documents.
- **Criteria:** 
  - **High Accuracy:** Subtotal, Tax, and Total Amount must have 95%+ accuracy. Vendor Name & Date > 90%.
  - **Confidence Calibration:** Ensure low-quality documents correctly produce low confidence scores (e.g., < 0.8) and successfully trigger the human review queue.

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

---

## 5. End-to-End (E2E) Workflow Testing

To validate the entire system, the following E2E scenarios must pass:

**Scenario: The Happy Path with Human Review**
1. Upload `sample_invoice_01.pdf`.
2. Verify Document Intake Agent extracts data and pauses for Human Review (due to configured rules).
3. User approves data via UI.
4. Verify Bookkeeping Agent drafts a journal entry and pauses for Review.
5. User approves journal entry via UI.
6. Verify entry is posted to the Ledger and Trial Balance remains balanced.
7. Upload `mock_bank_statement.csv`.
8. Verify Reconciliation Agent matches the entry correctly.
9. Check **Audit Log** to ensure all steps, AI confidence scores, and human actions are recorded with correct timestamps.

---

## 6. Tools & Frameworks

- **Backend Testing:** `pytest` for unit and integration testing.
- **Frontend Testing:** `Vitest` and `React Testing Library`.
- **LLM Evaluation:** Custom Python scripts (or evaluation frameworks like `LangSmith` / `DeepEval` / `Ragas`) to automate running agents against the Golden Dataset, calculating accuracy metrics, and checking for regressions when prompts are updated.
