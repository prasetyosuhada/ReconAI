# Hybrid Document Extraction
## ReconAI — Technical Design and Implemented Behavior

**Version:** 1.0
**Status:** Implemented
**Last Updated:** 2026-09-10
**Related Documents:** `docs/01-PRD.md`, `docs/02-System-Architecture.md`, `docs/03-Data-Model.md`, `docs/04-Agent-Design.md`, `docs/05-API-Spec.md`, `docs/06-UX-Flow.md`, `docs/07-Demo-Plan.md`, `docs/08-Test-Plan.md`, `docs/09-Setup-Guide.md`
**Document Owner:** Prasetyo Suhada

---

## 1. Purpose

This document is the source of truth for ReconAI's implemented document-content
pipeline. It explains how digital PDFs, scanned PDFs, mixed PDFs, and image uploads
become structured accounting suggestions, where deterministic validation applies,
what is persisted, and when Human Review is mandatory.

ReconAI does not currently run a separate OCR engine. Embedded PDF text is extracted
locally, pages that need visual understanding are rendered locally, and the configured
multimodal LLM interprets the text and/or page images into structured accounting fields.

---

## 2. Design Boundaries

The pipeline separates three concerns:

| Concern | Owner | Behavior |
|---|---|---|
| Content preparation | `document_extraction.py` | Extract embedded text and prepare bounded visual pages without interpreting accounting meaning. |
| Semantic extraction | Document Intake Agent | Use a structured-output multimodal LLM to identify document type, vendor, date, currency, line items, and amounts. |
| Validation and routing | Deterministic services and LangGraph | Validate readability, required fields, money consistency, confidence, and review conditions. |

The filename and storage path are metadata only. They are never evidence for vendor,
date, currency, totals, line items, or any other accounting field.

---

## 3. End-to-End Flow

```text
Upload (PDF/JPEG/PNG/WebP, maximum 10 MB)
        │
        ▼
Store file + documents row + document_uploaded audit event
        │
        ▼
Prepare DocumentContent
  ├── PDF: inspect embedded text page by page
  │     ├── enough text -> retain text
  │     └── little/no text -> render bounded PNG for vision
  └── Image: preserve bytes as one visual page with normalized MIME
        │
        ▼
Deterministically validate content readability and completeness
        │
        ├── unreadable/corrupt/encrypted -> Human Review; do not call LLM
        ▼
Document Intake Agent sends text + ordered visual pages to multimodal LLM
        │
        ▼
Deterministically validate essential fields and monetary relationships
        │
        ├── low confidence, partial, missing, or inconsistent -> Human Review
        └── valid and confidence >= 0.85 -> Bookkeeping Agent
        │
        ▼
Persist extraction metadata + audit snapshot + downstream result
```

Processing is started as a FastAPI background task after upload. Redis Streams carry
live progress events; Redis is an observability channel and is not the source of truth
for the final document state.

---

## 4. `DocumentContent` Contract

Content preparation returns a provider-neutral Pydantic object:

```json
{
  "text": "embedded text retained from qualifying PDF pages",
  "visual_pages": [
    {
      "page_number": 2,
      "mime_type": "image/png",
      "image_base64": "...",
      "source": "rendered_pdf_page",
      "width_pixels": 1240,
      "height_pixels": 1755,
      "render_dpi": 150.0
    }
  ],
  "extraction_method": "pdf_hybrid",
  "warnings": [],
  "provider_metadata": {}
}
```

`extraction_method` has these values:

| Value | Meaning |
|---|---|
| `pdf_text` | All processed PDF pages supplied sufficient embedded text. |
| `pdf_vision` | All processed PDF pages required rendered visual input. |
| `pdf_hybrid` | The PDF contained both retained text pages and pages rendered for vision. |
| `scanned_pdf_fallback` | PDF inspection failed before usable content could be prepared, including corrupt or password-protected files. |
| `image_vision` | A supported image was prepared as one visual page. |
| `file_not_found` | The stored source file was unavailable. |
| `unsupported` | The source type was not supported by the extractor. |

Visual pages retain their one-based source page numbers. Rendered PDF pages use
`image/png`; uploaded images use their effective normalized MIME type.

---

## 5. PDF Classification and Rendering

PDF processing uses `pypdf` for embedded text and PyMuPDF for page rendering.

1. Inspect at most the first 10 pages.
2. Strip embedded text on each inspected page.
3. Classify a page as text when it contains at least 30 characters; otherwise classify
   it as requiring vision.
4. Keep qualifying text in page order.
5. Render only pages requiring vision to RGB PNG.
6. Request 150 DPI, reducing the effective DPI when necessary so one rendered page
   does not exceed 4,000,000 pixels.

If the source has more than 10 pages, the output is deliberately partial. Metadata and
warnings record that truncation, deterministic validation caps confidence at `0.70`,
and the workflow requires Human Review even if the processed pages look valid.

A low-text digital page may be routed to vision by this character-count heuristic. This
is intentional: the vision path is safer than discarding a page whose content cannot be
trusted from embedded text alone.

---

## 6. Image and Multimodal Intake

Supported image MIME types are `image/jpeg`, `image/jpg`, `image/png`, and
`image/webp`. The `image/jpg` alias is normalized to `image/jpeg`. Clients should send
the MIME type that matches the uploaded image bytes.

The Document Intake Agent receives:

- source MIME and the configured default currency;
- embedded text, when present;
- every prepared visual page in source order;
- a page label and a MIME-correct `data:` URL for each visual page.

The original filename and storage path are not placed in the human multimodal payload.
The system prompt also instructs the model to treat all document content as untrusted
data and ignore commands or prompt-like text found inside it.

The provider adapter supports Gemini and OpenAI structured outputs. Runtime defaults
are Gemini `gemini-3.1-flash-lite` or OpenAI `gpt-4o-mini`; Gemini is selected first when
both keys are configured. These defaults may change in code, so persisted runtime
metadata—not UI copy—is authoritative for a completed call.

---

## 7. Deterministic Validation and Safe Failure

### 7.1 Content validation

The LLM is not invoked when content preparation returns `file_not_found`, `unsupported`,
or `scanned_pdf_fallback`, or when there is neither readable text nor a visual page.
These conditions produce a reviewable result with confidence `0.0` and
`unreadable_document_content` or `empty_document_content` risk flags.

Partial page processing, a missing rendered page, or a scanned PDF with no visual pages
also forces Human Review and may cap confidence at `0.70`.

### 7.2 Structured-field validation

After the LLM responds, deterministic code validates:

- document type is not `unknown`;
- vendor is non-empty;
- date is an exact, valid `YYYY-MM-DD` date;
- currency is an uppercase three-letter code;
- subtotal, tax, total, quantity, unit price, and line-item amounts are finite and
  non-negative when present;
- total is present and greater than zero;
- subtotal plus tax matches total within `0.05`;
- complete line-item amounts sum to subtotal within `0.05`.

Failures add stable warnings, `low_confidence_fields`, and `risk_flags`, cap confidence,
and route the extraction to Human Review. Model-reported unreadability is normalized to
`needs_review`; an actual provider exception remains `failed`.

The route to Bookkeeping requires all of the following: successful intake, confidence
of at least `0.85`, no review requirement, a vendor, and a total amount.

---

## 8. Persistence and Audit Metadata

Structured fields are persisted in `document_extractions`. The `raw_text` column contains
retained embedded PDF text; ReconAI does not currently persist a separate full-page OCR
transcription for visual-only pages.

The existing JSONB `provider_metadata` column records content preparation and intake
observability without requiring a schema migration. Depending on source type, it can
contain:

| Metadata | Purpose |
|---|---|
| `source_mime_type`, `source_suffix`, `file_size_bytes` | Source facts. |
| `text_extractor`, `page_renderer` | Local libraries used. |
| `source_page_count`, `processed_page_count`, `page_limit`, `page_limit_applied` | Page-bound accounting. |
| `embedded_text_char_count`, `text_page_numbers`, `vision_page_numbers`, `rendered_page_numbers`, `page_classifications` | Per-page decisions. |
| `requested_render_dpi`, `max_rendered_page_pixels`, `visual_page_count` | Rendering bounds and output count. |
| `extraction_method`, `vision_processed_page_numbers`, `vision_page_mime_types` | Normalized pipeline outcome. |
| `llm_provider`, `llm_model` | Actual runtime provider and model when an LLM was called. |
| `durations_ms` | Content preparation, intake, and total measured durations. |
| `warnings`, `low_confidence_fields`, `risk_flags` | Review and diagnostic context. |

The same normalized metadata is copied into the `extraction_completed` audit event's
output snapshot. Raw base64 page images are not copied into provider metadata or audit
snapshots.

---

## 9. Progress Semantics

The document progress stream is available at
`GET /api/v1/documents/stream/{document_id}` as Server-Sent Events. The extraction-related
stages are deliberately named `content_extraction_started` and `content_extracted`; they
do not claim that a dedicated OCR service ran.

Current stage order is:

1. `init`
2. `content_extraction_started`
3. `content_extracted`
4. `coa_loaded`
5. `intake_agent`
6. `intake_done`
7. optional `bookkeeping_agent` notification followed by `bookkeeping_done`
8. optional `review_queued` or `journal_created`
9. `completed` or `error`

The frontend presents the first phase as **Text & Vision**. A Redis outage ends live
observation with an error event but does not cancel background document processing.

---

## 10. Operational Limits and Failure Behavior

| Boundary | Implemented Limit or Behavior |
|---|---|
| Upload size | Maximum 10 MB. |
| PDF pages | First 10 pages only; truncation always requires review. |
| PDF render target | 150 DPI. |
| Rendered page size | Maximum 4,000,000 pixels per page. |
| Corrupt/encrypted PDF | No password flow; fail safely to Human Review without an LLM call. |
| Missing/unrenderable content | Persist warnings and review routing; do not guess from filename. |
| Provider credentials | At least one of `GEMINI_API_KEY` or `OPENAI_API_KEY` is required for live semantic extraction of readable content. |
| Dedicated OCR credentials | None; no dedicated OCR provider is integrated. |

The extraction constants are application defaults, not `.env` settings. Changing them
requires a code change plus regression coverage.

---

## 11. Test Matrix

`backend/tests/test_document_extraction_matrix.py` is the focused Task 14.6 matrix. It
uses generated local fixtures and mocked LLM boundaries, so it does not require provider
credentials or make external calls.

Coverage includes:

- digital, scanned, and mixed multi-page PDFs;
- standalone image bytes and MIME preservation;
- low-detail/blurry image routing on model-reported low confidence;
- corrupt and encrypted PDF safe failure;
- default page and render bounds;
- ordered multi-page multimodal payloads;
- persisted review, audit, metadata, and absence of a journal for unreadable files.

These tests validate pipeline behavior, not real-world OCR/LLM accuracy. Extraction
accuracy remains unmeasured until a labeled golden-dataset benchmark is executed.

For repeatable UI/API steps, disposable fixture generation, expected outcomes, and the
manual evidence template, see
[`docs/11-Hybrid-Extraction-Manual-Test.md`](11-Hybrid-Extraction-Manual-Test.md).

---

## 12. Known Limitations

- No dedicated OCR engine or separately persisted OCR transcript exists.
- Password-protected PDFs cannot be unlocked.
- Only the first 10 PDF pages are processed.
- Page classification uses a character-count heuristic, not layout analysis.
- Image blur is not scored locally; the model's confidence is combined with deterministic
  field and amount validation.
- Visual pages are base64-encoded in memory for the provider call; object-storage-backed
  streaming is not implemented.
- Provider token usage is not currently persisted.

These limitations must remain visible in product and demo claims. Unreadable, partial,
or inconsistent output is reviewable rather than silently accepted.

---

## 13. Implementation Map

| Area | Source |
|---|---|
| Content schema | `backend/app/schemas/document_content.py` |
| PDF/image preparation | `backend/app/services/document_extraction.py` |
| Content and financial validation | `backend/app/services/extraction_validation.py` |
| Multimodal agent adapter | `backend/app/agents/document_intake.py` |
| Prompt guardrails | `backend/app/agents/prompts.py` |
| LangGraph routing | `backend/app/agents/orchestrator.py` |
| Persistence, audit, and progress | `backend/app/services/document_processing.py` |
| Upload and SSE endpoints | `backend/app/api/v1/documents.py` |
| Extraction matrix | `backend/tests/test_document_extraction_matrix.py` |
