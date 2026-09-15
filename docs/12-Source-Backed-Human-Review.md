# Source-Backed Human Review
## ReconAI — Planned Design for Safe Extraction Correction

**Version:** 1.0
**Status:** Planned — Epic 15
**Last Updated:** 2026-09-14
**Related Documents:** `docs/01-PRD.md`, `docs/02-System-Architecture.md`, `docs/03-Data-Model.md`, `docs/04-Agent-Design.md`, `docs/05-API-Spec.md`, `docs/06-UX-Flow.md`, `docs/08-Test-Plan.md`, `docs/10-Hybrid-Document-Extraction.md`
**Document Owner:** Prasetyo Suhada

---

## 1. Purpose and Status

This document is the design source of truth for Epic 15. It defines how an extraction
reviewer will inspect the stored source document, understand extraction warnings and page
coverage, correct structured accounting fields, and continue the workflow safely.

Everything in this document is **planned** until its corresponding Epic 15 task is
implemented and verified. The current implemented document-content pipeline remains
defined by `docs/10-Hybrid-Document-Extraction.md`.

The current application already creates extraction review items and provides editable
fields. Epic 15 adds the missing trust boundary around that experience:

- a real source document served by a backend-controlled resource endpoint;
- explicit content quality and processed-page context;
- deterministic validation of both approve-as-is and edited extraction payloads;
- consistent, idempotent persistence of the human decision and downstream continuation;
- regression coverage for the backend contract and critical frontend review journey.

---

## 2. Goals and Non-Goals

### 2.1 Goals

1. Let a reviewer compare the structured extraction with the actual uploaded PDF or
   image without exposing an internal filesystem path.
2. Make missing, unreadable, corrupt, and partially processed source conditions visible
   and actionable.
3. Apply the same deterministic essential-field and monetary rules to human-corrected
   extraction data before Bookkeeping can run.
4. Preserve the original model output, confidence, warnings, and provider metadata while
   recording human corrections separately.
5. Ensure retries or concurrent review submissions do not create duplicate journal,
   review, status, or audit side effects.
6. Keep the frontend useful for correction while retaining the backend as the
   authoritative validation boundary.

### 2.2 Non-Goals

- A dedicated OCR service or persisted full-page OCR transcript.
- Editing the original uploaded file.
- Password recovery for encrypted PDFs.
- Production-grade multi-tenant authorization or document sharing.
- Automatic learning from reviewer corrections.
- General-purpose annotation, redaction, or document management.
- Changing the extraction confidence reported by the model into a synthetic human
  confidence score.

---

## 3. Design Principles

| Principle | Planned Behavior |
|---|---|
| Source content is untrusted | Resolve content from a document ID, validate the stored path and media type, and never interpret a client-provided path. |
| Evidence stays distinguishable | Preserve original extraction facts, model confidence, warnings, and page metadata separately from human corrections. |
| Validation is deterministic | Reuse the backend extraction validation rules for both approve-as-is and edit-and-continue actions. |
| Invalid input remains reviewable | Return field-level errors, keep the review pending, and do not invoke Bookkeeping. |
| One decision has one continuation | Commit the resolved review, corrected extraction, downstream persistence, status changes, and audit records consistently. |
| UI claims follow evidence | Unknown payment or document facts remain unknown; missing or unrenderable source content is shown as unavailable. |
| Implementation claims require verification | Specifications retain the `Planned` label until Task 15.8 verifies and documents the implemented behavior. |

---

## 4. Planned Review Flow

```text
Pending extraction review
        │
        ├── load review detail + latest extraction metadata
        ├── load source through document-ID content endpoint
        │       ├── available → show PDF/image evidence
        │       └── unavailable/unrenderable → show explicit source state
        │
        ▼
Reviewer chooses Approve as-is, Edit and Continue, or Reject
        │
        ├── Reject → persist human rejection + audit; stop downstream workflow
        │
        ▼
Build allowlisted extraction payload
        │
        ▼
Deterministic extraction validation
        │
        ├── invalid → HTTP 422 + field errors; review remains pending; no Bookkeeping
        │
        ▼
Bookkeeping classification and deterministic bookkeeping checks
        │
        ▼
Short database transaction
        ├── lock and re-check pending review
        ├── persist corrected extraction and provenance
        ├── persist downstream journal/review outcome
        ├── update document and review statuses
        └── append human and workflow audit events
                │
                ▼
          Commit once and return next workflow state
```

The implementation may perform the external Bookkeeping model call before the final
short database transaction. It must re-check the review state under a database lock
before persistence. A concurrent loser must not create a second continuation.

---

## 5. Source Evidence Contract

### 5.1 Source State Model

The review contract uses two separate concepts so file availability is not confused with
extraction quality.

| Field | Values | Meaning |
|---|---|---|
| `availability` | `available`, `missing`, `blocked` | Whether the backend can safely serve the stored source bytes. |
| `content_quality` | `readable`, `unreadable`, `corrupt`, `partial`, `unknown` | What the extraction pipeline learned about usable source content. |

- `missing` means the document row exists but the stored file no longer exists.
- `blocked` means the stored reference fails the server's source-access policy. Internal
  path details must not be returned to the client.
- `unreadable` or `corrupt` may still have `availability: available`; the reviewer may
  download or attempt to view the original bytes even though semantic extraction failed.
- `partial` means only part of the source was processed, including page-limit truncation
  or a required visual page that could not be rendered.

### 5.2 Review Detail Evidence

For an extraction review, the planned detail response exposes a safe source descriptor
and normalized diagnostic fields. It does not expose `stored_file_path`.

```json
{
  "source_document": {
    "document_id": "uuid",
    "original_filename": "office-supplies.pdf",
    "mime_type": "application/pdf",
    "content_url": "/api/v1/documents/uuid/content",
    "availability": "available",
    "content_quality": "partial"
  },
  "extraction_context": {
    "extraction_method": "pdf_hybrid",
    "source_page_count": 11,
    "processed_page_count": 10,
    "page_limit_applied": true,
    "text_page_numbers": [1, 2, 3],
    "vision_page_numbers": [4, 5],
    "rendered_page_numbers": [4, 5],
    "warnings": ["Only the first 10 pages were processed."],
    "low_confidence_fields": [],
    "risk_flags": ["partial_document_page_limit"]
  }
}
```

Only normalized diagnostic metadata is exposed. Raw base64 visual pages, API keys,
internal paths, and provider request payloads are excluded.

### 5.3 Document Content Endpoint

Planned endpoint:

```text
GET /api/v1/documents/{document_id}/content
```

Planned success behavior:

- Resolve the document by UUID through PostgreSQL.
- Resolve and normalize the stored path on the server.
- Require the resolved path to remain inside the configured upload storage root.
- Require a supported PDF or image media type and serve the stored bytes without
  transforming accounting content.
- Return the persisted MIME type after server-side validation.
- Use a safely encoded original filename for inline display.
- Support byte-range responses needed by browser PDF viewers when the response stack
  provides them.

Planned response headers:

| Header | Planned Value or Behavior |
|---|---|
| `Content-Type` | Validated PDF/JPEG/PNG/WebP MIME type. |
| `Content-Disposition` | `inline` with a safely encoded original filename. |
| `X-Content-Type-Options` | `nosniff`. |
| `Cache-Control` | `private, no-store` for the portfolio implementation. |
| `Accept-Ranges` | `bytes` when range support is available. |

Planned failures:

| HTTP | Stable Code | Condition |
|---:|---|---|
| `400` | `invalid_document_id` | UUID syntax is invalid. |
| `404` | `document_not_found` | No document row exists. |
| `410` | `source_content_unavailable` | The document exists but the stored source is missing or cannot be served safely. |
| `415` | `unsupported_source_media_type` | The persisted source type cannot be rendered by the supported review contract. |

Server logs and audit diagnostics may retain a safe internal reason. API errors must not
include absolute paths or filesystem exception details.

The portfolio version continues to use its demo-user authentication boundary. When
identity and authorization are added, this endpoint must use the same document-resource
authorization dependency as review detail.

---

## 6. Correction Payload and Validation

### 6.1 Allowlisted Fields

An extraction correction may contain only:

- `document_type`;
- `vendor_name`;
- `transaction_date`;
- `subtotal_amount`;
- `tax_amount`;
- `total_amount`;
- `currency`;
- `line_items` with `description`, `quantity`, `unit_price`, and `amount`.

Transport-only UI fields such as `payment_status` are not authoritative extraction
fields unless a later specification explicitly adds them to the data model. Provider
metadata, model confidence, risk flags, and original raw text cannot be overwritten by
an edit request.

### 6.2 Effective Payload

- **Approve as-is:** validate the original extraction review payload merged with the
  latest persisted extraction fields.
- **Edit and Continue:** merge only allowlisted edited fields over that effective payload,
  then validate the complete result.
- **Reject:** no correction validation is required, but the rejection and optional
  resolution note are audited.

The backend owns merge precedence and validation. Client-side validation may improve
feedback but cannot authorize continuation.

### 6.3 Deterministic Rules

The planned correction boundary reuses the extraction rules defined in
`docs/10-Hybrid-Document-Extraction.md`:

- document type is `invoice` or `receipt` before Bookkeeping;
- vendor is non-empty;
- transaction date is an exact valid `YYYY-MM-DD` date;
- currency is an uppercase three-letter code;
- monetary and line-item numeric values are finite and non-negative;
- total is present and greater than zero;
- subtotal plus tax matches total within `0.05` when all values are present;
- complete line-item amounts match subtotal within `0.05`.

Human correction resolves uncertainty about field values; it does not erase historical
source warnings or change the model-reported confidence. The audit trail records that a
human validated or edited the payload.

### 6.4 Validation Failure Response

Planned response: HTTP `422` with the standard API error envelope.

```json
{
  "error": {
    "code": "extraction_validation_failed",
    "message": "The extraction still contains fields that must be corrected.",
    "details": [
      {
        "field": "transaction_date",
        "code": "invalid_transaction_date",
        "message": "Use a valid date in YYYY-MM-DD format."
      }
    ],
    "warnings": [],
    "risk_flags": ["invalid_transaction_date"]
  }
}
```

On validation failure:

- the review remains `pending`;
- the document remains `extraction_review_required`;
- no Bookkeeping call or journal persistence occurs;
- the UI keeps the correction draft and associates errors with the affected fields;
- the failure may create a validation audit event without marking the review resolved.

---

## 7. Transaction and Idempotency Contract

### 7.1 Successful Continuation

The final persistence boundary must be caller-controlled and commit once. Within that
transaction it must:

1. Lock and reload the review item.
2. Confirm the item is still `pending` and its source document still exists.
3. Persist corrected extraction fields without replacing original provider metadata or
   model confidence with fabricated values.
4. Persist the Bookkeeping outcome through a helper that performs no internal commit.
5. Resolve the extraction review and update document status.
6. Append the human action and downstream workflow audit events.
7. Commit all changes together or roll all of them back.

If Bookkeeping fails before persistence, the extraction review remains pending and the
API returns a recoverable error. The system must not present a completed human decision
when downstream state was not saved consistently.

### 7.2 Duplicate and Concurrent Submission

- Only the first valid request may resolve a pending review.
- Repeated or concurrent requests must not create duplicate journals, review items,
  status transitions, or audit events.
- A request that loses the pending-state race returns `409 review_already_resolved` with
  the current review status and next workflow state where available.
- Existing unique pending-review and idempotent bookkeeping persistence safeguards
  should be reused rather than duplicated in the API layer.
- Transaction-race verification requires PostgreSQL; sequential SQLite tests alone are
  insufficient evidence for the concurrency claim.

---

## 8. Planned Review UI Contract

### 8.1 Evidence Panel

The Extraction Review view will replace decorative source artwork with:

- inline PDF viewing with page navigation;
- JPEG, PNG, and WebP image viewing with contained scaling;
- filename and validated media type;
- loading, unavailable, unsupported, and browser-render failure states;
- an Open Source action backed by the same controlled content endpoint.

If the source cannot be displayed, the UI must say so directly. It must not show a
placeholder that looks like the uploaded document.

### 8.2 Extraction Context

The review displays:

- original AI suggestion and any saved correction;
- model confidence and rationale;
- extraction method;
- source and processed page counts;
- text, vision, and rendered page coverage when available;
- warnings, low-confidence fields, and risk flags;
- a clear partial-processing notice when page limits or rendering failures apply.

Unknown facts remain unknown. In particular, a positive total does not prove that an
invoice was paid.

### 8.3 Actions

- **Confirm Extraction** validates the as-is effective payload before continuation.
- **Save Fields & Continue** submits the allowlisted correction and displays server field
  errors without closing the review.
- **Reject Item** records a deliberate human rejection.
- Action buttons remain disabled while a mutation is in flight to reduce accidental
  duplicate submissions; the backend remains responsible for concurrency safety.

### 8.4 Accessibility

- Viewer controls and review actions are keyboard reachable and visibly focused.
- PDF pages or images include a useful accessible label derived from safe metadata.
- Field errors are associated with their inputs and summarized for screen-reader users.
- Warning and source states use text/icons in addition to color.

---

## 9. Audit and Provenance

The original extraction remains distinguishable from the human decision. Planned audit
coverage includes:

| Event | Required Context |
|---|---|
| Source unavailable during review | Document ID, normalized public reason, and source state; no absolute path. |
| Correction validation failed | Review ID, stable field error codes, and risk flags. |
| Extraction approved | Review ID, original extraction ID, actor, resolution note, and effective payload reference. |
| Extraction edited | Review ID, allowlisted changed fields, actor, resolution note, and effective payload reference. |
| Bookkeeping continued | Corrected extraction ID, resulting journal/review IDs, status, and agent rationale/confidence. |

Sensitive content should not be copied into every audit event. Existing entity links and
bounded structured snapshots are preferred.

---

## 10. Planned Verification Matrix

| Area | Required Verification |
|---|---|
| Source endpoint | Valid PDF/JPEG/PNG/WebP response, correct MIME, inline filename, missing file, unsupported type, malformed UUID, and path-containment rejection. |
| Evidence UI | PDF multi-page navigation, image rendering, loading, missing source, unsupported/browser failure, and Open Source action. |
| Context UI | Warnings, risk flags, low-confidence fields, extraction method, and partial page coverage render from persisted metadata. |
| Approve as-is | Valid extraction continues; invalid extraction returns field errors and remains pending. |
| Edit and Continue | Valid correction continues; missing/invalid fields and inconsistent amounts remain pending. |
| Provenance | Original provider metadata/confidence is retained and human changes are auditable. |
| Idempotency | Repeated submission creates one downstream outcome and one resolution. |
| Concurrency | Two simultaneous valid submissions produce one winner and no duplicate persistence under PostgreSQL. |
| Regression | Existing digital, scanned, mixed, corrupt, encrypted, partial, bookkeeping, and audit paths remain valid. |

Frontend component testing is planned as part of Epic 15; it is not available at the
time this design is written. Browser or component tests must stub external model behavior
at a controlled boundary and must not claim real LLM accuracy.

---

## 11. Delivery and Documentation Map

| Task | Planned Deliverable |
|---|---|
| 15.1 | This design and planned alignment of PRD, Architecture, Agent Design, API, UX, and Test Plan. |
| 15.2 | Controlled source document endpoint and backend contract tests. |
| 15.3 | Real PDF/image evidence viewer and its frontend tests. |
| 15.4 | Persisted extraction diagnostic context in the review UI. |
| 15.5 | Shared deterministic correction validation for approve and edit actions. |
| 15.6 | Transactional and idempotent review continuation with concurrency coverage. |
| 15.7 | Frontend upload contract aligned to 10 MB, WebP, and Text & Vision terminology. |
| 15.8 | Full regression checks and conversion of verified planned claims into implemented documentation. |

At Task 15.8, update `docs/07-Demo-Plan.md` and
`docs/11-Hybrid-Extraction-Manual-Test.md`, and add the verified review handoff to
`docs/10-Hybrid-Document-Extraction.md`. Update `docs/03-Data-Model.md` or
`docs/09-Setup-Guide.md` only if the implementation changes schema, persistence, or
setup behavior.

---

## 12. Configuration Impact

Task 15.1 requires no `.env` changes. The planned source endpoint uses the existing
document storage configuration and does not require an external service or credential.

If later Epic 15 tasks introduce a configurable upload root, explicit content caching,
or a new browser-test service, those settings must be documented when they are actually
added. They are not current configuration requirements.
