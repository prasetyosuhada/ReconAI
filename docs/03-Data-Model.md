# Data Model
## ReconAI — Agentic AI Platform for Accounting Automation

**Version:** 1.0  
**Status:** Draft  
**Related Documents:** `docs/01-PRD.md`, `docs/02-System-Architecture.md`  
**Document Owner:** Prasetyo Suhada

---

## 1. Purpose

This document defines the initial data model for ReconAI. It describes the core entities, relationships, fields, status values, and validation rules needed to support the document intake, bookkeeping, human review, reconciliation, and audit traceability workflows.

The model is designed for a portfolio-grade implementation using PostgreSQL as the primary system of record.

---

## 2. Modeling Principles

| Principle | Description |
|---|---|
| Financial records are explicit | Journal entries, journal lines, accounts, and reconciliation results should be stored as structured records, not only as JSON blobs. |
| AI output is a suggestion first | Agent outputs should be persisted separately from final approved ledger records where appropriate. |
| Human decisions are traceable | Approvals, edits, and rejections should be stored and linked to the related AI suggestion. |
| Audit events are append-only | Corrections should create new audit events instead of mutating historical audit records. |
| Deterministic validation is enforceable | The schema should support backend validation for balanced journal entries and reconciliation state. |
| JSON is allowed for snapshots | Flexible JSON fields may be used for AI input/output snapshots, OCR results, and provider-specific metadata. |

---

## 3. Entity Relationship Overview

```text
documents
  │
  ├── document_extractions
  │       │
  │       └── journal_entries
  │              │
  │              └── journal_entry_lines
  │                       │
  │                       └── chart_of_accounts
  │
  └── review_items

bank_statement_imports
  │
  └── bank_transactions
          │
          └── reconciliation_matches
                    │
                    └── journal_entries

review_items
  ├── documents
  ├── document_extractions
  ├── journal_entries
  ├── bank_transactions
  └── reconciliation_matches

audit_events
  └── references any workflow entity through source_type + source_id
```

---

## 4. Core Tables

### 4.1 `documents`

Stores uploaded invoice or receipt metadata.

| Field | Type | Required | Description |
|---|---|---:|---|
| `id` | UUID | Yes | Primary key. |
| `original_filename` | Text | Yes | Filename from upload. |
| `stored_file_path` | Text | Yes | Internal storage location. |
| `mime_type` | Text | Yes | Uploaded file MIME type. |
| `file_size_bytes` | Integer | Yes | File size in bytes. |
| `document_type` | Text | Yes | `invoice`, `receipt`, or `unknown`. |
| `status` | Text | Yes | Current document workflow state. |
| `uploaded_at` | Timestamp | Yes | Upload timestamp. |
| `created_at` | Timestamp | Yes | Record creation timestamp. |
| `updated_at` | Timestamp | Yes | Last update timestamp. |

Recommended indexes:

- `idx_documents_status` on `status`.
- `idx_documents_uploaded_at` on `uploaded_at`.

Recommended statuses:

- `uploaded`
- `extracting`
- `extraction_review_required`
- `extracted`
- `bookkeeping_in_progress`
- `bookkeeping_review_required`
- `ready_to_post`
- `posted`
- `failed`

---

### 4.2 `document_extractions`

Stores structured extraction results produced by the Document Intake Agent.

| Field | Type | Required | Description |
|---|---|---:|---|
| `id` | UUID | Yes | Primary key. |
| `document_id` | UUID | Yes | Foreign key to `documents.id`. |
| `vendor_name` | Text | No | Extracted vendor name. |
| `transaction_date` | Date | No | Extracted transaction date. |
| `subtotal_amount` | Numeric(14,2) | No | Extracted subtotal. |
| `tax_amount` | Numeric(14,2) | No | Extracted tax amount. |
| `total_amount` | Numeric(14,2) | No | Extracted total amount. |
| `currency` | Text | Yes | ISO currency code, default `IDR` or configured demo currency. |
| `line_items` | JSONB | No | Extracted line item details. |
| `raw_text` | Text | No | OCR text or model-extracted text. |
| `provider_metadata` | JSONB | No | Provider-specific metadata such as model name or OCR details. |
| `confidence_score` | Numeric(5,4) | Yes | Extraction confidence from `0.0000` to `1.0000`. |
| `rationale` | Text | No | Human-readable extraction notes. |
| `status` | Text | Yes | Extraction lifecycle status. |
| `created_at` | Timestamp | Yes | Record creation timestamp. |
| `updated_at` | Timestamp | Yes | Last update timestamp. |

Recommended indexes:

- `idx_document_extractions_document_id` on `document_id`.
- `idx_document_extractions_status` on `status`.

Recommended statuses:

- `draft`
- `review_required`
- `approved`
- `rejected`
- `superseded`

Notes:

- Multiple extraction records may exist for one document if a user edits or reruns extraction.
- The currently accepted extraction should be the latest `approved` extraction unless the backend later adds an explicit pointer.

---

### 4.3 `chart_of_accounts`

Stores the chart of accounts used by the Bookkeeping Agent and ledger services.

| Field | Type | Required | Description |
|---|---|---:|---|
| `id` | UUID | Yes | Primary key. |
| `account_code` | Text | Yes | Human-readable account code, unique. |
| `account_name` | Text | Yes | Account display name. |
| `account_type` | Text | Yes | `asset`, `liability`, `equity`, `revenue`, or `expense`. |
| `normal_balance` | Text | Yes | `debit` or `credit`. |
| `is_sensitive` | Boolean | Yes | Whether use of this account always requires human review. |
| `is_active` | Boolean | Yes | Whether the account can be used for new entries. |
| `description` | Text | No | Optional explanation for AI and UI context. |
| `created_at` | Timestamp | Yes | Record creation timestamp. |
| `updated_at` | Timestamp | Yes | Last update timestamp. |

Recommended indexes and constraints:

- Unique index on `account_code`.
- `idx_chart_of_accounts_account_type` on `account_type`.
- `idx_chart_of_accounts_is_active` on `is_active`.

---

### 4.4 `journal_entries`

Stores draft and posted journal entries.

| Field | Type | Required | Description |
|---|---|---:|---|
| `id` | UUID | Yes | Primary key. |
| `document_id` | UUID | No | Optional foreign key to `documents.id`. |
| `extraction_id` | UUID | No | Optional foreign key to `document_extractions.id`. |
| `entry_date` | Date | Yes | Accounting date. |
| `description` | Text | Yes | Journal entry description. |
| `status` | Text | Yes | `draft`, `review_required`, `approved`, `posted`, `rejected`, or `voided`. |
| `source_type` | Text | Yes | `document`, `manual`, `import`, or `system`. |
| `agent_name` | Text | No | Agent that generated the draft entry. |
| `confidence_score` | Numeric(5,4) | No | Bookkeeping confidence from `0.0000` to `1.0000`. |
| `rationale` | Text | No | AI-generated accounting rationale. |
| `risk_flags` | JSONB | No | Flags such as sensitive account use or low confidence. |
| `posted_at` | Timestamp | No | Timestamp when posted. |
| `created_at` | Timestamp | Yes | Record creation timestamp. |
| `updated_at` | Timestamp | Yes | Last update timestamp. |

Recommended indexes:

- `idx_journal_entries_status` on `status`.
- `idx_journal_entries_entry_date` on `entry_date`.
- `idx_journal_entries_document_id` on `document_id`.
- `idx_journal_entries_extraction_id` on `extraction_id`.

Notes:

- A journal entry is not financially authoritative until it reaches `posted`.
- Posting should only occur after deterministic debit-credit validation and required human approval.

---

### 4.5 `journal_entry_lines`

Stores debit and credit lines for each journal entry.

| Field | Type | Required | Description |
|---|---|---:|---|
| `id` | UUID | Yes | Primary key. |
| `journal_entry_id` | UUID | Yes | Foreign key to `journal_entries.id`. |
| `account_id` | UUID | Yes | Foreign key to `chart_of_accounts.id`. |
| `line_number` | Integer | Yes | Ordering within the journal entry. |
| `description` | Text | No | Optional line-level description. |
| `debit_amount` | Numeric(14,2) | Yes | Debit amount, default `0.00`. |
| `credit_amount` | Numeric(14,2) | Yes | Credit amount, default `0.00`. |
| `created_at` | Timestamp | Yes | Record creation timestamp. |
| `updated_at` | Timestamp | Yes | Last update timestamp. |

Recommended indexes and constraints:

- `idx_journal_entry_lines_journal_entry_id` on `journal_entry_id`.
- `idx_journal_entry_lines_account_id` on `account_id`.
- Unique index on `(journal_entry_id, line_number)`.
- Check that `debit_amount >= 0`.
- Check that `credit_amount >= 0`.
- Check that each line has either debit or credit, but not both.

Validation rule:

- The backend must ensure `sum(debit_amount) = sum(credit_amount)` for every posted journal entry.

---

### 4.6 `bank_statement_imports`

Stores metadata for imported mock bank statement CSV files.

| Field | Type | Required | Description |
|---|---|---:|---|
| `id` | UUID | Yes | Primary key. |
| `original_filename` | Text | Yes | CSV filename from upload. |
| `stored_file_path` | Text | No | Optional internal storage location. |
| `status` | Text | Yes | Import lifecycle status. |
| `imported_at` | Timestamp | Yes | Import timestamp. |
| `row_count` | Integer | Yes | Number of parsed rows. |
| `created_at` | Timestamp | Yes | Record creation timestamp. |
| `updated_at` | Timestamp | Yes | Last update timestamp. |

Recommended statuses:

- `imported`
- `validation_failed`
- `matching_in_progress`
- `matched`
- `partially_matched`
- `failed`

---

### 4.7 `bank_transactions`

Stores parsed transactions from mock bank statement imports.

| Field | Type | Required | Description |
|---|---|---:|---|
| `id` | UUID | Yes | Primary key. |
| `bank_statement_import_id` | UUID | Yes | Foreign key to `bank_statement_imports.id`. |
| `transaction_date` | Date | Yes | Bank transaction date. |
| `description` | Text | Yes | Bank transaction description. |
| `amount` | Numeric(14,2) | Yes | Signed amount. Positive may represent inflow, negative outflow. |
| `currency` | Text | Yes | ISO currency code. |
| `reference_number` | Text | No | Optional bank reference. |
| `status` | Text | Yes | Reconciliation status. |
| `created_at` | Timestamp | Yes | Record creation timestamp. |
| `updated_at` | Timestamp | Yes | Last update timestamp. |

Recommended indexes:

- `idx_bank_transactions_import_id` on `bank_statement_import_id`.
- `idx_bank_transactions_status` on `status`.
- `idx_bank_transactions_transaction_date` on `transaction_date`.
- `idx_bank_transactions_amount` on `amount`.

Recommended statuses:

- `imported`
- `matched`
- `possible_match_review_required`
- `unmatched_review_required`
- `resolved`

---

### 4.8 `reconciliation_matches`

Stores proposed and accepted matches between bank transactions and journal entries.

| Field | Type | Required | Description |
|---|---|---:|---|
| `id` | UUID | Yes | Primary key. |
| `bank_transaction_id` | UUID | Yes | Foreign key to `bank_transactions.id`. |
| `journal_entry_id` | UUID | No | Candidate or accepted foreign key to `journal_entries.id`. |
| `match_type` | Text | Yes | `exact`, `fuzzy`, `manual`, or `unmatched`. |
| `status` | Text | Yes | Match lifecycle status. |
| `confidence_score` | Numeric(5,4) | No | Match confidence from `0.0000` to `1.0000`. |
| `amount_score` | Numeric(5,4) | No | Amount similarity score. |
| `date_score` | Numeric(5,4) | No | Date proximity score. |
| `vendor_score` | Numeric(5,4) | No | Vendor or description similarity score. |
| `rationale` | Text | No | Agent or system explanation. |
| `created_by` | Text | Yes | `agent`, `human`, or `system`. |
| `resolved_at` | Timestamp | No | Timestamp when accepted, rejected, or manually resolved. |
| `created_at` | Timestamp | Yes | Record creation timestamp. |
| `updated_at` | Timestamp | Yes | Last update timestamp. |

Recommended indexes:

- `idx_reconciliation_matches_bank_transaction_id` on `bank_transaction_id`.
- `idx_reconciliation_matches_journal_entry_id` on `journal_entry_id`.
- `idx_reconciliation_matches_status` on `status`.

Recommended statuses:

- `proposed`
- `review_required`
- `accepted`
- `rejected`
- `superseded`
- `unmatched`

Notes:

- A bank transaction may have multiple proposed candidate matches.
- Only one accepted match should exist per bank transaction in the initial implementation.

---

### 4.9 `review_items`

Stores human-in-the-loop review tasks.

| Field | Type | Required | Description |
|---|---|---:|---|
| `id` | UUID | Yes | Primary key. |
| `review_type` | Text | Yes | `extraction`, `bookkeeping`, `reconciliation`, or `validation`. |
| `status` | Text | Yes | Review lifecycle status. |
| `priority` | Text | Yes | `low`, `normal`, `high`. |
| `source_type` | Text | Yes | Entity type being reviewed. |
| `source_id` | UUID | Yes | Entity ID being reviewed. |
| `title` | Text | Yes | Short review item title for the UI. |
| `summary` | Text | No | Human-readable review summary. |
| `suggested_action` | Text | No | Suggested next action. |
| `original_payload` | JSONB | No | AI or system output before human action. |
| `edited_payload` | JSONB | No | Human-edited output, if applicable. |
| `resolution_note` | Text | No | Optional human note. |
| `resolved_by` | Text | No | Demo user identifier or name. |
| `resolved_at` | Timestamp | No | Resolution timestamp. |
| `created_at` | Timestamp | Yes | Record creation timestamp. |
| `updated_at` | Timestamp | Yes | Last update timestamp. |

Recommended statuses:

- `pending`
- `approved`
- `edited`
- `rejected`
- `cancelled`

Recommended indexes:

- `idx_review_items_status` on `status`.
- `idx_review_items_review_type` on `review_type`.
- `idx_review_items_source` on `(source_type, source_id)`.

Notes:

- `source_type` and `source_id` allow review items to point at different workflow entities without requiring many nullable foreign keys.
- The backend should validate that the referenced source exists before creating a review item.

---

### 4.10 `audit_events`

Stores append-only traceability events for agent decisions, system validations, and human actions.

| Field | Type | Required | Description |
|---|---|---:|---|
| `id` | UUID | Yes | Primary key. |
| `event_type` | Text | Yes | Type of event. |
| `source_type` | Text | Yes | Related entity type. |
| `source_id` | UUID | Yes | Related entity ID. |
| `actor_type` | Text | Yes | `agent`, `human`, or `system`. |
| `actor_name` | Text | No | Agent name, service name, or demo user name. |
| `input_snapshot` | JSONB | No | Relevant input at the time of decision. |
| `output_snapshot` | JSONB | No | Result of the decision or action. |
| `rationale` | Text | No | Human-readable explanation. |
| `confidence_score` | Numeric(5,4) | No | Confidence score if applicable. |
| `human_action` | Text | No | `approved`, `edited`, `rejected`, or null. |
| `created_at` | Timestamp | Yes | Event timestamp. |

Recommended indexes:

- `idx_audit_events_source` on `(source_type, source_id)`.
- `idx_audit_events_event_type` on `event_type`.
- `idx_audit_events_created_at` on `created_at`.

Recommended event types:

- `document_uploaded`
- `extraction_started`
- `extraction_completed`
- `extraction_review_required`
- `bookkeeping_started`
- `journal_entry_suggested`
- `journal_entry_validation_failed`
- `journal_entry_posted`
- `bank_statement_imported`
- `reconciliation_started`
- `reconciliation_match_proposed`
- `reconciliation_match_accepted`
- `review_item_created`
- `human_approved`
- `human_edited`
- `human_rejected`
- `workflow_failed`

---

## 5. Optional Tables

These tables are not required for the first implementation, but may become useful as the project grows.

### 5.1 `agent_runs`

Tracks individual agent invocations for debugging and observability.

Useful fields:

- `id`
- `workflow_type`
- `agent_name`
- `model_name`
- `status`
- `started_at`
- `completed_at`
- `latency_ms`
- `input_tokens`
- `output_tokens`
- `error_message`

### 5.2 `workflow_runs`

Tracks complete orchestrated workflows across multiple agents.

Useful fields:

- `id`
- `workflow_type`
- `source_type`
- `source_id`
- `status`
- `started_at`
- `completed_at`
- `current_step`
- `error_message`

### 5.3 `accounting_periods`

Supports period-based ledger reporting if the demo later expands toward financial statements.

Useful fields:

- `id`
- `period_name`
- `start_date`
- `end_date`
- `status`

---

## 6. Seed Chart of Accounts

The first demo should use a small but realistic chart of accounts.

| Account Code | Account Name | Type | Normal Balance | Sensitive |
|---|---|---|---|---:|
| `1000` | Cash | Asset | Debit | Yes |
| `1010` | Bank Account | Asset | Debit | Yes |
| `1100` | Accounts Receivable | Asset | Debit | No |
| `1200` | Inventory | Asset | Debit | No |
| `1300` | Prepaid Expenses | Asset | Debit | No |
| `1400` | PPN Masukan (Input VAT) | Asset | Debit | No |
| `2000` | Accounts Payable | Liability | Credit | No |
| `2100` | Tax Payable | Liability | Credit | Yes |
| `2200` | Loans Payable | Liability | Credit | Yes |
| `3000` | Owner Equity | Equity | Credit | Yes |
| `4000` | Sales Revenue | Revenue | Credit | No |
| `5000` | Cost of Goods Sold | Expense | Debit | No |
| `5100` | Office Supplies Expense | Expense | Debit | No |
| `5200` | Meals and Entertainment Expense | Expense | Debit | No |
| `5300` | Travel Expense | Expense | Debit | No |
| `5400` | Software Subscription Expense | Expense | Debit | No |
| `5900` | Miscellaneous Expense | Expense | Debit | No |
| `9999` | Suspense Account | Asset | Debit | Yes |

Notes:

- `Bank Account`, `Cash`, `Tax Payable`, `Loans Payable`, `Owner Equity`, and `Suspense Account` should require review.
- `Suspense Account` should only be used when the system cannot confidently classify a transaction.

---

## 7. Important Relationships

| Relationship | Cardinality | Notes |
|---|---|---|
| `documents` → `document_extractions` | One-to-many | A document may be extracted multiple times. |
| `documents` → `journal_entries` | One-to-many | One document may create one or more accounting entries. |
| `document_extractions` → `journal_entries` | One-to-many | Accepted extraction data may be used to draft entries. |
| `journal_entries` → `journal_entry_lines` | One-to-many | Each journal entry must have at least two lines. |
| `chart_of_accounts` → `journal_entry_lines` | One-to-many | Each line references one account. |
| `bank_statement_imports` → `bank_transactions` | One-to-many | Each import contains many bank transactions. |
| `bank_transactions` → `reconciliation_matches` | One-to-many | A transaction can have several candidate matches. |
| `journal_entries` → `reconciliation_matches` | One-to-many | A journal entry may be proposed for multiple bank transactions, but accepted matching should be controlled. |
| `review_items` → workflow entities | Polymorphic | Uses `source_type` and `source_id`. |
| `audit_events` → workflow entities | Polymorphic | Uses `source_type` and `source_id`. |

---

## 8. Validation Rules

The backend should enforce these rules before records become authoritative.

### 8.1 Journal Entry Rules

- A posted journal entry must have at least two lines.
- A journal entry line must have either a debit amount or credit amount, but not both.
- Debit and credit amounts must be non-negative.
- Total debits must equal total credits before posting.
- A journal entry touching a sensitive account must require human approval.
- A rejected journal entry must not be posted.
- A posted journal entry should not be edited directly; create a reversal or correcting entry if needed in future versions.

### 8.2 Extraction Rules

- Extraction confidence must be between `0.0000` and `1.0000`.
- Low-confidence extractions must create a review item.
- Approved extraction data should preserve the original AI output through audit events or snapshots.

### 8.3 Reconciliation Rules

- Match confidence must be between `0.0000` and `1.0000`.
- A high-confidence match may be auto-accepted only if it passes deterministic checks.
- Low-confidence or ambiguous matches must create review items.
- Only one accepted reconciliation match should exist per bank transaction in the initial implementation.
- Rejected proposed matches should remain available for audit traceability.

### 8.4 Audit Rules

- Audit events should be append-only.
- Any agent decision that affects workflow state should create an audit event.
- Any human approval, edit, or rejection should create an audit event.
- Audit snapshots should include enough context to understand the decision without relying only on the current state of mutable records.

---

## 9. Status and Enum Reference

The implementation may use text columns first for speed, then move to database enums later if useful.

| Concept | Values |
|---|---|
| Document type | `invoice`, `receipt`, `unknown` |
| Document status | `uploaded`, `extracting`, `extraction_review_required`, `extracted`, `bookkeeping_in_progress`, `bookkeeping_review_required`, `ready_to_post`, `posted`, `failed` |
| Extraction status | `draft`, `review_required`, `approved`, `rejected`, `superseded` |
| Account type | `asset`, `liability`, `equity`, `revenue`, `expense` |
| Normal balance | `debit`, `credit` |
| Journal entry status | `draft`, `review_required`, `approved`, `posted`, `rejected`, `voided` |
| Source type | `document`, `manual`, `import`, `system` |
| Bank import status | `imported`, `validation_failed`, `matching_in_progress`, `matched`, `partially_matched`, `failed` |
| Bank transaction status | `imported`, `matched`, `possible_match_review_required`, `unmatched_review_required`, `resolved` |
| Reconciliation match type | `exact`, `fuzzy`, `manual`, `unmatched` |
| Reconciliation match status | `proposed`, `review_required`, `accepted`, `rejected`, `superseded`, `unmatched` |
| Review type | `extraction`, `bookkeeping`, `reconciliation`, `validation` |
| Review status | `pending`, `approved`, `edited`, `rejected`, `cancelled` |
| Review priority | `low`, `normal`, `high` |
| Actor type | `agent`, `human`, `system` |

---

## 10. Example Data Flow

### 10.1 Uploaded Receipt

1. A user uploads `office-supplies-receipt.pdf`.
2. The backend creates a `documents` record with status `uploaded`.
3. The Document Intake Agent creates a `document_extractions` record.
4. If extraction confidence is high, the extraction status becomes `approved`.
5. The Bookkeeping Agent creates a `journal_entries` draft with two or more `journal_entry_lines`.
6. The Trial Balance Service validates debit equals credit.
7. If review is required, a `review_items` record is created.
8. After approval, the journal entry status becomes `posted`.
9. Each important step writes an `audit_events` record.

### 10.2 Bank Transaction Reconciliation

1. A user imports a mock CSV bank statement.
2. The backend creates one `bank_statement_imports` record.
3. Each CSV row becomes a `bank_transactions` record.
4. The Reconciliation Agent creates one or more `reconciliation_matches` records.
5. High-confidence matches become `accepted`.
6. Ambiguous matches become `review_required` and create `review_items`.
7. Human resolution updates match status and creates an `audit_events` record.

---

## 11. Implementation Notes

- Use UUID primary keys for all core tables.
- Use `created_at` and `updated_at` consistently for mutable records.
- Use `created_at` only for append-only audit events.
- Use `Numeric(14,2)` for money amounts in the initial implementation.
- Store confidence scores as `Numeric(5,4)` to support values from `0.0000` to `1.0000`.
- Prefer explicit relational fields for accounting records.
- Use JSONB for AI snapshots, flexible line items, risk flags, and provider metadata.
- Keep uploaded file contents out of the database for the first version.
- Add database migrations once the backend structure is created.

---

## 12. Open Questions

These questions can be answered before implementation or refined during the first migration design:

1. Should the first demo use `IDR` as the default currency, or a provider-neutral default such as `USD`?
2. Should the app store full OCR text for every document, or only extracted structured fields?
3. Should edited extraction results create a new `document_extractions` row or update the existing row with audit history?
4. Should journal entry corrections be supported in version 1, or should posted entries be immutable for the demo?
5. Should reconciliation support one-to-many matching, such as one bank payment covering multiple invoices, in the first version?
6. Should `agent_runs` and `workflow_runs` be part of version 1, or added only after the core workflow works?
7. Should audit snapshots store full payloads or only selected fields to keep records smaller?

---

## 13. Next Document

The next recommended document is `04-Agent-Design.md`, which should define each agent's responsibilities, input/output schemas, prompts, confidence behavior, tools, and handoff rules.
