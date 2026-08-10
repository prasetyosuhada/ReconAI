# Product Requirements Document (PRD)
## ReconAI — Agentic AI Platform for Accounting Automation

**Version:** 1.0
**Status:** Draft
**Type:** Portfolio Project
**Document Owner:** Prasetyo Suhada

---

## 1. Overview

### 1.1 Problem Statement
Small and medium businesses (SMBs) spend significant manual effort on repetitive bookkeeping tasks: reading invoices/receipts, coding transactions to the correct chart of accounts (COA), and reconciling bank statements against internal records. These tasks are rule-based, high-volume, and error-prone when done manually, yet they still require judgment that simple automation (e.g. plain OCR or fixed rules engines) cannot reliably provide.

### 1.2 Product Vision
ReconAI is an agentic AI platform that automates the core bookkeeping workflow — from raw financial documents to reconciled, audit-traceable ledger entries — using a coordinated set of specialized AI agents rather than a single monolithic model. The system prioritizes transparency (every AI decision is explainable and traceable) and human oversight (low-confidence or high-risk actions are routed to a human for approval).

### 1.3 Goals for This Project
- Demonstrate a working end-to-end agentic pipeline: document upload → data extraction → categorization/journal entry → reconciliation.
- Showcase multi-agent orchestration with clear task boundaries, not just a single LLM wrapper.
- Showcase human-in-the-loop design patterns appropriate for a finance-adjacent domain.
- Produce a project that is demoable in under 5 minutes and technically defensible in an interview/portfolio review.

### 1.4 Non-Goals
- Tax computation or regulatory filing (PPN, PPh, e-Faktur, e-Bupot, etc.)
- Full financial statement generation (Income Statement, Balance Sheet, Cash Flow)
- External/independent audit workflows
- Multi-tenant production-grade security/compliance (SOC 2, data residency, etc.)
- Real bank API integrations (mock/sample data will be used instead)

---

## 2. Target Users (for narrative/demo purposes)

| Persona | Description | Need |
|---|---|---|
| SMB Owner | Runs a small business, does bookkeeping themselves or with 1 part-time staff | Wants faster, less error-prone way to record transactions |
| Bookkeeper/Accountant | Handles day-to-day entries for one or more small clients | Wants to reduce manual data entry and speed up reconciliation |

---

## 3. Scope

### 3.1 In Scope (Tier 1 — Core)

**A. Document Intake Agent**
- Accepts uploaded documents: invoices, receipts (image or PDF)
- Extracts structured data: vendor name, date, line items, subtotal, tax, total amount
- Flags low-confidence extractions for human review

**B. Bookkeeping Agent**
- Takes extracted document data and:
  - Suggests the appropriate COA account(s) for the transaction
  - Generates a double-entry journal entry (debit/credit)
  - Provides a natural-language rationale for the categorization decision
  - Runs trial balance validation (debit total = credit total) after posting

### 3.2 In Scope (Tier 2 — Differentiator)

**C. Reconciliation Agent**
- Ingests a (mock) bank statement dataset
- Attempts to match bank transactions against posted ledger entries
- For unmatched items, performs a secondary investigation pass: fuzzy amount/date matching, vendor-name similarity, flags as "possible match" with a confidence score, or "unmatched — needs review"

**D. Supervisor/Orchestrator**
- Coordinates handoff between agents (Intake → Bookkeeping → Reconciliation)
- Maintains shared state/context across agent calls
- Routes items to a human-approval queue based on confidence thresholds or risk rules

**E. Human-in-the-Loop Review UI**
- Queue of AI suggestions awaiting approval (extraction results, categorization suggestions, reconciliation matches)
- User can Approve / Edit / Reject each item
- Rejections/edits are logged and can optionally inform future suggestions

**F. Audit/Traceability Log**
- Every agent decision is logged with: input reference, decision output, rationale, confidence score, timestamp, and human action taken (if any)

### 3.3 Out of Scope
- Tax/Compliance Agent
- Full financial statement (P&L, Balance Sheet, Cash Flow) generation
- Audit/review agent for independent assurance
- Production-grade multi-tenant auth, encryption-at-rest compliance, etc.

---

## 4. User Flow (End-to-End)

1. User uploads a document (invoice/receipt image or PDF).
2. **Document Intake Agent** extracts structured data and returns a confidence score.
   - If confidence is low → item goes to human review queue.
3. **Bookkeeping Agent** receives extracted data, suggests COA account(s), and drafts a journal entry with rationale.
   - If confidence is low or the entry affects a sensitive account → item goes to human review queue.
4. User (via Review UI) approves, edits, or rejects the suggested entry.
5. Approved entry is posted to the ledger; trial balance is re-validated.
6. User uploads/loads a bank statement (mock dataset).
7. **Reconciliation Agent** matches bank transactions to posted ledger entries.
   - High-confidence matches are auto-marked as reconciled.
   - Low-confidence or unmatched items go to human review queue with candidate suggestions.
8. User resolves remaining items via Review UI.
9. All agent decisions across the flow are visible in the **Audit Log** view, traceable back to the source document/transaction.

---

## 5. Functional Requirements

### 5.1 Document Intake Agent
| ID | Requirement |
|---|---|
| FR-1.1 | System shall accept image (JPG/PNG) and PDF uploads of invoices/receipts |
| FR-1.2 | System shall extract: vendor name, transaction date, line items, subtotal, tax amount, total amount |
| FR-1.3 | System shall return a confidence score for the extraction |
| FR-1.4 | System shall flag extractions below a configurable confidence threshold for human review |

### 5.2 Bookkeeping Agent
| ID | Requirement |
|---|---|
| FR-2.1 | System shall suggest one or more COA accounts for a given transaction |
| FR-2.2 | System shall generate a balanced double-entry journal entry (debit = credit) |
| FR-2.3 | System shall provide a natural-language rationale for the account suggestion |
| FR-2.4 | System shall validate that the running trial balance remains balanced after posting |
| FR-2.5 | System shall flag entries below a confidence threshold, or touching designated "sensitive" accounts, for human review |

### 5.3 Reconciliation Agent
| ID | Requirement |
|---|---|
| FR-3.1 | System shall ingest a mock bank statement dataset (CSV) |
| FR-3.2 | System shall attempt to match each bank transaction to a posted ledger entry |
| FR-3.3 | System shall support fuzzy matching on amount, date proximity, and vendor-name similarity |
| FR-3.4 | System shall assign a confidence score to each match |
| FR-3.5 | System shall present unmatched or low-confidence items with candidate suggestions for human resolution |

### 5.4 Orchestration & Human-in-the-Loop
| ID | Requirement |
|---|---|
| FR-4.1 | System shall maintain shared context/state as data passes between agents |
| FR-4.2 | System shall route low-confidence or high-risk outputs to a human review queue |
| FR-4.3 | System shall allow users to Approve, Edit, or Reject any AI-suggested item |
| FR-4.4 | System shall persist human decisions and reflect them in downstream state (e.g., posted ledger) |

### 5.5 Audit & Traceability
| ID | Requirement |
|---|---|
| FR-5.1 | System shall log every agent decision with: source reference, output, rationale, confidence score, and timestamp |
| FR-5.2 | System shall log the human action (if any) taken on each AI suggestion |
| FR-5.3 | System shall allow a user to trace any ledger entry back to its originating document and the agent decisions involved |

---

## 6. Non-Functional Requirements

| Category | Requirement |
|---|---|
| Explainability | Every AI suggestion must include a human-readable rationale, not just a raw output |
| Transparency | Confidence scores must be visible wherever AI makes a judgment call |
| Reliability | Trial balance validation must be deterministic and always run after any posting |
| Latency | Document extraction and categorization should complete within a few seconds for a good demo experience |
| Auditability | All agent actions must be logged in a way that is queryable and traceable |

---

## 7. Proposed Architecture (High Level)

```
┌─────────────────────┐
│   Supervisor /       │
│   Orchestrator       │
└─────────┬────────────┘
          │
 ┌────────┼─────────────────────┐
 │        │                     │
 ▼        ▼                     ▼
┌────────────┐  ┌────────────┐  ┌──────────────────┐
│ Document   │→ │ Bookkeeping│→ │ Reconciliation    │
│ Intake     │  │ Agent      │  │ Agent             │
│ Agent      │  │            │  │                   │
└────────────┘  └────────────┘  └──────────────────┘
       │               │                │
       ▼               ▼                ▼
   ┌─────────────────────────────────────────┐
   │     Human Review Queue / Approval UI     │
   └─────────────────────────────────────────┘
                       │
                       ▼
              ┌──────────────────┐
              │   Audit Log       │
              └──────────────────┘
```

### 7.1 Suggested Tech Stack
- **Agent orchestration:** LangGraph (supervisor pattern) or equivalent multi-agent framework
- **LLM:** Gemini-2.5-flash or GPT-5.4
- **Backend:** FastAPI + `uv` (per existing project conventions)
- **Database:** PostgreSQL (ledger, COA, audit log)
- **Frontend:** Vite-based SPA for upload, review queue, and audit log views
- **Containerization:** Docker Compose (existing reconai stack)

---

## 8. Success Metrics (for portfolio demo purposes)

| Metric | Target |
|---|---|
| Extraction accuracy on sample invoice set | Demonstrable and explainable, even if not perfect |
| End-to-end flow completion (upload → reconciled) | Fully working demo, < 5 minutes |
| Traceability | Any ledger entry can be traced to source document + agent rationale |
| Human-in-the-loop coverage | Every low-confidence/high-risk item is routed to review, none silently auto-approved |

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| LLM hallucinates extraction data | Confidence scoring + mandatory human review below threshold |
| Miscategorized journal entries break trial balance | Deterministic trial balance validation as a hard gate, not just AI judgment |
| Reconciliation false-positive matches | Confidence threshold + human review for anything below high confidence |
| Scope creep into tax/compliance | Explicitly out of scope for this version; documented as future work |

---

## 10. Future Work (Not in Current Scope)
- Tax & Compliance Agent (PPN/PPh calculation, human-approved filing drafts)
- Financial statement generation agent (P&L, Balance Sheet, Cash Flow)
- Real bank API integrations
- Multi-tenant, production-grade security and compliance posture