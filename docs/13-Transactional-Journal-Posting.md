# Transactional Journal Posting and Audit

**Status:** Planned — Epic 16. Posting contract documented in Task 16.1.
**Last Updated:** 2026-11-19

This contract covers direct posting in the Ledger API and Bookkeeping review approval
with or without edits. Today, the posting helper can commit the journal before the API
stores the linked document status and posting audit. The target is one transaction for
each decision. Extraction review continuation is governed by the
[Epic 15 contract](12-Source-Backed-Human-Review.md).

## Posting eligibility

| Action | Permitted journal state | Required review evidence |
|---|---|---|
| Direct post | `approved`, or an eligible `draft` as described below. | Every applicable required review has a positive decision for the journal being posted, or the journal is eligible without review. The direct route cannot resolve a review. |
| Bookkeeping approve | `review_required`, or a `draft` linked to a pending Bookkeeping review. | The pending review being approved supplies the decision in this transaction. Every other applicable requirement must already be satisfied. |
| Bookkeeping edit-and-post | Same as Bookkeeping approve. | The pending review supplies approval for the effective edited journal. Recheck all other requirements against the edited journal. |

- A document-backed `draft` is eligible for direct posting when the linked document is
  `ready_to_post` and the backend verifies that review requirements are met. In the
  current data model, `ready_to_post` is a **document** status and `draft` is its normal
  journal counterpart. `approved` can also support legacy journals with no document.
  A standalone `draft` is eligible only for a recognized `manual`, `import`, or `system`
  source and when its review requirements are met. A document-origin `draft` without a
  document cannot be verified and must be blocked.
- For document-backed direct posting, an `approved` journal may reference a document in
  `ready_to_post` or the legacy `approved` state. Block earlier or failed workflow states.
  A pending extraction review on the linked document blocks posting through either
  route. It cannot serve as evidence of Bookkeeping approval.
- `review_required` blocks direct posting, even if the review row is missing. Treat that
  case as requiring review or repair. Pending, rejected, or cancelled applicable reviews
  do not grant approval. Only an applicable `approved` or `edited` decision grants it.
  A stale or unrelated decision, including one for different journal lines, grants
  nothing. Evaluate requirements from the effective lines and COA, persisted risk and
  workflow state, and applicable review records. Sensitive effective accounts and other
  recorded gates require approval even if a state or review row is inconsistent.
- Link Bookkeeping reviews by `source_type=journal_entry` and `source_id` first. For
  legacy `source_type=document` reviews, use a verified journal ID when present, or
  the document's sole journal when unambiguous. Conflicting or ambiguous links block
  posting. A decision linked to one journal cannot clear a gate for another.
- Treat `posted`, `rejected`, and `voided` as terminal for these actions. Unknown states
  or ambiguous gate evidence fail closed. Always validate the effective entry using
  deterministic accounting rules, including double-entry and valid account references.
  Invalid edited lines leave the original journal and review intact. The legacy
  `trial_balance_status` success field remains in the direct response. Posting validates
  the journal being posted. Ledger-wide totals are read through the trial balance API.

## Transaction ownership and concurrency

The application service handling the request owns the transaction. Posting helpers
validate and stage changes, with `flush` where needed, and leave commit and rollback
to the owner. The following writes commit together:

1. Edited journal fields and lines, when applicable, and the Bookkeeping decision.
2. Journal `posted` status and `posted_at`, and `posted` status on the linked document.
3. Human decision audit for a review, followed by the journal posting audit.

Validate the target and effective journal before resolving the review. Build the success
response from the transaction's values and return it only after one successful commit.
If validation or persistence fails before commit, roll back every staged write. A failed
approve or edit-and-post leaves the previously pending review pending.

Serialize competing mutations with PostgreSQL row locks. Use the same order across
direct post, approve, edit-and-post, and Bookkeeping reject: linked document when
present, target journal, then applicable Bookkeeping review rows ordered by ID. Resolve
the candidate IDs before locking, then verify linkage, eligibility, and status using
fresh values under lock. The document row serializes the upstream workflow state check.
Posting does not acquire extraction review row locks after locking the document.

When posting wins, the waiting request cannot post again, change lines, or reject the
posted journal. When rejection wins, posting sees a rejected journal or resolved review
and cannot continue. Reject participates in the same locking protocol and records its
own decision, with no posting event. Use the journal's posted state as the durable
duplicate guard. A lost response after a successful commit is handled like a repeat.

## Audit ordering and references

- Review routes append one `review_item_approved` or `review_item_edited`, followed by
  one `journal_entry_posted`. Direct posting appends only `journal_entry_posted`.
- Keep event ordering explicit with decision and posting timestamps. The posting event
  must sort after the review event even if both writes share a database transaction.
- Keep source IDs typed as `review_item` or `journal_entry`. Include the journal ID and
  linked document ID when available. Include the review ID on review-triggered posting,
  and preserve the actor, resolution note, and existing ledger-period link. Store the
  final outcome in the human audit. Retain the review's original payload when saving edits.
- Invalid requests, conflicts, and rollbacks write no success audit. Repeats preserve
  the original posting timestamp and audit count.

## Planned HTTP behavior

Success remains `200`, using the existing response fields. For Bookkeeping approve/edit,
return the resolved review and `next_workflow_status: posted`. For direct post, return
the journal ID, `posted` status, and posting timestamp along with the legacy
`trial_balance_status` field. Planned domain errors use the API's top-level `error`
envelope with `code` and a user-facing `message`. Include `journal_status` and
`review_status` on a conflict where available. Native request-schema validation can
retain FastAPI's current `422` response.

| HTTP | Code | Condition and client action |
|---|---|---|
| `400` | `invalid_id` | Malformed URL ID. Correct the request. |
| `404` | `not_found` | The requested journal or review, or its required target, is missing. Refresh the record. |
| `422` | `journal_validation_failed` | The effective journal fails deterministic validation. Return safe validation details and allow correction. |
| `409` | `posting_review_required` | A required approval is missing or unresolved, including a direct post targeting `review_required`. Go to the review workflow. |
| `409` | `journal_already_posted` | The journal was already posted, including a direct replay or the losing request in a posting race. Refresh the journal. |
| `409` | `review_already_resolved` | The target review has already been resolved, including repeats of the same decision. Refresh the review. |
| `409` | `journal_not_postable` | A terminal or ineligible state, or ambiguous linkage, prevents the decision. Refresh and inspect the latest workflow state. |
| `503` | `posting_failed` | Database or audit persistence failed. Use a safe message and roll back when the transaction can still be rolled back. If the commit acknowledgement may have been lost, refresh before retrying to discover the durable outcome. |

For review routes, check resolved review status before journal status so a replay of
the same completed review returns `review_already_resolved`. If its review is still
pending but another route already posted the journal, return `journal_already_posted`.
Keep error messages free of raw database details. When the new errors ship, affected
frontend API clients must surface their messages and prompt a refresh on conflicts.

## Acceptance checks for implementation

- Direct posting succeeds for eligible entries and is blocked for pending or missing
  required approvals, legacy links that cannot be resolved safely, and invalid journals.
- Approve and edit-and-post commit journal, review, document, and ordered audit records
  together. Inject an audit write failure after staging changes and a pre-commit failure
  to verify rollback of statuses, journal lines, timestamps, and audit rows.
- Real PostgreSQL sessions cover repeat posting, direct post racing review decisions,
  and approve/edit or reject racing on the same review and journal. Assert one terminal
  decision, consistent entity state, and one posting event when a post wins.

Task 16.1 documents the contract only. Tasks 16.2–16.5 implement the behavior and run
the regression checks. This contract introduces no `.env` setting or schema change.
