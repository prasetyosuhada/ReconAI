# API Specification
## ReconAI — Agentic AI Platform for Accounting Automation

**Version:** 1.0  
**Status:** Draft  
**Related Documents:** `docs/01-PRD.md`, `docs/02-System-Architecture.md`, `docs/03-Data-Model.md`, `docs/04-Agent-Design.md`  
**Document Owner:** Prasetyo Suhada

---

## 1. Purpose

This document defines the initial REST API specification for ReconAI. It describes the backend endpoints, request payloads, response payloads, error format, and workflow behavior required to support document intake, bookkeeping, human review, ledger posting, bank reconciliation, and audit traceability.

The API is designed for a portfolio-grade FastAPI backend and a Vite-based frontend SPA.

---

## 2. API Design Principles

| Principle | Description |
|---|---|
| Workflow-oriented endpoints | APIs should map to user-visible workflows, not only raw database tables. |
| Structured responses | Responses should be predictable and easy for the frontend to render. |
| AI suggestions are not final records | Agent outputs remain suggestions until validated and, when required, approved. |
| Deterministic validation is backend-owned | The backend validates journal entries, trial balance, and reconciliation rules. |
| Human review is explicit | Approval, edit, and rejection actions have dedicated endpoints. |
| Traceability is visible | API responses should include IDs that allow users to trace source documents, suggestions, review items, and audit events. |

---

## 3. General API Conventions

### 3.1 Base URL

For local development:

```text
http://localhost:8000/api/v1
```

### 3.2 Content Types

| Request Type | Content Type |
|---|---|
| JSON requests | `application/json` |
| File uploads | `multipart/form-data` |
| JSON responses | `application/json` |

### 3.3 Identifiers

All resource IDs should be UUID strings.

Example:

```json
{
  "id": "3d94ec55-52f5-47a7-9f72-33f3abf6f342"
}
```

### 3.4 Timestamps

Timestamps should use ISO 8601 format in UTC.

Example:

```json
{
  "created_at": "2026-07-26T08:30:00Z"
}
```

### 3.5 Money Values

Money values should be returned as numbers with two decimal places in API examples. The backend should store money using fixed-precision numeric types.

Example:

```json
{
  "amount": 499500.00,
  "currency": "IDR"
}
```

### 3.6 Pagination

List endpoints should support simple pagination.

Query parameters:

| Parameter | Type | Default | Description |
|---|---|---:|---|
| `limit` | Integer | `50` | Number of records to return. |
| `offset` | Integer | `0` | Number of records to skip. |

Paginated response envelope:

```json
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}
```

---

## 4. Error Format

All API errors should use a consistent response shape.

```json
{
  "error": {
    "code": "validation_error",
    "message": "The request payload is invalid.",
    "details": [
      {
        "field": "total_amount",
        "message": "Amount must be greater than zero."
      }
    ]
  }
}
```

Common error codes:

| Code | HTTP Status | Description |
|---|---:|---|
| `validation_error` | `400` | Request payload is invalid. |
| `not_found` | `404` | Resource does not exist. |
| `conflict` | `409` | Resource state does not allow the requested action. |
| `unsupported_file_type` | `415` | Uploaded file type is not supported. |
| `workflow_failed` | `500` | Workflow execution failed unexpectedly. |
| `provider_unavailable` | `503` | AI, OCR, or external provider is unavailable. |

---

## 5. Workflow Assumptions for Version 1

The first implementation should use these assumptions unless changed later:

| Topic | Version 1 Assumption |
|---|---|
| Workflow execution | Synchronous enough for demo flows; background workers are optional. |
| Currency | Default currency is `IDR`, configurable later. |
| Authentication | Out of scope or stubbed with a demo user. |
| AI provider | Provider-agnostic behind backend services. |
| OCR | Multimodal LLM or simple OCR abstraction; exact provider can change. |
| Audit snapshots | Store JSON snapshots for important agent and human decisions. |
| Review resume behavior | Approval or edit resumes the next downstream workflow step. |

---

## 6. Health Endpoint

### 6.1 `GET /health`

Checks whether the backend is running.

Response `200`:

```json
{
  "status": "ok",
  "service": "reconai-api",
  "version": "1.0.0"
}
```

---

## 7. Documents API

### 7.1 `POST /documents`

Uploads an invoice or receipt and starts document processing.

Request:

```text
multipart/form-data
file: invoice or receipt file
document_type: invoice | receipt | unknown
```

Supported file types:

- `application/pdf`
- `image/jpeg`
- `image/png`

Response `201`:

```json
{
  "id": "uuid",
  "original_filename": "office-supplies-receipt.pdf",
  "document_type": "receipt",
  "status": "extracting",
  "uploaded_at": "2026-07-26T08:30:00Z",
  "links": {
    "self": "/api/v1/documents/uuid",
    "audit_events": "/api/v1/audit-events?source_type=document&source_id=uuid"
  }
}
```

Behavior:

- Store file metadata and file reference.
- Create a `document_uploaded` audit event.
- Start the Document Intake Agent workflow.
- If extraction is high-confidence, continue to bookkeeping.
- If extraction needs review, create a review item.

### 7.2 `GET /documents`

Lists uploaded documents.

Query parameters:

| Parameter | Type | Required | Description |
|---|---|---:|---|
| `status` | String | No | Filter by document status. |
| `limit` | Integer | No | Pagination limit. |
| `offset` | Integer | No | Pagination offset. |

Response `200`:

```json
{
  "items": [
    {
      "id": "uuid",
      "original_filename": "office-supplies-receipt.pdf",
      "document_type": "receipt",
      "status": "bookkeeping_review_required",
      "uploaded_at": "2026-07-26T08:30:00Z",
      "created_at": "2026-07-26T08:30:00Z",
      "updated_at": "2026-07-26T08:30:10Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

### 7.3 `GET /documents/{document_id}`

Fetches a document and its latest workflow summary.

Response `200`:

```json
{
  "id": "uuid",
  "original_filename": "office-supplies-receipt.pdf",
  "mime_type": "application/pdf",
  "file_size_bytes": 245000,
  "document_type": "receipt",
  "status": "bookkeeping_review_required",
  "uploaded_at": "2026-07-26T08:30:00Z",
  "latest_extraction": {
    "id": "uuid",
    "vendor_name": "Acme Office Supply",
    "transaction_date": "2026-07-20",
    "subtotal_amount": 450000.00,
    "tax_amount": 49500.00,
    "total_amount": 499500.00,
    "currency": "IDR",
    "confidence_score": 0.91,
    "status": "approved"
  },
  "latest_journal_entry": {
    "id": "uuid",
    "status": "review_required",
    "confidence_score": 0.86
  },
  "pending_review_item_id": "uuid"
}
```

### 7.4 `POST /documents/{document_id}/retry`

Retries a failed document workflow.

Response `202`:

```json
{
  "document_id": "uuid",
  "status": "extracting",
  "message": "Document workflow retry started."
}
```

Allowed when:

- Document status is `failed`.

---

## 8. Extractions API

### 8.1 `GET /documents/{document_id}/extractions`

Lists extraction records for a document.

Response `200`:

```json
{
  "items": [
    {
      "id": "uuid",
      "document_id": "uuid",
      "vendor_name": "Acme Office Supply",
      "transaction_date": "2026-07-20",
      "total_amount": 499500.00,
      "currency": "IDR",
      "confidence_score": 0.91,
      "status": "approved",
      "created_at": "2026-07-26T08:30:05Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

### 8.2 `GET /extractions/{extraction_id}`

Fetches a single extraction record.

Response `200`:

```json
{
  "id": "uuid",
  "document_id": "uuid",
  "vendor_name": "Acme Office Supply",
  "transaction_date": "2026-07-20",
  "subtotal_amount": 450000.00,
  "tax_amount": 49500.00,
  "total_amount": 499500.00,
  "currency": "IDR",
  "line_items": [
    {
      "description": "Printer paper",
      "quantity": 5,
      "unit_price": 50000.00,
      "amount": 250000.00
    }
  ],
  "confidence_score": 0.91,
  "rationale": "The fields were clearly visible on the receipt.",
  "status": "approved",
  "created_at": "2026-07-26T08:30:05Z",
  "updated_at": "2026-07-26T08:30:05Z"
}
```

---

## 9. Review Items API

### 9.1 `GET /review-items`

Lists human review items.

Query parameters:

| Parameter | Type | Required | Description |
|---|---|---:|---|
| `status` | String | No | `pending`, `approved`, `edited`, `rejected`, or `cancelled`. |
| `review_type` | String | No | `extraction`, `bookkeeping`, `reconciliation`, or `validation`. |
| `limit` | Integer | No | Pagination limit. |
| `offset` | Integer | No | Pagination offset. |

Response `200`:

```json
{
  "items": [
    {
      "id": "uuid",
      "review_type": "bookkeeping",
      "status": "pending",
      "priority": "high",
      "source_type": "journal_entry",
      "source_id": "uuid",
      "title": "Review suggested journal entry",
      "summary": "Bank Account is sensitive and requires approval.",
      "suggested_action": "Approve or edit the journal entry before posting.",
      "created_at": "2026-07-26T08:30:10Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

### 9.2 `GET /review-items/{review_item_id}`

Fetches a review item with full payload details.

Response `200`:

```json
{
  "id": "uuid",
  "review_type": "bookkeeping",
  "status": "pending",
  "priority": "high",
  "source_type": "journal_entry",
  "source_id": "uuid",
  "title": "Review suggested journal entry",
  "summary": "Bank Account is sensitive and requires approval.",
  "suggested_action": "Approve or edit the journal entry before posting.",
  "original_payload": {
    "entry_date": "2026-07-20",
    "description": "Office supplies purchase from Acme Office Supply",
    "journal_lines": []
  },
  "edited_payload": null,
  "resolution_note": null,
  "created_at": "2026-07-26T08:30:10Z",
  "updated_at": "2026-07-26T08:30:10Z"
}
```

### 9.3 `POST /review-items/{review_item_id}/approve`

Approves an AI or system suggestion as-is.

Request:

```json
{
  "resolution_note": "Looks correct."
}
```

Response `200`:

```json
{
  "id": "uuid",
  "status": "approved",
  "resolved_at": "2026-07-26T08:35:00Z",
  "next_workflow_status": "posted",
  "message": "Review item approved."
}
```

Behavior by review type:

| Review Type | Behavior |
|---|---|
| `extraction` | Mark extraction approved and continue to bookkeeping. |
| `bookkeeping` | Re-run validation, then post if valid. |
| `reconciliation` | Accept proposed match or mark manual resolution. |
| `validation` | Re-run validation before continuing. |

### 9.4 `POST /review-items/{review_item_id}/edit`

Edits a suggestion and approves the edited payload.

Request:

```json
{
  "edited_payload": {
    "entry_date": "2026-07-20",
    "description": "Office supplies purchase from Acme Office Supply",
    "journal_lines": [
      {
        "account_code": "5100",
        "debit_amount": 499500.00,
        "credit_amount": 0.00,
        "description": "Office supplies expense"
      },
      {
        "account_code": "1010",
        "debit_amount": 0.00,
        "credit_amount": 499500.00,
        "description": "Payment from bank account"
      }
    ]
  },
  "resolution_note": "Adjusted line description."
}
```

Response `200`:

```json
{
  "id": "uuid",
  "status": "edited",
  "resolved_at": "2026-07-26T08:36:00Z",
  "next_workflow_status": "posted",
  "message": "Review item edited and approved."
}
```

### 9.5 `POST /review-items/{review_item_id}/reject`

Rejects a suggestion.

Request:

```json
{
  "resolution_note": "The transaction is not business-related."
}
```

Response `200`:

```json
{
  "id": "uuid",
  "status": "rejected",
  "resolved_at": "2026-07-26T08:37:00Z",
  "message": "Review item rejected."
}
```

Behavior:

- Mark review item as rejected.
- Mark related suggestion as rejected where applicable.
- Create a human rejection audit event.
- Do not continue downstream workflow automatically.

---

## 10. Ledger API

### 10.1 `GET /ledger/chart-of-accounts`

Lists active chart of accounts.

Response `200`:

```json
{
  "items": [
    {
      "id": "uuid",
      "account_code": "5100",
      "account_name": "Office Supplies Expense",
      "account_type": "expense",
      "normal_balance": "debit",
      "is_sensitive": false,
      "is_active": true
    }
  ],
  "total": 17,
  "limit": 50,
  "offset": 0
}
```

### 10.2 `GET /ledger/journal-entries`

Lists journal entries.

Query parameters:

| Parameter | Type | Required | Description |
|---|---|---:|---|
| `status` | String | No | Filter by status. |
| `document_id` | UUID | No | Filter by source document. |
| `limit` | Integer | No | Pagination limit. |
| `offset` | Integer | No | Pagination offset. |

Response `200`:

```json
{
  "items": [
    {
      "id": "uuid",
      "document_id": "uuid",
      "entry_date": "2026-07-20",
      "description": "Office supplies purchase from Acme Office Supply",
      "status": "posted",
      "source_type": "document",
      "confidence_score": 0.86,
      "posted_at": "2026-07-26T08:36:01Z",
      "total_debit": 499500.00,
      "total_credit": 499500.00
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

### 10.3 `GET /ledger/journal-entries/{journal_entry_id}`

Fetches one journal entry with lines.

Response `200`:

```json
{
  "id": "uuid",
  "document_id": "uuid",
  "extraction_id": "uuid",
  "entry_date": "2026-07-20",
  "description": "Office supplies purchase from Acme Office Supply",
  "status": "posted",
  "source_type": "document",
  "confidence_score": 0.86,
  "rationale": "The vendor and line items indicate office supplies.",
  "risk_flags": [
    {
      "type": "sensitive_account",
      "account_code": "1010",
      "message": "Bank Account requires human review."
    }
  ],
  "lines": [
    {
      "id": "uuid",
      "line_number": 1,
      "account_code": "5100",
      "account_name": "Office Supplies Expense",
      "debit_amount": 499500.00,
      "credit_amount": 0.00,
      "description": "Office supplies expense"
    },
    {
      "id": "uuid",
      "line_number": 2,
      "account_code": "1010",
      "account_name": "Bank Account",
      "debit_amount": 0.00,
      "credit_amount": 499500.00,
      "description": "Payment from bank account"
    }
  ],
  "posted_at": "2026-07-26T08:36:01Z",
  "created_at": "2026-07-26T08:30:09Z",
  "updated_at": "2026-07-26T08:36:01Z"
}
```

### 10.4 `POST /ledger/journal-entries/{journal_entry_id}/post`

Posts an approved journal entry.

Response `200`:

```json
{
  "id": "uuid",
  "status": "posted",
  "posted_at": "2026-07-26T08:36:01Z",
  "trial_balance_status": "balanced"
}
```

Allowed when:

- Journal entry status is `approved` or `ready_to_post`.
- Journal entry passes deterministic validation.
- Required review items are resolved.

### 10.5 `GET /ledger/trial-balance`

Returns trial balance validation status.

Response `200`:

```json
{
  "as_of_date": "2026-07-26",
  "status": "balanced",
  "total_debits": 499500.00,
  "total_credits": 499500.00,
  "difference": 0.00,
  "accounts": [
    {
      "account_code": "5100",
      "account_name": "Office Supplies Expense",
      "debit_balance": 499500.00,
      "credit_balance": 0.00
    },
    {
      "account_code": "1010",
      "account_name": "Bank Account",
      "debit_balance": 0.00,
      "credit_balance": 499500.00
    }
  ]
}
```

---

## 11. Bank Statements API

### 11.1 `POST /bank-statements/import`

Imports a mock bank statement CSV.

Request:

```text
multipart/form-data
file: bank statement CSV
```

Expected CSV columns:

```text
transaction_date,description,amount,currency,reference_number
```

Response `201`:

```json
{
  "id": "uuid",
  "original_filename": "bank-statement-july.csv",
  "status": "imported",
  "row_count": 12,
  "imported_at": "2026-07-26T09:00:00Z",
  "links": {
    "transactions": "/api/v1/bank-statements/uuid/transactions",
    "run_reconciliation": "/api/v1/reconciliation/run"
  }
}
```

### 11.2 `GET /bank-statements`

Lists bank statement imports.

Response `200`:

```json
{
  "items": [
    {
      "id": "uuid",
      "original_filename": "bank-statement-july.csv",
      "status": "partially_matched",
      "row_count": 12,
      "imported_at": "2026-07-26T09:00:00Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

### 11.3 `GET /bank-statements/{bank_statement_import_id}/transactions`

Lists bank transactions from an import.

Response `200`:

```json
{
  "items": [
    {
      "id": "uuid",
      "transaction_date": "2026-07-22",
      "description": "ACME OFFICE SUPPLY",
      "amount": -499500.00,
      "currency": "IDR",
      "reference_number": "BANK-001",
      "status": "matched"
    }
  ],
  "total": 12,
  "limit": 50,
  "offset": 0
}
```

---

## 12. Reconciliation API

### 12.1 `POST /reconciliation/run`

Runs reconciliation for one bank statement import.

Request:

```json
{
  "bank_statement_import_id": "uuid"
}
```

Response `202`:

```json
{
  "bank_statement_import_id": "uuid",
  "status": "matching_in_progress",
  "message": "Reconciliation workflow started."
}
```

Behavior:

- Load unreconciled bank transactions.
- Load candidate posted journal entries.
- Run deterministic and agent-assisted matching.
- Auto-accept high-confidence matches if deterministic checks pass.
- Create review items for possible matches and unmatched transactions.
- Create audit events for proposed and accepted matches.

### 12.2 `GET /reconciliation`

Lists reconciliation results.

Query parameters:

| Parameter | Type | Required | Description |
|---|---|---:|---|
| `bank_statement_import_id` | UUID | No | Filter by bank statement import. |
| `status` | String | No | Filter by match status. |
| `limit` | Integer | No | Pagination limit. |
| `offset` | Integer | No | Pagination offset. |

Response `200`:

```json
{
  "items": [
    {
      "id": "uuid",
      "bank_transaction": {
        "id": "uuid",
        "transaction_date": "2026-07-22",
        "description": "ACME OFFICE SUPPLY",
        "amount": -499500.00,
        "currency": "IDR",
        "status": "matched"
      },
      "journal_entry": {
        "id": "uuid",
        "entry_date": "2026-07-20",
        "description": "Office supplies purchase from Acme Office Supply"
      },
      "match_type": "fuzzy",
      "status": "accepted",
      "confidence_score": 0.94,
      "amount_score": 1.00,
      "date_score": 0.90,
      "vendor_score": 0.92,
      "rationale": "Exact amount match, close date, and similar vendor description."
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

### 12.3 `GET /reconciliation/{reconciliation_match_id}`

Fetches a reconciliation match.

Response `200`:

```json
{
  "id": "uuid",
  "bank_transaction_id": "uuid",
  "journal_entry_id": "uuid",
  "match_type": "fuzzy",
  "status": "accepted",
  "confidence_score": 0.94,
  "amount_score": 1.00,
  "date_score": 0.90,
  "vendor_score": 0.92,
  "rationale": "Exact amount match, close date, and similar vendor description.",
  "created_by": "agent",
  "resolved_at": "2026-07-26T09:00:10Z",
  "created_at": "2026-07-26T09:00:08Z",
  "updated_at": "2026-07-26T09:00:10Z"
}
```

### 12.4 `POST /reconciliation/{reconciliation_match_id}/accept`

Accepts a proposed reconciliation match directly.

Request:

```json
{
  "resolution_note": "Confirmed this is the correct match."
}
```

Response `200`:

```json
{
  "id": "uuid",
  "status": "accepted",
  "resolved_at": "2026-07-26T09:05:00Z",
  "message": "Reconciliation match accepted."
}
```

Notes:

- This endpoint is useful for a direct reconciliation UI.
- The Review Items API may also resolve reconciliation matches.

### 12.5 `POST /reconciliation/{reconciliation_match_id}/reject`

Rejects a proposed reconciliation match.

Request:

```json
{
  "resolution_note": "The vendor is similar, but the amount belongs to another transaction."
}
```

Response `200`:

```json
{
  "id": "uuid",
  "status": "rejected",
  "resolved_at": "2026-07-26T09:06:00Z",
  "message": "Reconciliation match rejected."
}
```

---

## 13. Audit Events API

### 13.1 `GET /audit-events`

Lists audit events.

Query parameters:

| Parameter | Type | Required | Description |
|---|---|---:|---|
| `source_type` | String | No | Filter by related entity type. |
| `source_id` | UUID | No | Filter by related entity ID. |
| `event_type` | String | No | Filter by event type. |
| `actor_type` | String | No | `agent`, `human`, or `system`. |
| `limit` | Integer | No | Pagination limit. |
| `offset` | Integer | No | Pagination offset. |

Response `200`:

```json
{
  "items": [
    {
      "id": "uuid",
      "event_type": "journal_entry_suggested",
      "source_type": "journal_entry",
      "source_id": "uuid",
      "actor_type": "agent",
      "actor_name": "bookkeeping_agent",
      "rationale": "The vendor and line items indicate office supplies.",
      "confidence_score": 0.86,
      "human_action": null,
      "created_at": "2026-07-26T08:30:10Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

### 13.2 `GET /audit-events/{audit_event_id}`

Fetches one audit event with snapshots.

Response `200`:

```json
{
  "id": "uuid",
  "event_type": "journal_entry_suggested",
  "source_type": "journal_entry",
  "source_id": "uuid",
  "actor_type": "agent",
  "actor_name": "bookkeeping_agent",
  "input_snapshot": {
    "vendor_name": "Acme Office Supply",
    "total_amount": 499500.00,
    "currency": "IDR"
  },
  "output_snapshot": {
    "entry_date": "2026-07-20",
    "journal_lines": []
  },
  "rationale": "The vendor and line items indicate office supplies.",
  "confidence_score": 0.86,
  "human_action": null,
  "created_at": "2026-07-26T08:30:10Z"
}
```

---

## 14. Dashboard Summary API

### 14.1 `GET /dashboard/summary`

Returns a compact summary for the frontend dashboard or primary demo view.

Response `200`:

```json
{
  "documents": {
    "total": 5,
    "pending_review": 1,
    "posted": 3,
    "failed": 0
  },
  "review_items": {
    "pending": 2,
    "high_priority": 1
  },
  "ledger": {
    "posted_entries": 3,
    "trial_balance_status": "balanced"
  },
  "reconciliation": {
    "bank_transactions": 12,
    "matched": 8,
    "pending_review": 3,
    "unmatched": 1
  }
}
```

---

## 15. State Transition Rules

### 15.1 Document Status Transitions

| Current Status | Allowed Next Status |
|---|---|
| `uploaded` | `extracting`, `failed` |
| `extracting` | `extraction_review_required`, `extracted`, `failed` |
| `extraction_review_required` | `extracted`, `failed` |
| `extracted` | `bookkeeping_in_progress`, `failed` |
| `bookkeeping_in_progress` | `bookkeeping_review_required`, `ready_to_post`, `failed` |
| `bookkeeping_review_required` | `ready_to_post`, `failed` |
| `ready_to_post` | `posted`, `failed` |
| `posted` | No automatic transition in version 1. |
| `failed` | `extracting` through retry. |

### 15.2 Review Status Transitions

| Current Status | Allowed Next Status |
|---|---|
| `pending` | `approved`, `edited`, `rejected`, `cancelled` |
| `approved` | No transition. |
| `edited` | No transition. |
| `rejected` | No transition. |
| `cancelled` | No transition. |

### 15.3 Journal Entry Status Transitions

| Current Status | Allowed Next Status |
|---|---|
| `draft` | `review_required`, `approved`, `rejected` |
| `review_required` | `approved`, `rejected` |
| `approved` | `posted` |
| `posted` | No direct edit in version 1. |
| `rejected` | No automatic transition. |
| `voided` | No automatic transition. |

---

## 16. Validation Rules by Endpoint

| Endpoint | Key Validation |
|---|---|
| `POST /documents` | File type, file size, document type. |
| `POST /review-items/{id}/approve` | Review item must be pending and source must still exist. |
| `POST /review-items/{id}/edit` | Edited payload must pass source-specific schema validation. |
| `POST /ledger/journal-entries/{id}/post` | Entry must balance and required reviews must be resolved. |
| `POST /bank-statements/import` | CSV columns, parseable dates, numeric amounts. |
| `POST /reconciliation/run` | Bank statement import must exist and have transactions. |
| `POST /reconciliation/{id}/accept` | Match must be proposed or review required. |

---

## 17. Open Questions

These questions can be resolved during implementation:

1. Should workflow-triggering endpoints return only immediate state, or wait for synchronous agent completion in demo mode?
2. Should `POST /documents` automatically run bookkeeping after high-confidence extraction, or should the frontend trigger that separately?
3. Should reconciliation review be handled only through Review Items API, or also through direct reconciliation accept/reject endpoints?
4. Should draft journal entries be manually creatable through the API in version 1?
5. Should API responses include full nested objects by default, or keep nesting minimal and let the frontend fetch details separately?
6. Should audit snapshots be returned by default or only on detail endpoints?

---

## 18. Next Document

The next recommended document is `06-UX-Flow.md`, which should define the frontend screens, user interactions, review patterns, and demo-oriented navigation flow.
