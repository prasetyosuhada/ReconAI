# System Architecture
## ReconAI — Agentic AI Platform for Accounting Automation

**Version:** 1.0  
**Status:** Draft  
**Related Document:** `docs/01-PRD.md`  
**Document Owner:** Prasetyo Suhada

---

## 1. Purpose

This document describes the high-level technical architecture for ReconAI, an agentic AI platform for accounting automation. It translates the product requirements into an implementation-oriented system design covering application layers, core services, agent orchestration, data flow, persistence, and operational boundaries.

The architecture is intentionally scoped for a portfolio-grade implementation: realistic enough to demonstrate strong engineering judgment, but not overbuilt for production-grade multi-tenant compliance.

---

## 2. Architectural Goals

ReconAI should be designed around the following principles:

| Goal | Description |
|---|---|
| Agentic separation of concerns | Each AI agent should own a clear task boundary: document extraction, bookkeeping, reconciliation, or supervision. |
| Human oversight | Low-confidence or high-risk AI outputs must be routed to a human review queue before becoming authoritative records. |
| Deterministic financial validation | Critical accounting rules, such as debit-credit balance validation, must be enforced by deterministic code, not by an LLM. |
| Traceability | Every AI-generated decision must be logged with source input, output, rationale, confidence score, timestamp, and human action. |
| Demo readiness | The system should support a polished end-to-end flow that can be demonstrated in under five minutes. |
| Replaceable AI providers | LLM and OCR providers should be abstracted enough that the implementation can switch providers without rewriting business logic. |

---

## 3. High-Level Architecture

ReconAI follows a layered architecture:

1. **Frontend SPA**
   - Provides upload, review queue, ledger, reconciliation, and audit log screens.
   - Communicates with the backend through REST APIs.

2. **Backend API**
   - Exposes application workflows through FastAPI endpoints.
   - Owns authentication stubs, request validation, persistence coordination, and workflow triggering.

3. **Agent Orchestration Layer**
   - Coordinates task execution across specialized agents.
   - Maintains workflow state and determines when human review is required.

4. **Domain Services**
   - Encapsulate deterministic accounting and reconciliation logic.
   - Validate journal entries, trial balance, review decisions, and reconciliation outcomes.

5. **Persistence Layer**
   - Stores source documents, extracted data, ledger records, bank transactions, review items, and audit logs.

6. **External AI/OCR Providers**
   - Provide document understanding, text extraction, classification suggestions, and natural-language rationales.

---

## 4. System Context Diagram

```text
┌────────────────────┐
│       User         │
│ SMB Owner /        │
│ Bookkeeper         │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│   Frontend SPA     │
│ Upload, Review,    │
│ Ledger, Audit      │
└─────────┬──────────┘
          │ REST / JSON
          ▼
┌──────────────────────────────────────────┐
│              Backend API                 │
│ FastAPI application services             │
└─────────┬──────────────────────┬─────────┘
          │                      │
          ▼                      ▼
┌────────────────────┐   ┌────────────────────┐
│ Agent Orchestrator │   │ Domain Services    │
│ Supervisor graph   │   │ Accounting rules   │
└─────────┬──────────┘   └─────────┬──────────┘
          │                        │
          ▼                        ▼
┌────────────────────┐   ┌────────────────────┐
│ AI / OCR Providers │   │ PostgreSQL         │
│ LLM, vision, OCR   │   │ System of record   │
└────────────────────┘   └────────────────────┘
```

---

## 5. Core Components

### 5.1 Frontend SPA

The frontend should be a Vite-based single-page application. Its primary purpose is to make the agentic workflow visible and reviewable.

Expected views:

| View | Responsibility |
|---|---|
| Document Upload | Upload invoice or receipt files and show processing status. |
| Review Queue | Display pending AI suggestions that require human approval, edit, or rejection. |
| Ledger | Show posted journal entries and trial balance status. |
| Reconciliation | Show bank transactions, matched ledger entries, candidate matches, and unresolved items. |
| Audit Log | Show the trace of agent decisions and human actions. |

The frontend should not contain accounting business logic. It may perform lightweight client-side validation for usability, but authoritative validation must happen in the backend.

### 5.2 Backend API

The backend should be implemented with FastAPI. It acts as the application boundary for all workflows.

Core responsibilities:

- Accept file uploads and bank statement CSV imports.
- Trigger agent workflows through the orchestrator.
- Persist intermediate and final workflow results.
- Expose review queue actions.
- Enforce deterministic validation before posting ledger entries.
- Serve audit log and traceability data.

The API should treat AI outputs as suggestions until they pass validation and, when required, human approval.

### 5.3 Agent Orchestrator

The orchestrator coordinates multi-step workflows across agents. LangGraph is a strong fit because the system requires explicit state transitions, conditional routing, and human-in-the-loop pauses.

Responsibilities:

- Maintain workflow state across agent calls.
- Route work from Document Intake Agent to Bookkeeping Agent.
- Trigger Reconciliation Agent after bank statement ingestion.
- Apply confidence and risk thresholds.
- Create review queue items when human approval is required.
- Emit audit events for every agent decision.

The orchestrator should not contain detailed accounting rules. It decides the next step in the workflow, while domain services validate financial correctness.

### 5.4 Document Intake Agent

The Document Intake Agent extracts structured financial data from uploaded documents.

Input:

- Uploaded invoice or receipt file.
- Optional OCR text if extracted separately.
- Document metadata.

Output:

- Vendor name.
- Transaction date.
- Line items.
- Subtotal.
- Tax amount.
- Total amount.
- Extraction confidence score.
- Rationale or extraction notes.

If confidence is below the configured threshold, the agent output becomes a review queue item instead of flowing directly into bookkeeping.

### 5.5 Bookkeeping Agent

The Bookkeeping Agent converts extracted transaction data into accounting suggestions.

Input:

- Extracted document data.
- Chart of accounts.
- Existing ledger context, if needed.

Output:

- Suggested account classification.
- Draft double-entry journal entry.
- Natural-language rationale.
- Confidence score.
- Risk flags, such as sensitive account usage.

All generated journal entries must be validated by deterministic accounting services before posting.

### 5.6 Reconciliation Agent

The Reconciliation Agent matches bank statement transactions against posted ledger entries.

Input:

- Mock bank statement transactions.
- Posted ledger entries.
- Existing reconciliation status.

Output:

- High-confidence matches.
- Possible matches with candidate ledger entries.
- Unmatched transactions.
- Confidence score and rationale for each decision.

High-confidence matches may be auto-marked as reconciled. Low-confidence and unmatched items must be sent to human review.

### 5.7 Domain Services

Domain services contain deterministic business rules. These services should be ordinary application code, not agent prompts.

Recommended services:

| Service | Responsibility |
|---|---|
| Ledger Service | Create, post, and query journal entries. |
| Trial Balance Service | Validate debit and credit equality after posting. |
| Review Service | Create and resolve human review items. |
| Reconciliation Service | Apply deterministic match scoring and persist reconciliation status. |
| Audit Service | Record agent decisions, system events, and human actions. |
| COA Service | Manage and query the chart of accounts. |

### 5.8 Persistence Layer

PostgreSQL should be the primary database for structured data. Uploaded files may be stored locally for the portfolio version, with file metadata stored in PostgreSQL.

Recommended storage approach:

| Data | Storage |
|---|---|
| Uploaded documents | Local filesystem or object-storage-compatible abstraction |
| Document metadata | PostgreSQL |
| Extracted transaction data | PostgreSQL |
| Chart of accounts | PostgreSQL seed data |
| Journal entries | PostgreSQL |
| Bank transactions | PostgreSQL |
| Reconciliation matches | PostgreSQL |
| Review queue items | PostgreSQL |
| Audit events | PostgreSQL |

---

## 6. End-to-End Workflow

### 6.1 Document to Ledger Flow

```text
User uploads document
        │
        ▼
Backend stores document metadata and file reference
        │
        ▼
Orchestrator invokes Document Intake Agent
        │
        ▼
Extraction result persisted and audit event recorded
        │
        ├── Low confidence → Review Queue
        │
        ▼
Orchestrator invokes Bookkeeping Agent
        │
        ▼
Draft journal entry persisted and audit event recorded
        │
        ├── Low confidence / sensitive account → Review Queue
        │
        ▼
Domain service validates debit = credit
        │
        ▼
Approved journal entry posted to ledger
        │
        ▼
Trial balance validation runs
```

### 6.2 Bank Reconciliation Flow

```text
User imports mock bank statement CSV
        │
        ▼
Backend validates and stores bank transactions
        │
        ▼
Orchestrator invokes Reconciliation Agent
        │
        ▼
Agent proposes matches and confidence scores
        │
        ├── High confidence → Auto-mark as reconciled
        │
        └── Low confidence / unmatched → Review Queue
        │
        ▼
Human resolves remaining review items
        │
        ▼
Audit log records final action and reconciliation status
```

---

## 7. Suggested Backend Module Structure

The exact structure may change during implementation, but this layout keeps agent logic, API routes, and domain services separated.

```text
backend/
  app/
    main.py
    api/
      routes/
        documents.py
        review.py
        ledger.py
        reconciliation.py
        audit.py
    agents/
      orchestrator.py
      document_intake.py
      bookkeeping.py
      reconciliation.py
      schemas.py
    services/
      ledger_service.py
      trial_balance_service.py
      review_service.py
      reconciliation_service.py
      audit_service.py
      coa_service.py
    models/
      document.py
      extraction.py
      ledger.py
      bank_transaction.py
      review_item.py
      audit_event.py
    db/
      session.py
      migrations/
    settings.py
```

---

## 8. Suggested Frontend Structure

```text
frontend/
  src/
    app/
      routes.tsx
    api/
      client.ts
      documents.ts
      review.ts
      ledger.ts
      reconciliation.ts
      audit.ts
    pages/
      DocumentUploadPage.tsx
      ReviewQueuePage.tsx
      LedgerPage.tsx
      ReconciliationPage.tsx
      AuditLogPage.tsx
    components/
      FileUpload.tsx
      ReviewItemPanel.tsx
      JournalEntryTable.tsx
      ConfidenceBadge.tsx
      AuditTimeline.tsx
    types/
      api.ts
```

---

## 9. API Surface Overview

Detailed API contracts should be documented separately in `05-API-Spec.md`. At a high level, the backend should expose:

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/documents` | Upload invoice or receipt. |
| `GET` | `/documents/{document_id}` | Fetch document processing status and extracted data. |
| `GET` | `/review-items` | List pending human review items. |
| `POST` | `/review-items/{review_item_id}/approve` | Approve an AI suggestion. |
| `POST` | `/review-items/{review_item_id}/edit` | Edit and approve a suggestion. |
| `POST` | `/review-items/{review_item_id}/reject` | Reject a suggestion. |
| `GET` | `/ledger/journal-entries` | List posted and draft journal entries. |
| `GET` | `/ledger/trial-balance` | Fetch trial balance validation status. |
| `POST` | `/bank-statements/import` | Import mock bank statement CSV. |
| `POST` | `/reconciliation/run` | Run reconciliation workflow. |
| `GET` | `/reconciliation` | Fetch reconciliation results. |
| `GET` | `/audit-events` | Fetch audit trail events. |

---

## 10. Workflow State Model

The orchestrator should treat each uploaded document or bank statement import as a workflow with explicit state.

Recommended document workflow states:

| State | Meaning |
|---|---|
| `uploaded` | Document file has been received and stored. |
| `extracting` | Document Intake Agent is processing the file. |
| `extraction_review_required` | Extraction result needs human review. |
| `extracted` | Extraction result is accepted. |
| `bookkeeping_in_progress` | Bookkeeping Agent is creating a journal entry suggestion. |
| `bookkeeping_review_required` | Journal entry suggestion needs human review. |
| `ready_to_post` | Journal entry is valid and approved. |
| `posted` | Journal entry has been posted to the ledger. |
| `failed` | Workflow failed and requires investigation. |

Recommended reconciliation states:

| State | Meaning |
|---|---|
| `imported` | Bank statement data has been loaded. |
| `matching_in_progress` | Reconciliation Agent is matching transactions. |
| `matched` | Transaction has a high-confidence match. |
| `possible_match_review_required` | Candidate match needs human review. |
| `unmatched_review_required` | No reliable match was found. |
| `resolved` | Human has resolved the reconciliation item. |

---

## 11. Confidence and Review Routing

Confidence thresholds should be configurable. A reasonable initial setup:

| Decision Type | Auto-Approve Threshold | Review Condition |
|---|---:|---|
| Document extraction | `>= 0.85` | Confidence below `0.85` |
| Account classification | `>= 0.80` | Confidence below `0.80` |
| Journal entry posting | N/A | Any validation failure or sensitive account usage |
| Reconciliation match | `>= 0.90` | Confidence below `0.90` or no match found |

Sensitive accounts should always require review, regardless of confidence. Examples:

- Cash.
- Loans payable.
- Owner equity.
- Tax payable.
- Suspense account.
- Manual adjustment account.

---

## 12. Audit Logging

Audit logging is a core feature, not an implementation detail. Every meaningful agent or human decision should create an audit event.

Recommended audit event fields:

| Field | Description |
|---|---|
| `id` | Unique event identifier. |
| `event_type` | Agent decision, human approval, human edit, validation failure, posting, reconciliation decision, etc. |
| `source_type` | Document, extraction, journal entry, bank transaction, reconciliation match, review item. |
| `source_id` | Identifier of the related record. |
| `agent_name` | Name of the agent, if applicable. |
| `input_snapshot` | JSON snapshot of the relevant input. |
| `output_snapshot` | JSON snapshot of the generated output. |
| `rationale` | Human-readable explanation for the decision. |
| `confidence_score` | Numeric confidence score, if applicable. |
| `human_action` | Approved, edited, rejected, or null. |
| `created_at` | Timestamp of the event. |

Audit entries should be append-only for the portfolio implementation. If a correction is needed, write a new event instead of mutating the original event.

---

## 13. Error Handling Strategy

Errors should be visible and recoverable where possible.

| Error Type | Handling |
|---|---|
| Invalid upload format | Reject request with clear validation error. |
| OCR or LLM provider failure | Mark workflow as failed and create audit event. |
| Low-confidence AI result | Route to review queue. |
| Invalid journal entry | Block posting and create review item. |
| Trial balance failure | Block posting and create audit event. |
| CSV parsing error | Reject import with row-level error details where possible. |
| Reconciliation ambiguity | Route candidate matches to human review. |

---

## 14. Security and Privacy Scope

For the portfolio version, ReconAI should include basic safety practices without claiming production-grade compliance.

Recommended baseline:

- Validate uploaded file type and size.
- Store uploaded files outside frontend-accessible paths.
- Avoid logging raw secrets or API keys.
- Use environment variables for provider credentials.
- Keep audit logs focused on workflow traceability.
- Use sample or synthetic financial documents for demos.

Explicitly out of scope:

- Multi-tenant authorization.
- SOC 2 controls.
- Data residency guarantees.
- Encryption-at-rest compliance program.
- Real bank API connectivity.

---

## 15. Deployment Model

For local development and demo purposes, Docker Compose should run the full stack.

Recommended services:

```text
docker-compose.yml
  frontend
  backend
  postgres
```

Optional services:

```text
  worker
  redis
```

A background worker is optional for the first implementation. If agent calls are slow or need retry handling, agent workflows can later be moved from synchronous API requests into a worker queue.

---

## 16. Key Design Decisions

| Decision | Rationale |
|---|---|
| FastAPI backend | Simple, typed, Python-native backend suitable for AI and data workflows. |
| Vite SPA frontend | Fast development loop and polished demo experience. |
| PostgreSQL system of record | Strong fit for relational accounting data and audit trails. |
| LangGraph-style orchestration | Supports explicit multi-agent workflows, conditional routing, and human-in-the-loop pauses. |
| Deterministic ledger validation | Accounting correctness should not depend on LLM judgment. |
| Append-only audit events | Provides a credible traceability story with simple implementation. |
| Mock bank statements | Keeps demo scope focused while still showing reconciliation logic. |

---

## 17. Open Questions

These questions should be answered during implementation planning:

1. Which AI provider will be used first for document extraction and reasoning?
2. Should OCR be handled by the same multimodal LLM or by a dedicated OCR library/provider?
3. Should agent workflows run synchronously during the demo, or through a background worker?
4. What sample chart of accounts should be used for the first demo?
5. What confidence score format should be standardized across agents?
6. How much extracted document detail should be editable in the review UI?
7. Should audit logs store full JSON snapshots or normalized references plus selected fields?

---

## 18. Next Documents

The following documents should build on this architecture:

| Document | Purpose |
|---|---|
| `03-Data-Model.md` | Defines tables, relationships, key fields, and seed data. |
| `04-Agent-Design.md` | Defines each agent's input/output schema, prompts, tools, and routing behavior. |
| `05-API-Spec.md` | Defines detailed request/response contracts. |
| `06-UX-Flow.md` | Defines screens and user interactions for the demo. |
| `07-Demo-Plan.md` | Defines the portfolio demo script and sample data flow. |
| `08-Test-Plan.md` | Defines validation and test coverage for critical workflows. |
