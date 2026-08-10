# Demo Plan
## ReconAI — Agentic AI Platform for Accounting Automation

**Version:** 1.0  
**Status:** Draft  
**Related Documents:** `docs/01-PRD.md`, `docs/02-System-Architecture.md`, `docs/03-Data-Model.md`, `docs/04-Agent-Design.md`, `docs/05-API-Spec.md`, `docs/06-UX-Flow.md`  
**Document Owner:** Prasetyo Suhada

---

## 1. Purpose

This document defines the portfolio demo plan for ReconAI. It provides the demo story, sample data requirements, step-by-step flow, expected outcomes, fallback paths, and technical talking points needed to present the project clearly in under five minutes.

The demo should prove that ReconAI is not just an LLM wrapper. It should show a coordinated agentic workflow with deterministic accounting validation, human-in-the-loop review, reconciliation, and audit traceability.

---

## 2. Demo Goals

| Goal | What the Demo Should Prove |
|---|---|
| End-to-end automation | A source document can become a reviewed and posted journal entry. |
| Agentic architecture | Separate agents handle extraction, bookkeeping, and reconciliation. |
| Human oversight | Risky or uncertain suggestions are routed to review before becoming final. |
| Accounting correctness | Journal entries are validated for balanced debits and credits. |
| Reconciliation intelligence | Bank transactions can be matched to ledger entries using amount, date, and vendor similarity. |
| Auditability | Any important decision can be traced back to source input, AI rationale, confidence, and human action. |

---

## 3. Demo Audience

The demo should work for:

| Audience | What to Emphasize |
|---|---|
| Recruiter or non-technical reviewer | Clear product story, practical automation, human approval, visible results. |
| Engineering interviewer | Architecture, schemas, API design, validation boundaries, orchestration. |
| Accounting-aware reviewer | Journal entries, COA mapping, trial balance, reconciliation, audit trail. |

The default narration should be product-first, then technical. Open with the workflow, then explain architecture when the user sees enough context.

---

## 4. Demo Duration

Target duration: **4 to 5 minutes**

Recommended pacing:

| Segment | Target Time |
|---|---:|
| Product setup | 30 seconds |
| Document upload and extraction | 45 seconds |
| Bookkeeping review and posting | 75 seconds |
| Bank reconciliation | 75 seconds |
| Audit traceability | 45 seconds |
| Technical close | 30 seconds |

---

## 5. Demo Setup

### 5.1 Required Local Services

The demo should run with:

- Frontend SPA.
- FastAPI backend.
- PostgreSQL database.
- Seeded chart of accounts.
- Sample invoice or receipt file.
- Sample bank statement CSV.
- AI/OCR provider configured, or deterministic mocked agent outputs for fallback.

### 5.2 Recommended Demo Mode

Use a hybrid approach:

- Upload a sample document live during the demo.
- Keep seeded data available as a fallback.
- Keep agent responses deterministic enough for reliable presentation.
- Include at least one low-risk flow and one review-required flow.

### 5.3 Pre-Demo Checklist

Before presenting:

- Backend is running.
- Frontend is running.
- Database has been migrated.
- Chart of accounts seed data exists.
- Sample files are available.
- AI provider key is configured, if live AI is used.
- Review queue starts empty or in a known state.
- Demo data can be reset quickly.
- Browser is open to the app.

---

## 6. Sample Data

### 6.1 Sample Document

Recommended sample file:

```text
samples/documents/office-supplies-receipt.pdf
```

Expected extraction:

| Field | Value |
|---|---|
| Document Type | `receipt` |
| Vendor | `Acme Office Supply` |
| Transaction Date | `2026-07-20` |
| Subtotal | `450000.00` |
| Tax | `49500.00` |
| Total | `499500.00` |
| Currency | `IDR` |

Expected bookkeeping result:

| Line | Account | Debit | Credit |
|---:|---|---:|---:|
| 1 | `5100` Office Supplies Expense | `499500.00` | `0.00` |
| 2 | `1010` Bank Account | `0.00` | `499500.00` |

Expected review reason:

- `Bank Account` is marked as sensitive, so the journal entry requires human approval.

### 6.2 Sample Bank Statement

Recommended sample file:

```text
samples/bank-statements/july-bank-statement.csv
```

Required columns:

```text
transaction_date,description,amount,currency,reference_number
```

Recommended rows:

| transaction_date | description | amount | currency | reference_number | Expected Result |
|---|---|---:|---|---|---|
| `2026-07-22` | `ACME OFFICE SUPPLY` | `-499500.00` | `IDR` | `BANK-001` | High-confidence match to office supplies journal entry. |
| `2026-07-23` | `SOFTWARE CLOUD SUBSCRIPTION` | `-250000.00` | `IDR` | `BANK-002` | Possible match or unmatched review item. |
| `2026-07-24` | `CLIENT PAYMENT` | `1500000.00` | `IDR` | `BANK-003` | Optional unmatched or revenue-related review item. |

### 6.3 Seed Chart of Accounts

The demo should use the seed accounts defined in `docs/03-Data-Model.md`, especially:

- `1010` Bank Account.
- `5100` Office Supplies Expense.
- `5400` Software Subscription Expense.
- `9999` Suspense Account.

---

## 7. Demo Script

### 7.1 Opening Narrative

Suggested narration:

> "ReconAI automates the bookkeeping flow for small businesses. The key idea is that AI can suggest and explain financial work, but deterministic services and human review decide what becomes final."

Then show the main navigation:

- Documents.
- Review Queue.
- Ledger.
- Reconciliation.
- Audit Log.

### 7.2 Step 1 — Upload a Receipt

Screen: **Documents**

Actions:

1. Upload `office-supplies-receipt.pdf`.
2. Wait for extraction result.
3. Point out the extracted vendor, date, subtotal, tax, and total.

Expected result:

- Document status moves from `uploaded` to `extracting`.
- Extraction result appears.
- Confidence score is visible.
- Rationale is visible.

Talking points:

- Document Intake Agent extracts structured fields.
- Extraction is persisted, not just displayed.
- Low-confidence extraction would go to human review.

### 7.3 Step 2 — Show Bookkeeping Suggestion

Screen: **Documents** or **Review Queue**

Actions:

1. Open the related bookkeeping review item.
2. Show the suggested journal entry.
3. Point out debit and credit lines.
4. Point out the sensitive account warning.

Expected result:

- Journal entry is suggested but not posted yet.
- Review item exists because `Bank Account` is sensitive.

Talking points:

- Bookkeeping Agent maps the transaction to the chart of accounts.
- The journal entry is balanced before it can be posted.
- Sensitive accounts require human approval regardless of confidence.

### 7.4 Step 3 — Approve and Post Journal Entry

Screen: **Review Queue**

Actions:

1. Click Approve.
2. Let backend validation run.
3. Navigate to Ledger.
4. Open the posted journal entry.

Expected result:

- Review item status becomes `approved`.
- Journal entry status becomes `posted`.
- Trial balance status is `balanced`.

Talking points:

- The LLM does not post directly.
- Backend services validate debit equals credit.
- Human approval and posting are logged.

### 7.5 Step 4 — Import Bank Statement

Screen: **Reconciliation**

Actions:

1. Upload `july-bank-statement.csv`.
2. Click Run Reconciliation.
3. Show imported bank transactions.

Expected result:

- Bank statement import succeeds.
- Reconciliation Agent runs.
- `ACME OFFICE SUPPLY` matches the posted journal entry.
- At least one item remains review-required.

Talking points:

- Reconciliation uses amount, date, and vendor similarity.
- High-confidence matches can be accepted automatically.
- Ambiguous items go to human review.

### 7.6 Step 5 — Resolve a Reconciliation Review Item

Screen: **Reconciliation** or **Review Queue**

Actions:

1. Open a possible match or unmatched transaction.
2. Show candidate match details.
3. Accept or reject the match.

Expected result:

- Match status updates.
- Bank transaction status updates.
- Audit event is created.

Talking points:

- The system explains why it proposed a match.
- Human review controls ambiguous cases.
- Rejected candidates remain traceable.

### 7.7 Step 6 — Show Audit Trace

Screen: **Audit Log**

Actions:

1. Filter audit events by the uploaded document or journal entry.
2. Show chronological events:
   - Document uploaded.
   - Extraction completed.
   - Journal entry suggested.
   - Review item created.
   - Human approved.
   - Journal entry posted.
   - Reconciliation match proposed or accepted.
3. Open one audit event detail.

Expected result:

- The reviewer can see input snapshot, output snapshot, rationale, confidence, and human action.

Talking points:

- Auditability is designed into the core workflow.
- The system can explain what happened and why.
- This is important for finance-adjacent automation.

### 7.8 Closing Narrative

Suggested narration:

> "The project is intentionally scoped: no real bank APIs, no tax filing, and no production compliance claims. The goal is to demonstrate the architecture of a trustworthy agentic bookkeeping workflow where AI suggests, deterministic services validate, and humans approve risky decisions."

---

## 8. Expected End State

At the end of the demo:

| Area | Expected State |
|---|---|
| Documents | One uploaded receipt or invoice has been processed. |
| Extraction | Structured extraction exists with confidence and rationale. |
| Review Queue | At least one item has been approved or edited. |
| Ledger | One journal entry is posted and balanced. |
| Trial Balance | Status is `balanced`. |
| Bank Statement | One CSV has been imported. |
| Reconciliation | One high-confidence match exists and one review case is visible or resolved. |
| Audit Log | Full trace exists from source document to posted ledger and reconciliation decision. |

---

## 9. Fallback Plan

The demo should not fail if an AI provider is slow, unavailable, or produces imperfect output.

### 9.1 AI Provider Failure

Fallback:

- Use deterministic mocked agent outputs for the sample document.
- Keep the same UI flow.
- Explain that the provider adapter is replaceable and mocked outputs are used for demo reliability.

### 9.2 Extraction Is Wrong

Fallback:

- Use Review Queue to edit extraction fields.
- Approve edited extraction.
- Continue downstream workflow.

Talking point:

- This demonstrates why human-in-the-loop review exists.

### 9.3 Bookkeeping Suggestion Is Wrong

Fallback:

- Edit the journal entry in Review Queue.
- Show validation blocking invalid debit/credit totals.
- Approve once balanced.

Talking point:

- The system treats AI as a suggestion engine, not an authority.

### 9.4 Reconciliation Match Is Wrong

Fallback:

- Reject the match.
- Show the rejected event in Audit Log.
- Manually resolve another candidate if available.

Talking point:

- Reconciliation decisions are traceable and reversible at the review stage.

### 9.5 App State Is Dirty

Fallback:

- Reset database to seeded demo state.
- Use pre-seeded document, journal entry, and bank transaction records.
- Start the demo from Dashboard instead of live upload.

---

## 10. Technical Talking Points

Use these when the audience asks for architecture detail.

### 10.1 Why Multi-Agent?

- Document extraction, bookkeeping, and reconciliation require different context and output schemas.
- Splitting agents makes the workflow easier to validate and debug.
- Each agent produces a structured suggestion that can be audited.

### 10.2 Why Human-in-the-Loop?

- Finance-adjacent workflows require review for low-confidence or high-risk actions.
- Sensitive accounts always require approval.
- Human edits are persisted and audit logged.

### 10.3 Why Deterministic Validation?

- Trial balance validation should never depend on an LLM.
- Posting is blocked unless debits equal credits.
- The backend owns financial correctness.

### 10.4 Why PostgreSQL?

- Accounting records are relational.
- Journal entries, journal lines, accounts, and reconciliation matches benefit from strong structure.
- JSONB can still support AI snapshots and flexible metadata.

### 10.5 Why Audit Events?

- Every important agent and human decision is traceable.
- Audit events explain what input was used and what output was produced.
- Append-only events create a credible traceability story.

---

## 11. Demo Data Reset Strategy

Recommended reset options:

| Option | Description |
|---|---|
| Full reset | Drop and recreate the local database, then seed COA and sample data. |
| Soft reset | Delete workflow records but keep chart of accounts. |
| Seeded scenario | Load prebuilt documents, journal entries, bank transactions, review items, and audit events. |

For the first implementation, a simple seed command is enough:

```text
make seed-demo
```

or:

```text
uv run python -m app.scripts.seed_demo
```

The exact command can be finalized after the backend structure exists.

---

## 12. Demo Acceptance Criteria

The demo is successful if:

- A user can upload or select a sample document.
- The system shows extracted document fields.
- The system suggests a balanced journal entry.
- A review item is created for a risky or uncertain suggestion.
- The user can approve or edit the suggestion.
- The approved journal entry is posted.
- Trial balance is shown as balanced.
- A bank statement can be imported.
- At least one bank transaction is matched to a posted journal entry.
- At least one reconciliation case requires review.
- Audit Log shows agent decisions and human actions.
- The full flow can be completed in under five minutes.

---

## 13. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| AI output is inconsistent during demo | Use sample files and optional mocked outputs. |
| Workflow takes too long | Use synchronous demo mode with small sample data. |
| Reviewer focuses on missing production compliance | Clearly state scope and non-goals. |
| Accounting classification is questioned | Show editability, rationale, and deterministic validation. |
| Reconciliation has no good match | Seed at least one exact or strong fuzzy match. |
| UI feels too complex | Keep demo path focused on one document and one bank statement. |

---

## 14. Future Demo Enhancements

Possible improvements after version 1:

- Show multiple vendors and recurring categorization.
- Add one-to-many reconciliation.
- Add a simple vendor memory feature based on approved prior decisions.
- Add side-by-side original document preview.
- Add model/provider metadata in audit details.
- Add seeded scenarios for different confidence levels.
- Add exportable audit report.

---

## 15. Next Document

The next recommended document is `08-Test-Plan.md`, which should define test coverage for document intake, bookkeeping validation, review routing, reconciliation, API behavior, and audit traceability.
