# UX Flow
## ReconAI — Agentic AI Platform for Accounting Automation

**Version:** 1.0  
**Status:** Draft  
**Related Documents:** `docs/01-PRD.md`, `docs/02-System-Architecture.md`, `docs/03-Data-Model.md`, `docs/04-Agent-Design.md`, `docs/05-API-Spec.md`  
**Document Owner:** Prasetyo Suhada

---

## 1. Purpose

This document defines the user experience flow for ReconAI's first portfolio demo. It describes the primary screens, navigation model, user journeys, review patterns, visible AI decision points, and UI states required to demonstrate the end-to-end workflow.

The UX should make the system feel like an operational accounting tool: clear, efficient, reviewable, and built around trust rather than spectacle.

---

## 2. UX Goals

| Goal | Description |
|---|---|
| Demonstrate the full workflow quickly | A reviewer should understand document upload, AI extraction, journal entry creation, reconciliation, and audit traceability in under five minutes. |
| Make AI decisions visible | Confidence, rationale, warnings, and review requirements should be easy to inspect. |
| Keep human approval central | The user should clearly control whether AI suggestions become ledger or reconciliation records. |
| Preserve accounting clarity | Journal entries, debit/credit lines, accounts, and trial balance status should be shown in familiar accounting terms. |
| Reduce demo friction | The main path should use sample data and predictable actions so the demo does not depend on perfect real-world extraction. |

---

## 3. Target Users

The interface is designed for two demo personas:

| Persona | UX Need |
|---|---|
| SMB Owner | Wants a simple way to upload receipts and see bookkeeping handled with clear review checkpoints. |
| Bookkeeper / Accountant | Wants to inspect AI suggestions, validate journal entries, resolve reconciliation items, and trace decisions. |

For version 1, the UI should lean slightly toward the bookkeeper persona because the product's credibility depends on showing reviewability and accounting correctness.

---

## 4. Navigation Model

The application should use a compact operational layout:

- Left sidebar or top navigation.
- Main content area.
- Optional right-side detail panel for selected review or audit items.

Primary navigation items:

| Navigation Item | Purpose |
|---|---|
| Dashboard | Show workflow status and demo progress summary. |
| Documents | Upload and inspect invoice or receipt processing. |
| Review Queue | Approve, edit, or reject AI suggestions. |
| Ledger | View posted and draft journal entries plus trial balance status. |
| Reconciliation | Import bank statement CSV and resolve matches. |
| Audit Log | Trace agent decisions and human actions. |

Recommended default landing screen:

- **Dashboard** if sample data already exists.
- **Documents** if the database is empty and the user needs to start the demo.

---

## 5. Screen Map

```text
Dashboard
  ├── Documents summary
  ├── Review queue summary
  ├── Ledger status
  └── Reconciliation summary

Documents
  ├── Upload document
  ├── Document processing status
  ├── Latest extraction
  └── Related journal entry

Review Queue
  ├── Pending items list
  ├── Review item detail
  ├── Approve action
  ├── Edit and approve action
  └── Reject action

Ledger
  ├── Journal entries list
  ├── Journal entry detail
  └── Trial balance panel

Reconciliation
  ├── Bank statement import
  ├── Bank transaction list
  ├── Match candidates
  └── Resolve match actions

Audit Log
  ├── Event timeline
  ├── Event filters
  └── Event detail snapshots
```

---

## 6. Primary Demo Journey

This journey should be optimized for a smooth portfolio walkthrough.

### 6.1 Step 1 — Upload Receipt or Invoice

Screen: **Documents**

User actions:

1. Select or drag a sample invoice/receipt file.
2. Choose document type if needed.
3. Submit upload.

System response:

- Show upload success.
- Show document status: `extracting`.
- Show processing indicator while the Document Intake Agent runs.
- Show extraction result when complete.

Visible AI signals:

- Extracted vendor.
- Extracted date.
- Extracted subtotal, tax, total.
- Confidence score.
- Rationale or extraction notes.
- Warnings if present.

### 6.2 Step 2 — Review Extracted or Suggested Accounting Data

Screen: **Review Queue**

User actions:

1. Open the pending review item.
2. Inspect original AI suggestion.
3. Approve, edit, or reject.

System response:

- If approved or edited, update review item status.
- Resume downstream workflow.
- If reviewing bookkeeping, validate and post the journal entry if valid.
- Create audit event for the human action.

Visible AI signals:

- Confidence score.
- Rationale.
- Risk flags.
- Sensitive account warning.
- Original payload and edited payload comparison, if edited.

### 6.3 Step 3 — Inspect Ledger Entry

Screen: **Ledger**

User actions:

1. Open the posted journal entry.
2. Inspect debit and credit lines.
3. Check trial balance status.

System response:

- Display journal entry status as `posted`.
- Display total debits and credits.
- Display trial balance status as `balanced`.

Visible accounting signals:

- Entry date.
- Description.
- Debit account.
- Credit account.
- Debit total.
- Credit total.
- Trial balance difference.

### 6.4 Step 4 — Import Bank Statement

Screen: **Reconciliation**

User actions:

1. Upload mock bank statement CSV.
2. Run reconciliation.

System response:

- Parse and display bank transactions.
- Run Reconciliation Agent.
- Auto-accept high-confidence matches.
- Create review items for possible or unmatched transactions.

Visible AI signals:

- Match confidence.
- Amount score.
- Date score.
- Vendor score.
- Match rationale.
- Candidate journal entry.

### 6.5 Step 5 — Resolve Reconciliation Items

Screen: **Reconciliation** or **Review Queue**

User actions:

1. Open possible match or unmatched item.
2. Accept candidate match, reject candidate, or manually resolve.

System response:

- Update reconciliation match status.
- Update bank transaction status.
- Create audit event.

### 6.6 Step 6 — Show Audit Trace

Screen: **Audit Log**

User actions:

1. Filter by source document, journal entry, or bank transaction.
2. Open event details.
3. Inspect input and output snapshots.

System response:

- Show chronological trace from upload to agent decisions to human approval.

Visible trust signals:

- Agent name.
- Event type.
- Rationale.
- Confidence score.
- Human action.
- Timestamp.
- Source entity link.

---

## 7. Dashboard Screen

### 7.1 Purpose

The Dashboard provides a quick operating summary and helps guide the demo.

### 7.2 Content

Recommended panels:

| Panel | Content |
|---|---|
| Documents | Total uploaded, processing, pending review, posted. |
| Review Queue | Pending items, high-priority items. |
| Ledger | Posted journal entries, trial balance status. |
| Reconciliation | Imported bank transactions, matched, pending review, unmatched. |

### 7.3 Actions

Primary actions:

- Upload document.
- Open review queue.
- Import bank statement.
- View audit log.

The Dashboard should not become a marketing page. It should be a compact operational command center.

---

## 8. Documents Screen

### 8.1 Purpose

The Documents screen supports document upload and inspection of extraction/bookkeeping progress.

### 8.2 Layout

Recommended layout:

- Upload area at the top.
- Document list below.
- Detail panel or detail route for selected document.

### 8.3 Document List Fields

| Field | Description |
|---|---|
| Filename | Original uploaded filename. |
| Type | Invoice, receipt, or unknown. |
| Status | Current workflow state. |
| Vendor | From latest extraction, if available. |
| Total | From latest extraction, if available. |
| Confidence | Latest extraction or bookkeeping confidence. |
| Uploaded At | Upload timestamp. |

### 8.4 Document Detail

Recommended sections:

- File metadata.
- Extraction result.
- Bookkeeping result.
- Related review item.
- Related journal entry.
- Audit trail link.

---

## 9. Review Queue Screen

### 9.1 Purpose

The Review Queue is the main human-in-the-loop screen. It should make pending AI suggestions easy to inspect and resolve.

### 9.2 Layout

Recommended layout:

- Filterable review item list on the left.
- Review detail on the right.
- Action bar at the bottom or top-right of the detail area.

Filters:

- Status.
- Review type.
- Priority.
- Created date.

### 9.3 Review Item Types

| Type | What User Reviews |
|---|---|
| Extraction | Extracted vendor, date, line items, tax, and total. |
| Bookkeeping | Suggested COA classification and journal entry. |
| Reconciliation | Candidate match between bank transaction and journal entry. |
| Validation | System-detected issue requiring correction. |

### 9.4 Review Actions

| Action | Behavior |
|---|---|
| Approve | Accept suggestion as-is and resume workflow. |
| Edit and Approve | Save edited payload, validate it, and resume workflow. |
| Reject | Reject suggestion and stop downstream workflow for that item. |

### 9.5 Editing Behavior

Extraction edit fields:

- Vendor name.
- Transaction date.
- Subtotal.
- Tax.
- Total.
- Currency.
- Line items.

Bookkeeping edit fields:

- Entry date.
- Description.
- Account codes.
- Debit amounts.
- Credit amounts.
- Line descriptions.

Reconciliation edit fields:

- Selected journal entry.
- Resolution note.
- Match status.

### 9.6 Review Detail Must Show

- Original AI suggestion.
- Confidence score.
- Rationale.
- Warnings and risk flags.
- Source document or transaction reference.
- Editable fields where appropriate.
- Audit trail link.

---

## 10. Ledger Screen

### 10.1 Purpose

The Ledger screen shows accounting results after human approval and deterministic validation.

### 10.2 Content

Recommended sections:

- Trial balance summary.
- Journal entries list.
- Journal entry detail.

### 10.3 Journal Entry List Fields

| Field | Description |
|---|---|
| Entry Date | Accounting date. |
| Description | Entry description. |
| Status | Draft, review required, approved, posted, rejected. |
| Source | Document, manual, import, or system. |
| Confidence | Bookkeeping confidence, if AI-generated. |
| Total Debit | Total debit amount. |
| Total Credit | Total credit amount. |

### 10.4 Journal Entry Detail

The detail view should show:

- Header metadata.
- AI rationale.
- Risk flags.
- Debit and credit lines.
- Related document.
- Related extraction.
- Related audit events.

The debit and credit table should look familiar to accounting users and clearly show whether the entry balances.

---

## 11. Reconciliation Screen

### 11.1 Purpose

The Reconciliation screen helps users import a mock bank statement and resolve matches between bank transactions and posted ledger entries.

### 11.2 Layout

Recommended layout:

- Bank statement import action.
- Summary counts.
- Bank transaction list.
- Match detail panel.

### 11.3 Summary Counts

| Count | Description |
|---|---|
| Imported | Total bank transactions imported. |
| Matched | Transactions with accepted matches. |
| Possible Match | Transactions needing review. |
| Unmatched | Transactions with no credible candidate. |
| Resolved | Manually resolved items. |

### 11.4 Transaction List Fields

| Field | Description |
|---|---|
| Date | Bank transaction date. |
| Description | Bank transaction description. |
| Amount | Signed amount. |
| Status | Matched, possible match, unmatched, resolved. |
| Confidence | Best match confidence, if available. |

### 11.5 Match Detail

For a selected bank transaction, show:

- Bank transaction details.
- Candidate journal entries.
- Amount/date/vendor score.
- Match rationale.
- Accept/reject actions.
- Review item link if review is required.

---

## 12. Audit Log Screen

### 12.1 Purpose

The Audit Log screen proves traceability. It should answer: "Why did the system do this, what data did it use, and who approved it?"

### 12.2 Layout

Recommended layout:

- Filter bar.
- Event timeline or table.
- Event detail panel.

Filters:

- Source type.
- Source ID.
- Event type.
- Actor type.
- Date range.

### 12.3 Event List Fields

| Field | Description |
|---|---|
| Timestamp | When the event occurred. |
| Event Type | What happened. |
| Actor | Agent, human, or system. |
| Source | Related entity. |
| Confidence | If applicable. |
| Human Action | If applicable. |

### 12.4 Event Detail

Event detail should show:

- Rationale.
- Input snapshot.
- Output snapshot.
- Confidence score.
- Human action.
- Links to related document, journal entry, review item, or reconciliation match.

---

## 13. Key UI Components

| Component | Purpose |
|---|---|
| `ConfidenceBadge` | Shows confidence score with visual severity. |
| `StatusBadge` | Shows workflow or record status. |
| `ReviewActionBar` | Provides approve, edit, and reject actions. |
| `JournalEntryTable` | Shows debit and credit lines. |
| `TrialBalancePanel` | Shows balanced/unbalanced status and totals. |
| `AuditTimeline` | Shows chronological trace of events. |
| `FileUpload` | Handles document and CSV uploads. |
| `MatchScoreBreakdown` | Shows amount, date, and vendor score. |

Confidence display:

| Confidence | Suggested UI Treatment |
|---:|---|
| `>= 0.90` | High confidence. |
| `0.70` to `0.89` | Needs attention. |
| `< 0.70` | Low confidence. |

The UI should show the numeric score and a short label. Avoid hiding important uncertainty behind color alone.

---

## 14. Empty, Loading, and Error States

### 14.1 Empty States

| Screen | Empty State |
|---|---|
| Dashboard | Show zero counts and primary action to upload a document. |
| Documents | Show upload area and no document rows. |
| Review Queue | Show that no items need review. |
| Ledger | Show no journal entries and trial balance at zero. |
| Reconciliation | Show import CSV action. |
| Audit Log | Show no audit events yet. |

### 14.2 Loading States

Use explicit loading states for:

- Uploading document.
- Running extraction.
- Generating journal entry.
- Importing bank statement.
- Running reconciliation.
- Loading audit detail.

Loading copy should describe the operation, not overpromise the outcome.

### 14.3 Error States

Error messages should:

- State what failed.
- Provide a retry path when possible.
- Link to the related workflow item if already created.

Examples:

- Unsupported file type.
- CSV parsing failed.
- Agent provider unavailable.
- Journal entry validation failed.
- Reconciliation workflow failed.

---

## 15. Demo-Friendly UX Requirements

The first version should support a reliable demo path:

- Include sample receipt or invoice data.
- Include sample bank statement CSV data.
- Make pending review items easy to find.
- Show confidence and rationale without requiring extra clicks.
- Show a posted journal entry with balanced debits and credits.
- Show at least one high-confidence reconciliation match.
- Show at least one review-required reconciliation item.
- Make audit trace available from document, ledger, reconciliation, and review screens.

---

## 16. Accessibility and Usability Notes

Baseline requirements:

- Buttons should have clear labels.
- Important status should not rely on color alone.
- Tables should have readable column labels.
- Form fields should have visible labels.
- Error states should be associated with the affected field or action.
- Keyboard navigation should work for primary review actions.
- Destructive actions, such as rejection, should require a short confirmation or deliberate click.

---

## 17. Out of Scope for Version 1

The first UX version should not include:

- Multi-user permissions.
- Role-specific navigation.
- Full accounting reports.
- Tax filing workflows.
- Real bank connection setup.
- Complex onboarding.
- Mobile-first optimization beyond responsive usability.
- Learning preference configuration from human edits.

---

## 18. Open Questions

These questions can be resolved during frontend implementation:

1. Should the app open on Dashboard or Documents when there is no data?
2. Should document processing show live step-by-step progress or only final status refreshes?
3. Should review edits happen inline or in a modal?
4. Should reconciliation be resolved primarily from the Reconciliation screen or the Review Queue?
5. Should audit event snapshots be displayed as formatted JSON, summarized fields, or both?
6. Should the demo include seeded sample data by default, or require the presenter to upload sample files live?

---

## 19. Next Document

The next recommended document is `07-Demo-Plan.md`, which should define the exact portfolio demo script, sample data, expected outcomes, and fallback path if an AI provider response is imperfect.
