# Hybrid Extraction Manual Test Guide
## ReconAI — UI, API, Review, and Audit Verification

**Version:** 1.0
**Status:** Active Runbook
**Last Updated:** 2026-09-11
**Related Documents:** `docs/08-Test-Plan.md`, `docs/09-Setup-Guide.md`, `docs/10-Hybrid-Document-Extraction.md`
**Document Owner:** Prasetyo Suhada

---

## 1. Purpose

This runbook explains how to manually verify ReconAI's implemented hybrid document
pipeline through the UI and API. It covers digital PDFs, scanned PDFs, mixed PDFs,
images, low-quality images, multi-page limits, corrupt/encrypted files, upload limits,
Human Review routing, extraction metadata, audit events, and journal safeguards.

This guide verifies workflow behavior. It does not measure real-world OCR or LLM
accuracy. Model fields and confidence can vary between providers and runs; deterministic
pipeline, validation, and routing expectations are identified separately.

---

## 2. Prerequisites

Required locally:

- PostgreSQL and Redis from Docker Compose.
- Backend dependencies installed with `uv`.
- Frontend dependencies installed with `npm`.
- `jq` for the optional API inspection commands.
- At least one live LLM credential in the root `.env`:

```env
GEMINI_API_KEY=your_key
# or
OPENAI_API_KEY=your_key
```

No dedicated OCR credential is required. Without either LLM key, readable document
intake ends in provider failure; corrupt/encrypted safe-failure scenarios can still stop
before the LLM boundary.

Start dependencies from the repository root:

```bash
docker compose up -d
docker compose ps
```

Start the backend:

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run python app/db/seed.py
uv run uvicorn app.main:app --reload --port 8000
```

Start the frontend in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open:

- Documents UI: [http://localhost:5173/documents](http://localhost:5173/documents)
- API documentation: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 3. Prepare Manual Fixtures

Never damage the version-controlled demo documents. Generate disposable fixtures under
`/tmp/reconai-manual-test` from the existing office-supplies PDF.

Run from `backend/`:

```bash
uv run python - <<'PY'
from pathlib import Path

import pymupdf
from pypdf import PdfReader, PdfWriter

source_path = Path("../demo-data/invoices/invoice_02_office_supplies.pdf").resolve()
fixture_dir = Path("/tmp/reconai-manual-test")
fixture_dir.mkdir(parents=True, exist_ok=True)
source_bytes = source_path.read_bytes()

source_pdf = pymupdf.open(source_path)
source_page = source_pdf[0]

# Standalone image with normal resolution.
image_pixmap = source_page.get_pixmap(
    matrix=pymupdf.Matrix(1.5, 1.5),
    colorspace=pymupdf.csRGB,
    alpha=False,
)
(fixture_dir / "invoice-image.png").write_bytes(image_pixmap.tobytes("png"))

# Low-resolution image for a non-deterministic quality/confidence exercise.
low_quality_pixmap = source_page.get_pixmap(
    matrix=pymupdf.Matrix(0.12, 0.12),
    colorspace=pymupdf.csRGB,
    alpha=False,
)
(fixture_dir / "invoice-low-quality.png").write_bytes(
    low_quality_pixmap.tobytes("png")
)

# Scanned PDF: every source page is rasterized before insertion.
scanned_pdf = pymupdf.open()
for page in source_pdf:
    pixmap = page.get_pixmap(
        matrix=pymupdf.Matrix(1.5, 1.5),
        colorspace=pymupdf.csRGB,
        alpha=False,
    )
    scanned_page = scanned_pdf.new_page(
        width=page.rect.width,
        height=page.rect.height,
    )
    scanned_page.insert_image(scanned_page.rect, stream=pixmap.tobytes("png"))
scanned_pdf.save(fixture_dir / "invoice-scanned.pdf")
scanned_pdf.close()

# Mixed PDF: page 1 retains embedded text; page 2 is a raster copy.
mixed_pdf = pymupdf.open()
mixed_pdf.insert_pdf(source_pdf, from_page=0, to_page=0)
mixed_page = mixed_pdf.new_page(
    width=source_page.rect.width,
    height=source_page.rect.height,
)
mixed_page.insert_image(mixed_page.rect, stream=image_pixmap.tobytes("png"))
mixed_pdf.save(fixture_dir / "invoice-mixed.pdf")
mixed_pdf.close()

# Page-limit fixture: 11 digital pages, one more than the processing limit.
long_pdf = pymupdf.open()
for _ in range(11):
    long_pdf.insert_pdf(source_pdf, from_page=0, to_page=0)
long_pdf.save(fixture_dir / "invoice-11-pages.pdf")
long_pdf.close()
source_pdf.close()

# Password-protected PDF.
reader = PdfReader(source_path)
writer = PdfWriter()
for page in reader.pages:
    writer.add_page(page)
writer.encrypt("manual-test-password")
with (fixture_dir / "invoice-encrypted.pdf").open("wb") as file:
    writer.write(file)

# Invalid upload and safe-failure fixtures.
(fixture_dir / "invoice-corrupt.pdf").write_bytes(source_bytes[:200])
(fixture_dir / "invoice-empty.pdf").write_bytes(b"")
(fixture_dir / "unsupported.txt").write_text("unsupported manual test")
(fixture_dir / "oversized.pdf").write_bytes(b"0" * (10 * 1024 * 1024 + 1))

print(f"Fixtures created in {fixture_dir}")
for fixture in sorted(fixture_dir.iterdir()):
    print(f"- {fixture.name}: {fixture.stat().st_size} bytes")
PY
```

The low-quality fixture is intentionally downsampled, not a calibrated blur benchmark.
For a stronger visual test, blur `invoice-image.png` in an image editor and save a new
PNG. The existing `invoice_06_blurry_low_confidence.pdf` contains embedded text and may
therefore exercise `pdf_text` rather than the actual vision path.

---

## 4. Standard UI Procedure

Repeat these steps for every accepted document fixture:

1. Open the Documents UI.
2. Drag or select one document.
3. Choose `invoice` unless the scenario specifically tests `unknown`.
4. Submit the upload.
5. Record the document UUID from the response, URL, or browser network panel.
6. Observe the live pipeline card.
7. Wait for `completed`, `review_queued`, or `error`.
8. Refresh the Documents list and record the final status.
9. For review scenarios, open Review Queue and inspect the pending extraction item.
10. Open Audit and inspect `extraction_completed` metadata.

The live pipeline should describe these phases without claiming dedicated OCR:

```text
Text & Vision
Intake Agent
Bookkeeping Agent (only when extraction can continue)
Guardrails & Save
```

Warnings, review routing, and persisted state are more important than a green-looking
completion message. A `completed` SSE event can still carry a final workflow status that
requires Human Review.

---

## 5. Optional API Procedure

Upload one fixture from a terminal:

```bash
RECON_UPLOAD_JSON=$(curl -sS \
  -F "file=@/tmp/reconai-manual-test/invoice-mixed.pdf" \
  -F "document_type=invoice" \
  http://localhost:8000/api/v1/documents/upload)

printf '%s\n' "$RECON_UPLOAD_JSON" | jq
RECON_DOCUMENT_ID=$(printf '%s\n' "$RECON_UPLOAD_JSON" | jq -r '.id')
```

Observe retained Redis Stream events:

```bash
curl -N \
  "http://localhost:8000/api/v1/documents/stream/$RECON_DOCUMENT_ID"
```

After processing finishes, inspect the extraction:

```bash
curl -sS \
  "http://localhost:8000/api/v1/documents/$RECON_DOCUMENT_ID/extractions/latest" \
  | jq '{
      status,
      vendor_name,
      transaction_date,
      subtotal_amount,
      tax_amount,
      total_amount,
      confidence_score,
      rationale,
      provider_metadata: (
        .provider_metadata
        | {
            extraction_method,
            source_page_count,
            processed_page_count,
            page_limit_applied,
            text_page_numbers,
            vision_page_numbers,
            vision_processed_page_numbers,
            vision_page_mime_types,
            llm_provider,
            llm_model,
            durations_ms,
            warnings,
            low_confidence_fields,
            risk_flags
          }
      )
    }'
```

Inspect pending extraction reviews for the document:

```bash
curl -sS \
  "http://localhost:8000/api/v1/review-items?status=pending&review_type=extraction" \
  | jq --arg document_id "$RECON_DOCUMENT_ID" \
      '.items[] | select(.source_id == $document_id)'
```

Verify whether a journal was created:

```bash
curl -sS \
  "http://localhost:8000/api/v1/ledger?document_id=$RECON_DOCUMENT_ID" \
  | jq '{total, items}'
```

Inspect the extraction audit event:

```bash
curl -sS \
  "http://localhost:8000/api/v1/audit-log/$RECON_DOCUMENT_ID" \
  | jq '.timeline[] | select(.event_type == "extraction_completed")'
```

If `extractions/latest` initially returns `404`, processing has not persisted the
extraction yet. Wait for a terminal progress event and retry.

---

## 6. Scenario Matrix and Expected Results

### 6.1 Accepted documents

| Scenario | Fixture | Deterministic expectation |
|---|---|---|
| Digital PDF | `demo-data/invoices/invoice_02_office_supplies.pdf` | `pdf_text`; `text_page_numbers: [1]`; no vision pages. |
| Scanned PDF | `invoice-scanned.pdf` | `pdf_vision`; `vision_page_numbers: [1]`; rendered page MIME is PNG. |
| Mixed PDF | `invoice-mixed.pdf` | `pdf_hybrid`; text page `[1]`; vision/rendered page `[2]`; visual order preserved. |
| Standalone image | `invoice-image.png` | `image_vision`; one uploaded visual page with `image/png`. |
| Low-quality image | `invoice-low-quality.png` or manually blurred PNG | `image_vision`; image reaches the LLM. Extracted fields, confidence, and review outcome are provider-dependent. |
| Eleven-page PDF | `invoice-11-pages.pdf` | Only pages 1–10 processed; `page_limit_applied: true`; `partial_document_page_limit`; confidence capped at `0.70`; extraction review required. |

For the unmodified digital fixture, the expected source values are:

| Field | Expected value |
|---|---|
| Vendor | `PT Paper & Supplies Indo` |
| Transaction date | `2026-08-03` |
| Subtotal | `405405.00` |
| Tax | `44595.00` |
| Total | `450000.00` |
| Currency | `IDR` |

These field values are semantic-model expectations and should be recorded as observed
results. Page classification, limits, safe routing, and deterministic financial checks
are the hard pass/fail assertions.

### 6.2 Unreadable and rejected inputs

| Scenario | Fixture | Deterministic expectation |
|---|---|---|
| Corrupt PDF | `invoice-corrupt.pdf` | `scanned_pdf_fallback`; no LLM call; confidence `0.0`; extraction review; no journal. |
| Encrypted PDF | `invoice-encrypted.pdf` | Same safe-failure behavior as corrupt PDF; password is not requested or guessed. |
| Empty file | `invoice-empty.pdf` | Upload rejected with HTTP `400`; no document workflow starts. |
| Unsupported type | `unsupported.txt` | Upload rejected with HTTP `400`; no document workflow starts. |
| Over 10 MB | `oversized.pdf` | Upload rejected with HTTP `413`; no document workflow starts. |

For the corrupt-file guardrail, optionally rename the fixture to something containing
fake accounting data, such as `PT-Acme-IDR-999999.pdf`. The persisted extraction must not
derive vendor, currency, or total from that filename.

---

## 7. Human Review and Persistence Checks

For corrupt, encrypted, partial, or deterministically invalid extraction results, verify:

- document status is `extraction_review_required`;
- the latest extraction status is `draft`;
- a pending review with `review_type: extraction` exists;
- review payload includes relevant `warnings`, `low_confidence_fields`, and `risk_flags`;
- `extraction_completed` contains the same normalized provider metadata;
- no journal entry exists for unreadable content;
- corrupt/encrypted content has `llm_provider: null` and `llm_model: null`;
- no value was inferred from the filename.

For a valid high-confidence extraction, verify:

- intake can continue to Bookkeeping;
- extraction status is `extracted`;
- runtime provider/model and durations are persisted;
- subtotal, tax, and total are deterministically consistent;
- any Bookkeeping review is distinguishable from an Extraction review.

---

## 8. Pass/Fail Evidence Template

Record one row per scenario:

| Field | Value |
|---|---|
| Test date/time | |
| Tester | |
| Git commit | |
| Provider/model | |
| Fixture | |
| Document UUID | |
| Extraction method | |
| Text page numbers | |
| Vision page numbers | |
| Warnings/risk flags | |
| Final document status | |
| Review item created | |
| Journal created | |
| Audit metadata verified | |
| Observed semantic fields | |
| Result | Pass / Fail / Inconclusive |
| Notes or screenshots | |

Use `Inconclusive` rather than `Fail` when only a non-deterministic blur-confidence
expectation differs. Use `Fail` for broken contracts such as wrong page classification,
missing visual pages, absent safe review, filename-derived fields, exceeded resource
limits, or a journal created from unreadable content.

---

## 9. Completion Checklist

- [ ] Digital PDF verified as `pdf_text`.
- [ ] Scanned PDF verified as `pdf_vision`.
- [ ] Mixed PDF verified as `pdf_hybrid` with correct page numbers.
- [ ] PNG/JPEG/WebP image path verified as `image_vision`.
- [ ] Low-quality visual behavior recorded without claiming measured accuracy.
- [ ] Eleven-page PDF truncated and routed to extraction review.
- [ ] Corrupt PDF safely reviewed without an LLM call or journal.
- [ ] Encrypted PDF safely reviewed without an LLM call or journal.
- [ ] Empty, unsupported, and over-size uploads rejected correctly.
- [ ] Extraction `provider_metadata` verified.
- [ ] `extraction_completed` audit snapshot verified.
- [ ] Filename non-inference guardrail verified.
- [ ] Human Review and Bookkeeping outcomes distinguished.

Disposable fixtures live outside the repository and may be removed after evidence has
been captured. Database cleanup should follow the normal local reset procedure rather
than deleting individual accounting records without their related audit history.
