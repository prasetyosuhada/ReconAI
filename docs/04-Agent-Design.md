# Agent Design
## ReconAI — Agentic AI Platform for Accounting Automation

**Version:** 1.0  
**Status:** Draft  
**Related Documents:** `docs/01-PRD.md`, `docs/02-System-Architecture.md`, `docs/03-Data-Model.md`  
**Document Owner:** Prasetyo Suhada

---

## 1. Purpose

This document defines the design of ReconAI's agentic workflow. It describes each agent's responsibility, input and output schema, handoff rules, confidence behavior, review routing, and deterministic guardrails.

The goal is to make the system clearly agentic without allowing AI components to become the source of financial truth. Agents generate structured suggestions and rationales. Backend services validate, persist, and enforce accounting rules.

---

## 2. Agent Design Principles

| Principle | Description |
|---|---|
| Narrow agent responsibilities | Each agent should own one clear job and produce a structured output. |
| Structured outputs over prose | Agent responses should be parsed into typed schemas, not interpreted from free-form text. |
| Deterministic validation after AI | Accounting correctness must be enforced by backend services. |
| Confidence is explicit | Every judgment-oriented agent output should include a confidence score and rationale. |
| Human review is first-class | Low-confidence, ambiguous, or high-risk outputs must create review items. |
| Audit everything important | Agent decisions, validation outcomes, and human actions must create audit events. |
| Provider replaceability | Prompting and provider-specific details should be isolated from domain services. |

---

## 3. Agent Overview

| Agent | Primary Responsibility | Main Input | Main Output |
|---|---|---|---|
| Supervisor / Orchestrator | Coordinate workflow state and agent handoff. | Workflow state, entity IDs, thresholds. | Next step, review routing, persisted state updates. |
| Document Intake Agent | Extract structured financial data from invoices and receipts. | Uploaded file, OCR text, document metadata. | Extraction result with confidence and rationale. |
| Bookkeeping Agent | Suggest COA classification and draft journal entry. | Approved extraction, COA, ledger context. | Draft journal entry, confidence, rationale, risk flags. |
| Reconciliation Agent | Match bank transactions to posted journal entries. | Bank transactions, posted ledger entries. | Exact matches, possible matches, unmatched items. |

Optional future agents are intentionally excluded from version 1:

- Tax and Compliance Agent.
- Financial Statement Agent.
- Independent Audit Review Agent.

---

## 4. Orchestration Model

The orchestrator should be implemented as an explicit state machine or graph. LangGraph is the recommended implementation pattern, but the design can also be implemented with ordinary application services first.

### 4.1 Document Workflow

```text
uploaded
  │
  ▼
extracting
  │
  ├── extraction confidence below threshold
  │       ▼
  │   extraction_review_required
  │       │
  │       ▼
  │   extracted
  │
  ▼
extracted
  │
  ▼
bookkeeping_in_progress
  │
  ├── low confidence / sensitive account / validation issue
  │       ▼
  │   bookkeeping_review_required
  │       │
  │       ▼
  │   ready_to_post
  │
  ▼
ready_to_post
  │
  ▼
posted
```

### 4.2 Reconciliation Workflow

```text
bank statement imported
  │
  ▼
matching_in_progress
  │
  ├── high-confidence match
  │       ▼
  │   matched
  │
  ├── possible match
  │       ▼
  │   possible_match_review_required
  │       │
  │       ▼
  │   resolved
  │
  └── unmatched
          ▼
      unmatched_review_required
          │
          ▼
      resolved
```

### 4.3 Orchestrator Responsibilities

The orchestrator should:

- Load workflow state and related records.
- Invoke the correct agent for the current step.
- Validate agent output against a schema.
- Persist agent output through backend services.
- Apply confidence thresholds and risk rules.
- Create review items when human approval is required.
- Stop workflow execution when review is required.
- Resume workflow execution after human approval or edit.
- Create audit events for agent decisions and state transitions.

The orchestrator should not:

- Decide accounting correctness by itself.
- Bypass trial balance validation.
- Post entries directly from LLM output.
- Hide low-confidence or ambiguous results from the user.

---

## 5. Shared Agent Output Contract

Every agent should return a predictable envelope.

```json
{
  "agent_name": "document_intake_agent",
  "status": "completed",
  "confidence_score": 0.92,
  "rationale": "The vendor, date, and total were clearly visible in the document.",
  "warnings": [],
  "result": {}
}
```

Recommended fields:

| Field | Type | Required | Description |
|---|---|---:|---|
| `agent_name` | String | Yes | Stable agent identifier. |
| `status` | String | Yes | `completed`, `needs_review`, or `failed`. |
| `confidence_score` | Number | Yes | Score from `0.0000` to `1.0000`. |
| `rationale` | String | Yes | Concise human-readable explanation. |
| `warnings` | Array | Yes | Non-fatal issues or ambiguity notes. |
| `result` | Object | Yes | Agent-specific structured result. |

Confidence score rules:

- Use `1.0000` only when the result is completely deterministic or unambiguous.
- Use lower confidence when document quality, missing fields, ambiguous account mapping, or fuzzy matching affects reliability.
- Confidence must describe the agent's certainty in its own output, not whether the business event is important.

---

## 6. Document Intake Agent

### 6.1 Responsibility

The Document Intake Agent extracts structured transaction data from an uploaded invoice or receipt.

It should identify:

- Vendor name.
- Transaction date.
- Line items.
- Subtotal.
- Tax amount.
- Total amount.
- Currency.
- Document type.

### 6.2 Inputs

```json
{
  "document_id": "uuid",
  "original_filename": "office-supplies-receipt.pdf",
  "mime_type": "application/pdf",
  "file_reference": "uploads/documents/...",
  "ocr_text": "optional extracted text",
  "demo_currency": "IDR"
}
```

### 6.3 Output Schema

```json
{
  "agent_name": "document_intake_agent",
  "status": "completed",
  "confidence_score": 0.91,
  "rationale": "The document has a clear vendor name, date, subtotal, tax, and total.",
  "warnings": [],
  "result": {
    "document_type": "receipt",
    "vendor_name": "Acme Office Supply",
    "transaction_date": "2026-07-20",
    "currency": "IDR",
    "subtotal_amount": 450000.00,
    "tax_amount": 49500.00,
    "total_amount": 499500.00,
    "line_items": [
      {
        "description": "Printer paper",
        "quantity": 5,
        "unit_price": 50000.00,
        "amount": 250000.00
      }
    ],
    "extraction_notes": "Line item quantity was visible. Tax appears to be 11% VAT."
  }
}
```

### 6.4 Tools and Dependencies

Possible tools:

- PDF text extraction.
- OCR or multimodal document understanding.
- LLM structured extraction.

The first implementation may use a multimodal LLM directly for simplicity. If OCR is separated later, the OCR result should be passed into the agent as `ocr_text`.

### 6.5 Confidence Heuristics

Confidence should decrease when:

- Vendor name is missing or partially visible.
- Transaction date is missing or ambiguous.
- Total amount is inferred rather than directly visible.
- Subtotal plus tax does not equal total.
- Currency is unclear.
- OCR text is noisy.
- The document looks unlike an invoice or receipt.

Recommended routing:

| Condition | Action |
|---|---|
| Confidence `>= 0.85` and required fields present | Continue to Bookkeeping Agent. |
| Confidence `< 0.85` | Create extraction review item. |
| Required financial fields missing | Create extraction review item. |
| Total amount cannot be determined | Create extraction review item. |

### 6.6 Guardrails

- The agent must not invent missing totals.
- The agent must mark uncertain fields through warnings.
- The agent must preserve ambiguity rather than forcing a clean answer.
- The backend should validate numeric consistency where possible.

---

## 7. Bookkeeping Agent

### 7.1 Responsibility

The Bookkeeping Agent converts approved extraction data into an accounting suggestion.

It should:

- Select one or more chart of accounts.
- Draft a double-entry journal entry.
- Provide an accounting rationale.
- Identify sensitive accounts or risky classifications.

### 7.2 Inputs

```json
{
  "document_id": "uuid",
  "extraction_id": "uuid",
  "vendor_name": "Acme Office Supply",
  "transaction_date": "2026-07-20",
  "total_amount": 499500.00,
  "currency": "IDR",
  "line_items": [],
  "chart_of_accounts": [
    {
      "id": "uuid",
      "account_code": "5100",
      "account_name": "Office Supplies Expense",
      "account_type": "expense",
      "normal_balance": "debit",
      "is_sensitive": false
    },
    {
      "id": "uuid",
      "account_code": "1010",
      "account_name": "Bank Account",
      "account_type": "asset",
      "normal_balance": "debit",
      "is_sensitive": true
    }
  ]
}
```

### 7.3 Output Schema

```json
{
  "agent_name": "bookkeeping_agent",
  "status": "needs_review",
  "confidence_score": 0.86,
  "rationale": "The vendor and line items indicate office supplies. The payment appears to reduce the bank account.",
  "warnings": [
    "Bank Account is marked as sensitive and requires human approval."
  ],
  "result": {
    "entry_date": "2026-07-20",
    "description": "Office supplies purchase from Acme Office Supply",
    "source_type": "document",
    "journal_lines": [
      {
        "account_code": "5100",
        "account_name": "Office Supplies Expense",
        "debit_amount": 499500.00,
        "credit_amount": 0.00,
        "description": "Office supplies purchase"
      },
      {
        "account_code": "1010",
        "account_name": "Bank Account",
        "debit_amount": 0.00,
        "credit_amount": 499500.00,
        "description": "Payment from bank account"
      }
    ],
    "risk_flags": [
      {
        "type": "sensitive_account",
        "account_code": "1010",
        "message": "Bank Account requires human review."
      }
    ]
  }
}
```

### 7.4 Tools and Dependencies

Possible tools:

- Chart of accounts lookup.
- Vendor classification memory in a future version.
- Ledger context lookup in a future version.

For version 1, the agent should receive the relevant chart of accounts in the prompt/context and produce structured journal lines.

### 7.5 Confidence Heuristics

Confidence should decrease when:

- Vendor purpose is unclear.
- Line items map to multiple possible expense categories.
- The transaction could be either personal, capital, liability, or expense.
- The agent selects Suspense Account.
- Amounts are inconsistent with extraction data.
- The entry uses a sensitive account.

Recommended routing:

| Condition | Action |
|---|---|
| Confidence `>= 0.80`, no sensitive accounts, valid journal entry | Mark ready to post or auto-post depending on demo setting. |
| Confidence `< 0.80` | Create bookkeeping review item. |
| Any sensitive account used | Create bookkeeping review item. |
| Journal entry fails validation | Create validation review item and block posting. |
| Suspense Account used | Create high-priority bookkeeping review item. |

### 7.6 Deterministic Validation

After the Bookkeeping Agent returns a draft entry, backend services must validate:

- At least two journal lines exist.
- Every account code maps to an active account.
- Each line has either debit or credit, but not both.
- Debit and credit amounts are non-negative.
- Total debits equal total credits.
- Currency is consistent with the extraction.
- Sensitive account usage is detected.

The LLM should never be trusted as the final validator.

---

## 8. Reconciliation Agent

### 8.1 Responsibility

The Reconciliation Agent matches mock bank transactions against posted journal entries.

It should:

- Identify exact matches.
- Identify possible fuzzy matches.
- Explain why a match was proposed.
- Mark items as unmatched when no credible candidate exists.

### 8.2 Inputs

```json
{
  "bank_transaction": {
    "id": "uuid",
    "transaction_date": "2026-07-22",
    "description": "ACME OFFICE SUPPLY",
    "amount": -499500.00,
    "currency": "IDR"
  },
  "candidate_journal_entries": [
    {
      "id": "uuid",
      "entry_date": "2026-07-20",
      "description": "Office supplies purchase from Acme Office Supply",
      "total_debit": 499500.00,
      "total_credit": 499500.00,
      "accounts": ["Office Supplies Expense", "Bank Account"]
    }
  ]
}
```

### 8.3 Output Schema

```json
{
  "agent_name": "reconciliation_agent",
  "status": "completed",
  "confidence_score": 0.94,
  "rationale": "The bank amount exactly matches the journal entry amount, the dates are within two days, and the vendor names are highly similar.",
  "warnings": [],
  "result": {
    "bank_transaction_id": "uuid",
    "matches": [
      {
        "journal_entry_id": "uuid",
        "match_type": "fuzzy",
        "confidence_score": 0.94,
        "amount_score": 1.00,
        "date_score": 0.90,
        "vendor_score": 0.92,
        "rationale": "Exact amount match, close date, and similar vendor description."
      }
    ],
    "recommended_status": "matched"
  }
}
```

For unmatched items:

```json
{
  "agent_name": "reconciliation_agent",
  "status": "needs_review",
  "confidence_score": 0.32,
  "rationale": "No posted journal entry has a sufficiently similar amount, date, and description.",
  "warnings": [
    "No credible match found."
  ],
  "result": {
    "bank_transaction_id": "uuid",
    "matches": [],
    "recommended_status": "unmatched_review_required"
  }
}
```

### 8.4 Matching Signals

The agent and deterministic reconciliation service should consider:

| Signal | Description |
|---|---|
| Amount similarity | Exact or near-exact amount match. |
| Date proximity | Transaction date close to journal entry date. |
| Vendor similarity | Similarity between bank description and vendor or entry description. |
| Direction | Bank outflow should usually match expense or payment entries. |
| Existing status | Already reconciled entries should be excluded by default. |

### 8.5 Confidence Heuristics

Recommended score interpretation:

| Confidence | Meaning | Action |
|---:|---|---|
| `>= 0.90` | Strong match | Auto-accept if deterministic checks pass. |
| `0.70` to `0.89` | Possible match | Create reconciliation review item. |
| `< 0.70` | Weak or no match | Create unmatched review item. |

### 8.6 Guardrails

- Do not match against unposted journal entries.
- Do not match against already reconciled journal entries unless explicitly allowed.
- Do not auto-accept when multiple candidates have similar confidence.
- Do not invent missing journal entries.
- Keep rejected match candidates for audit traceability.

---

## 9. Human Review Integration

Human review is a workflow pause, not an exception path.

### 9.1 Review Item Creation Rules

| Source | Create Review Item When |
|---|---|
| Document Intake Agent | Confidence is low or required fields are missing. |
| Bookkeeping Agent | Confidence is low, sensitive account is used, Suspense Account is used, or validation fails. |
| Reconciliation Agent | Match is ambiguous, confidence is low, or no match is found. |
| System Validation | Trial balance fails or schema validation fails after agent output. |

### 9.2 Review Actions

Humans can:

- Approve the suggestion as-is.
- Edit the suggestion and approve the edited version.
- Reject the suggestion.

Each action should:

- Update the related source entity.
- Update the review item status.
- Create an audit event.
- Resume downstream workflow if appropriate.

### 9.3 Resume Behavior

| Review Type | After Approval or Edit |
|---|---|
| Extraction | Continue to Bookkeeping Agent. |
| Bookkeeping | Re-run deterministic validation, then post if valid. |
| Reconciliation | Accept, reject, or manually resolve match. |
| Validation | Re-run validation against edited payload. |

---

## 10. Prompting Strategy

Prompts should be kept close to the agent implementation and versioned in source control.

### 10.1 General Prompt Rules

Agents should be instructed to:

- Return only valid structured output.
- Use the provided schema.
- Avoid guessing when evidence is weak.
- Include concise rationale.
- Include warnings for ambiguous fields.
- Never claim that an entry is posted or reconciled; only backend services can do that.

### 10.2 Document Intake Prompt Focus

The prompt should emphasize:

- Extract only visible or strongly supported information.
- Preserve uncertain fields as null or warnings.
- Check subtotal, tax, and total consistency.
- Identify whether the document is an invoice, receipt, or unknown.

### 10.3 Bookkeeping Prompt Focus

The prompt should emphasize:

- Use only accounts from the provided chart of accounts.
- Produce a balanced journal entry.
- Explain classification reasoning.
- Prefer Suspense Account only when classification is genuinely unclear.
- Flag sensitive account usage.

### 10.4 Reconciliation Prompt Focus

The prompt should emphasize:

- Compare amount, date, and vendor similarity.
- Return ranked candidate matches.
- Mark as unmatched when no credible candidate exists.
- Avoid auto-confidence inflation when multiple candidates look similar.

---

## 11. Agent State and Persistence

Agents should not directly write to the database. Instead:

1. The backend loads data and calls the orchestrator.
2. The orchestrator calls an agent.
3. The agent returns structured output.
4. Backend services validate the output.
5. Backend services persist records.
6. Audit Service records the decision.

Recommended persistence mapping:

| Agent Output | Persisted To |
|---|---|
| Document Intake Agent result | `document_extractions` |
| Bookkeeping Agent result | `journal_entries`, `journal_entry_lines` |
| Reconciliation Agent result | `reconciliation_matches` |
| Review routing decision | `review_items` |
| Agent decision metadata | `audit_events`, optionally `agent_runs` |

---

## 12. Failure Handling

| Failure | Handling |
|---|---|
| Agent returns invalid JSON | Mark workflow failed, create audit event, allow retry. |
| Agent output fails schema validation | Create validation review item or mark workflow failed. |
| Provider timeout | Retry once if safe, then mark workflow failed. |
| Provider unavailable | Mark workflow failed and show recoverable error in UI. |
| Missing required input | Block agent call and create system audit event. |
| Accounting validation failure | Block posting and create review item. |
| Reconciliation ambiguity | Create review item instead of auto-accepting. |

---

## 13. Observability and Debugging

For the first implementation, `audit_events` may be enough for demo traceability. If debugging becomes difficult, add `agent_runs`.

Recommended debug metadata:

- Agent name.
- Model name.
- Prompt version.
- Input snapshot.
- Output snapshot.
- Latency.
- Token usage, if available.
- Error message.

This metadata should support technical explanation during an interview without exposing secrets or unnecessary raw document content.

---

## 14. Security and Privacy Notes

Agents may process sensitive financial documents even in a demo. The system should:

- Use synthetic or sample documents.
- Avoid sending real personal financial records to external providers.
- Avoid logging API keys, secrets, or provider credentials.
- Store only the file references needed for traceability.
- Keep provider metadata useful but minimal.

---

## 15. Version 1 Agent Scope

Version 1 should include:

- Document Intake Agent.
- Bookkeeping Agent.
- Reconciliation Agent.
- Supervisor / Orchestrator.
- Human review routing.
- Audit event creation for each agent decision.

Version 1 should not include:

- Learning from human edits.
- Real bank integration.
- Tax calculation.
- Multi-company memory.
- Autonomous posting without deterministic validation.
- Autonomous filing, payment, or external financial action.

---

## 16. Open Questions

These questions can be answered during implementation:

1. Which LLM or OCR provider should be used first?
2. Should prompts be stored as plain text files, Python constants, or database records?
3. Should agent confidence be entirely model-generated, or adjusted by deterministic scoring rules?
4. Should reconciliation matching be mostly deterministic with LLM explanation, or LLM-led with deterministic validation?
5. Should review approval resume the exact paused workflow, or start a fresh downstream workflow from the approved record?
6. Should agent runs be persisted in version 1, or only audit events?
7. How much raw document text should be included in audit snapshots?

---

## 17. Next Document

The next recommended document is `05-API-Spec.md`, which should define the backend endpoints, request payloads, response payloads, error formats, and workflow-specific API behavior.
