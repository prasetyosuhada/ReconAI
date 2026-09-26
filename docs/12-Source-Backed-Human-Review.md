# Source-Backed Human Review
## ReconAI — Safe Extraction Correction

**Version:** 1.1
**Status:** Implemented portfolio workflow — Epic 15; verification limits below
**Last Updated:** 2026-09-26
**Related Documents:** `docs/01-PRD.md`, `docs/02-System-Architecture.md`, `docs/03-Data-Model.md`, `docs/04-Agent-Design.md`, `docs/05-API-Spec.md`, `docs/06-UX-Flow.md`, `docs/08-Test-Plan.md`, `docs/10-Hybrid-Document-Extraction.md`
**Document Owner:** Prasetyo Suhada

---

## 1. Purpose and Implementation Status

Extraction reviewers can compare structured fields with stored PDF/image evidence,
inspect intake diagnostics, correct accounting fields, and continue to Bookkeeping
through deterministic validation and an atomic persistence boundary.

This document describes the implemented portfolio behavior. It supersedes the initial
Epic 15 design where that design proposed a combined evidence response, additional audit
events, or authorization that the application does not implement. The document-content
pipeline is defined in `docs/10-Hybrid-Document-Extraction.md`.

## 2. Scope and Non-Goals

Implemented:

- controlled source-byte delivery by document ID;
- native PDF iframe and JPEG/PNG/WebP preview;
- persisted extraction diagnostics and partial-page notices;
- backend validation for approve-as-is and edited extraction;
- transactional, idempotent persistence with PostgreSQL concurrency regression tests;
- API and component regression tests with external model behavior stubbed.

Not implemented by Epic 15:

- production authentication, tenant authorization, or document sharing;
- a dedicated OCR service, redaction, annotation, or encrypted-PDF password recovery;
- a combined `source_document` / `extraction_context` review-detail response;
- new audit events for source reads or failed correction validation;
- removal of legacy `stored_file_path` from document list/detail responses;
- a cross-browser PDF renderer or measured LLM extraction accuracy.

## 3. Implemented Review Flow

```text
Pending extraction review
  ├─ GET review detail (original/edited payload and document source ID)
  ├─ GET latest extraction (fields, confidence, provider_metadata)
  └─ GET document content (source bytes or safe error)
          │
          ├─ Reject → lock/recheck → reject document/review + audit → commit once
          │
          ▼
Approve as-is or Save Fields & Continue
  → merge persisted extraction with allowlisted correction
  → deterministic validation
      ├─ invalid: 422; pending; no model call or persisted mutation
      └─ valid: end read transaction → call Bookkeeping without a held DB connection
          → lock/reload review, document, latest extraction
          → recheck pending status and unchanged source snapshot
          → persist extraction, downstream outcome, review, status, human/agent audits
          → commit once (or roll back all changes)
```

The orchestration lives in `backend/app/services/review_continuation.py`; HTTP transport
stays in `backend/app/api/v1/review_items.py`. Accounting validation and persistence remain
deterministic. Extraction approval may result in `ready_to_post` or
`bookkeeping_review_required`; it is not itself ledger posting.

## 4. Evidence and Diagnostic Reads

The frontend assembles evidence from separate API calls:

| Source | Implemented contract |
|---|---|
| `GET /api/v1/review-items/{id}` | Review type, source ID, original/edited payload, confidence and review risk flags. No new combined evidence descriptor. |
| `GET /api/v1/documents/{id}/extractions/latest` | Persisted accounting fields, model confidence/rationale and `provider_metadata`. |
| `GET /api/v1/documents/{id}/content` | Validated stored bytes, safe headers, or stable error envelope. |

The modal uses the document source ID (or linked payload/extraction document ID), and
builds the content URL. Its filename comes from available payload metadata or review
title. It does not use `stored_file_path` to fetch evidence.

`ExtractionReviewContext.tsx` reads the existing metadata keys:

- `extraction_method`;
- `source_page_count`, `processed_page_count`, `page_limit_applied`;
- `text_page_numbers`, `vision_page_numbers`, `rendered_page_numbers`;
- `warnings`, `low_confidence_fields`, `risk_flags`.

Review risk flags are a fallback if metadata has no recorded flags. Missing diagnostics
are shown as unavailable/not recorded; empty recorded lists are distinguished from
missing lists. Page limits, lower processed counts, or partial risk flags show a partial
processing notice. No full visual page base64 payload is persisted for this panel.

Availability and extraction quality are separate signals, not new response enum fields.
Missing or blocked source access maps to one public unavailable state (`410`); diagnostic
warnings and flags describe unreadable or partial processing. A valid file signature does
not prove that a PDF is readable or unencrypted. Source availability does not determine
whether a valid accounting correction can continue: the backend requires the document
record and valid fields, not a successful viewer fetch.

## 5. Controlled Source Endpoint

`GET /api/v1/documents/{document_id}/content` in `backend/app/api/v1/documents.py`:

1. Parses UUID and loads the document row.
2. Normalizes stored JPEG aliases and checks the PDF/JPEG/PNG/WebP MIME allowlist.
3. Resolves the file under `UPLOAD_STORAGE_DIR` (`./storage/uploads` relative to backend).
4. Rejects traversal and symlink escapes or absent/non-regular files.
5. Checks a bounded file signature against the stored MIME.
6. Uses `FileResponse` for stored bytes, safely encoded inline filename, and byte ranges.

| Header | Value |
|---|---|
| `Content-Type` | Validated PDF/JPEG/PNG/WebP MIME. |
| `Content-Disposition` | `inline` with encoded original filename. |
| `X-Content-Type-Options` | `nosniff`. |
| `Cache-Control` | `private, no-store`. |
| `Accept-Ranges` | `bytes` from the response stack. |

| HTTP | Stable code | Condition |
|---:|---|---|
| 400 | `invalid_document_id` | Invalid UUID. |
| 404 | `document_not_found` | No document row. |
| 410 | `source_content_unavailable` | File missing or path cannot be served safely. |
| 415 | `unsupported_source_media_type` | Unsupported stored MIME or signature mismatch. |

Source response errors do not expose filesystem paths. The route has no authentication
or ownership dependency in this demo application. Production access control and removal
of storage paths from legacy document list/detail responses remain separate hardening
work; path containment is not user authorization.

## 6. Correction and Validation Contract

`backend/app/services/review_validation.py` filters corrections to:

- `document_type`, `vendor_name`, `transaction_date`, `currency`;
- `subtotal_amount`, `tax_amount`, `total_amount`;
- `line_items`: `description`, `quantity`, `unit_price`, `amount`.

Other keys are ignored, including confidence, provider metadata, raw text, risk flags,
payment status, status, and journal lines. Approve-as-is validates the original review
payload overlaid by persisted document/latest extraction fields, including persisted
nulls. Edit overlays only allowlisted correction fields onto that effective snapshot.
Legacy wrapped line-item lists are normalized before validation.

The typed boundary and shared deterministic intake rules require an invoice/receipt,
non-empty vendor, exact valid `YYYY-MM-DD` date, uppercase three-letter currency,
finite non-negative supplied numeric fields and a positive total. Subtotal plus tax must
match total within `0.05` when all three are present; complete line amounts must match
subtotal within `0.05`. Decimal arithmetic is used for monetary comparisons.

Invalid decisions return HTTP `422`:

```json
{
  "error": {
    "code": "extraction_validation_failed",
    "message": "The extraction still contains fields that must be corrected.",
    "details": [
      {"field": "vendor_name", "code": "missing_vendor_name", "message": "Vendor name is required."}
    ],
    "warnings": [],
    "risk_flags": ["missing_vendor_name"]
  }
}
```

Messages may vary by validation rule; clients use the code and field path. Validation
failure leaves the review/document/extraction unchanged, invokes no Bookkeeping, and
creates no audit or journal. The frontend opens the editor, retains the draft, associates
errors with inputs using `aria-invalid`/`aria-describedby`, and shows an alert summary.
Reject does not require valid accounting fields.

## 7. Atomic Persistence and Concurrency

After model classification, locks are acquired in order: review → document → latest
extraction. The service rechecks pending status and compares the accounting snapshot
with the pre-classification snapshot. One transaction persists corrected fields,
downstream journal/review, review resolution, document status, and audit events. Shared
bookkeeping persistence flushes without committing; the caller commits once.

| Failure | Response / state |
|---|---|
| Already resolved or losing concurrent request | `409 review_already_resolved`, current `review_status` and `next_workflow_status` where available; no second persistence. |
| Source snapshot changed during classification | `409 review_source_changed`; refresh before continuing. |
| Classification, deterministic bookkeeping, persistence, or audit failure | `503 review_continuation_failed`; rollback leaves the decision pending unless another request already resolved it. |

Reject uses the same locking/pending recheck and cannot overwrite a winning approval.
Concurrent valid callers may both invoke the LLM before locking; only one may persist.
This is not an exactly-once model invocation guarantee. PostgreSQL tests use independent
sessions and observe the losing session waiting on a real row lock.

## 8. UI Behavior and Browser Limits

`SourceDocumentViewer.tsx` fetches bytes into an object URL and revokes it on source
change/unmount. PDF uses a native iframe with `#page=N`; custom Previous/Next controls
are bounded by persisted `source_page_count`. For a one-page PDF both are disabled;
with no known count the component uses native viewer controls without a custom counter.
JPEG/PNG/WebP use contained image scaling. Open Source always targets the same endpoint.

Loading, missing ID, unavailable, unsupported, fetch failure, and image-render failure
have explicit text. Native PDF plugin errors/password prompts may remain inside the
browser viewer; iframe `onError` is not reliable for detecting these failures. The
component suite does not render PDF pixels. Browser-specific rendering, keyboard/focus
behavior across the full modal, and responsive layout remain manual verification items.

Confirm Extraction and Save Fields & Continue wait for API success before closing and
refreshing the queue. Submission is disabled while the mutation is pending. API conflicts
and recoverable failures keep the modal and draft open with an error; conflicts instruct
the user to refresh rather than silently treating a stale decision as successful.

Payment remains `unknown` unless recorded; a positive total does not imply paid. Existing
legacy form fallbacks (such as IDR currency and zero/derived amount display) are not
independent evidence of what was read. The backend revalidates persisted fields for
approve-as-is; the reviewer must verify all fields before saving a correction.

Upload UI uses the backend's `10 * 1024 * 1024` byte limit, supports PDF/JPEG/PNG/WebP,
rejects empty files, and uses **Text & Vision** terminology.

## 9. Audit and Provenance

Successful decisions preserve `ReviewItem.original_payload`, model confidence,
rationale, raw text, and provider metadata. Accounting fields in the newest extraction
are updated in place (or a row is created if absent); this is not an immutable extraction
version history. Original persisted fields and effective corrected fields are captured
in the human audit snapshots.

| Event | Implemented context |
|---|---|
| `review_item_approved` / `review_item_edited` | Actor `human_user`, note, review type, original extraction ID/fields, filtered edits, effective fields, resulting extraction/journal/review IDs and next state. |
| `review_item_rejected` | Human rejection and resolution note. |
| `bookkeeping_completed` | Agent rationale/confidence, outcome, resulting entities, actual completion timestamp and duration. |

Human decision and Bookkeeping audit records are saved together. Failed validation,
failed continuation, and source reads do not append separate failure/access audit events.

## 10. Regression Evidence

| Area | Automated evidence |
|---|---|
| Safe source delivery | `backend/tests/test_documents_api.py`: supported types, range response, headers, missing/unsupported content, UUID and path traversal/symlink checks. |
| Validation / provenance | `test_review_correction_validation.py`: valid/invalid approve/edit, persisted precedence, protected metadata, numeric boundaries and recovery. |
| Rollback / retry | `test_review_continuation.py`: failures at model, persistence, audit and commit boundaries; all decision retries. |
| Real concurrency | `test_review_continuation_postgres.py`: PostgreSQL winner/loser, reject races and transaction rollback. |
| Cross-endpoint journey | `test_review_workflow_regression.py`: actual digital/scanned multi-page PDFs, PNG or missing source → invalid approve/edit → valid correction → duplicate conflict. |
| Evidence UI | `frontend/tests/SourceDocumentViewer.test.tsx`: bounded PDF controls/URL, images, source failures, URL cleanup. |
| Context UI | `frontend/tests/ExtractionReviewContext.test.tsx`: persisted diagnostics, partial coverage and absent metadata. |
| Form + API adapter | `frontend/tests/ExtractionReviewModal.test.tsx`: success, 422 draft retention/errors, duplicate click, 409/503 and rejection. |
| Upload | `frontend/tests/documentUpload.test.ts`: 10 MB boundary, formats, empty/unsupported files. |

See `docs/08-Test-Plan.md` for commands and recorded run results. Frontend tests use
Vitest, React Testing Library and jsdom with mocked fetch. Backend tests mock external
classification; local file preparation and API persistence run for real. No coverage
percentage, model accuracy benchmark, or live-browser pass is implied.

## 11. Configuration and Documentation

No application `.env` addition or migration is required. Install frontend test
dependencies with `npm ci`; run `npm test`. PostgreSQL race tests opt in via
`RECONAI_TEST_POSTGRES_URL` in the test process environment, using a database user allowed
to create/drop isolated test schemas. Without it those tests skip; SQLite is not evidence
for row-lock correctness. See `docs/09-Setup-Guide.md`.

Manual review and demo procedures are in `docs/11-Hybrid-Extraction-Manual-Test.md` and
`docs/07-Demo-Plan.md`. Their unchecked runbook steps are instructions, not completed test
results. Related PRD, architecture, API, agent, UX, and persistence sections describe the
same implemented boundaries and remaining limitations.
