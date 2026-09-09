"""Provider-neutral document content extraction utilities for ReconAI.

PDFs are inspected page by page. Pages with sufficient embedded text stay as
text, while image-based pages are rendered to bounded PNGs for a vision model.
The downstream agent still uses its legacy single-image adapter until Task 14.3.
"""

import base64
import logging
import math
from dataclasses import dataclass
from pathlib import Path

from app.schemas.document_content import (
    DocumentContent,
    DocumentExtractionMethod,
    DocumentVisualPage,
)

logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_MIMES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}

# Resource bounds for untrusted uploads. They are deliberately application
# defaults rather than environment settings so every deployment has safe limits.
MAX_PDF_PAGES = 10
MIN_EMBEDDED_TEXT_CHARS_PER_PAGE = 30
PDF_RENDER_DPI = 150
MAX_RENDERED_PAGE_PIXELS = 4_000_000


@dataclass(frozen=True)
class _PdfPageText:
    """Embedded text detected on one PDF page."""

    page_number: int
    text: str


def _extract_pdf_page_text(
    file_path: str,
    max_pages: int,
) -> tuple[int, list[_PdfPageText], list[str]]:
    """Read embedded text for a bounded number of PDF pages."""
    from pypdf import PdfReader  # type: ignore[import-untyped]

    reader = PdfReader(file_path)
    source_page_count = len(reader.pages)
    processed_page_count = min(source_page_count, max_pages)
    pages: list[_PdfPageText] = []
    warnings: list[str] = []

    for index in range(processed_page_count):
        try:
            text = (reader.pages[index].extract_text() or "").strip()
        except Exception as exc:
            text = ""
            logger.warning(
                "Embedded text extraction failed for page %d of %s: %s",
                index + 1,
                file_path,
                exc,
            )
            warnings.append(
                f"Embedded text extraction failed on PDF page {index + 1}; "
                "the page was prepared for vision instead."
            )
        pages.append(_PdfPageText(page_number=index + 1, text=text))

    return source_page_count, pages, warnings


def extract_text_from_pdf(file_path: str) -> str:
    """Extract embedded text from the safely bounded set of PDF pages.

    This compatibility helper retains the original plain-text API. Structured
    extraction uses the per-page data directly.
    """
    try:
        source_page_count, pages, _ = _extract_pdf_page_text(
            file_path,
            MAX_PDF_PAGES,
        )
        result = "\n\n".join(page.text for page in pages if page.text)
        logger.info(
            "pypdf extracted %d characters from %s (%d/%d pages)",
            len(result),
            Path(file_path).name,
            len(pages),
            source_page_count,
        )
        return result
    except Exception as exc:
        logger.warning("pypdf extraction failed for %s: %s", file_path, exc)
        return ""


def _render_pdf_pages(
    file_path: str,
    page_numbers: list[int],
    render_dpi: int,
    max_rendered_page_pixels: int,
) -> tuple[list[DocumentVisualPage], list[str]]:
    """Render selected PDF pages to PNG without exceeding the pixel budget."""
    import pymupdf

    visual_pages: list[DocumentVisualPage] = []
    warnings: list[str] = []

    try:
        document = pymupdf.open(file_path)
    except Exception as exc:
        logger.warning("PDF renderer could not open %s: %s", file_path, exc)
        return [], ["PDF pages that require vision could not be rendered."]

    try:
        for page_number in page_numbers:
            try:
                page = document.load_page(page_number - 1)
                page_area = page.rect.width * page.rect.height
                if page_area <= 0:
                    raise ValueError("page has invalid dimensions")

                scale = render_dpi / 72
                projected_pixels = page_area * scale * scale
                if projected_pixels > max_rendered_page_pixels:
                    scale *= math.sqrt(max_rendered_page_pixels / projected_pixels)

                pixmap = page.get_pixmap(
                    matrix=pymupdf.Matrix(scale, scale),
                    colorspace=pymupdf.csRGB,
                    alpha=False,
                )

                # Pixel dimensions are rounded by the renderer. Apply a small
                # second-pass reduction if rounding exceeded the hard budget.
                actual_pixels = pixmap.width * pixmap.height
                if actual_pixels > max_rendered_page_pixels:
                    scale *= math.sqrt(max_rendered_page_pixels / actual_pixels) * 0.99
                    pixmap = page.get_pixmap(
                        matrix=pymupdf.Matrix(scale, scale),
                        colorspace=pymupdf.csRGB,
                        alpha=False,
                    )

                visual_pages.append(
                    DocumentVisualPage(
                        page_number=page_number,
                        mime_type="image/png",
                        image_base64=base64.b64encode(pixmap.tobytes("png")).decode(
                            "utf-8"
                        ),
                        source="rendered_pdf_page",
                        width_pixels=pixmap.width,
                        height_pixels=pixmap.height,
                        render_dpi=round(scale * 72, 2),
                    )
                )
            except Exception as exc:
                logger.warning(
                    "Failed to render page %d of %s: %s",
                    page_number,
                    file_path,
                    exc,
                )
                warnings.append(
                    f"PDF page {page_number} requires vision but could not be rendered."
                )
    finally:
        document.close()

    return visual_pages, warnings


def image_to_base64(file_path: str) -> str:
    """Read an image file and return its base64-encoded bytes."""
    try:
        with open(file_path, "rb") as file:
            return base64.b64encode(file.read()).decode("utf-8")
    except Exception as exc:
        logger.warning("Failed to read image file %s: %s", file_path, exc)
        return ""


def _extract_pdf_content(
    path: Path,
    source_metadata: dict[str, object],
    max_pdf_pages: int,
    pdf_render_dpi: int,
    max_rendered_page_pixels: int,
) -> DocumentContent:
    """Classify and extract a PDF page by page."""
    try:
        source_page_count, pages, warnings = _extract_pdf_page_text(
            str(path),
            max_pdf_pages,
        )
    except Exception as exc:
        logger.warning("pypdf extraction failed for %s: %s", path, exc)
        return DocumentContent(
            text=(
                f"[SCANNED PDF] Filename: {path.name}\n"
                "This document could not be read as plain text. "
                "Please flag it for human review."
            ),
            extraction_method=DocumentExtractionMethod.SCANNED_PDF_FALLBACK,
            warnings=["PDF page detection failed before content could be extracted."],
            provider_metadata={
                **source_metadata,
                "text_extractor": "pypdf",
                "embedded_text_char_count": 0,
            },
        )

    if source_page_count > max_pdf_pages:
        warnings.append(
            f"PDF has {source_page_count} pages; only the first "
            f"{max_pdf_pages} pages were processed."
        )

    text_pages = [
        page for page in pages if len(page.text) >= MIN_EMBEDDED_TEXT_CHARS_PER_PAGE
    ]
    vision_pages = [page for page in pages if page not in text_pages]
    visual_pages, render_warnings = _render_pdf_pages(
        str(path),
        [page.page_number for page in vision_pages],
        pdf_render_dpi,
        max_rendered_page_pixels,
    )
    warnings.extend(render_warnings)

    text = "\n\n".join(page.text for page in text_pages)
    if text_pages and vision_pages:
        extraction_method = DocumentExtractionMethod.PDF_HYBRID
    elif vision_pages:
        extraction_method = DocumentExtractionMethod.PDF_VISION
        # Retained for the legacy prompt adapter. Task 14.3 will remove this
        # filename-based fallback when all visual pages are sent to the model.
        text = (
            f"[SCANNED PDF] Filename: {path.name}\n"
            "The PDF pages were rendered for visual document extraction."
        )
    else:
        extraction_method = DocumentExtractionMethod.PDF_TEXT

    page_classifications = [
        {
            "page_number": page.page_number,
            "content_type": "text" if page in text_pages else "scanned",
            "embedded_text_char_count": len(page.text),
        }
        for page in pages
    ]
    embedded_text_char_count = sum(len(page.text) for page in pages)

    logger.info(
        "PDF %s classified %d text and %d vision pages (%d/%d processed)",
        path.name,
        len(text_pages),
        len(vision_pages),
        len(pages),
        source_page_count,
    )
    return DocumentContent(
        text=text,
        visual_pages=visual_pages,
        extraction_method=extraction_method,
        warnings=warnings,
        provider_metadata={
            **source_metadata,
            "text_extractor": "pypdf",
            "page_renderer": "pymupdf" if vision_pages else None,
            "source_page_count": source_page_count,
            "processed_page_count": len(pages),
            "page_limit": max_pdf_pages,
            "page_limit_applied": source_page_count > max_pdf_pages,
            "embedded_text_char_count": embedded_text_char_count,
            "text_page_numbers": [page.page_number for page in text_pages],
            "vision_page_numbers": [page.page_number for page in vision_pages],
            "rendered_page_numbers": [page.page_number for page in visual_pages],
            "visual_page_count": len(visual_pages),
            "page_classifications": page_classifications,
            "requested_render_dpi": pdf_render_dpi,
            "max_rendered_page_pixels": max_rendered_page_pixels,
        },
    )


def extract_document_content(
    file_path: str,
    mime_type: str,
    *,
    max_pdf_pages: int = MAX_PDF_PAGES,
    pdf_render_dpi: int = PDF_RENDER_DPI,
    max_rendered_page_pixels: int = MAX_RENDERED_PAGE_PIXELS,
) -> DocumentContent:
    """Extract bounded, provider-neutral text and visual document content."""
    if max_pdf_pages < 1:
        raise ValueError("max_pdf_pages must be at least 1")
    if pdf_render_dpi < 1:
        raise ValueError("pdf_render_dpi must be at least 1")
    if max_rendered_page_pixels < 1:
        raise ValueError("max_rendered_page_pixels must be at least 1")

    path = Path(file_path)
    if not path.exists():
        logger.error("Document file not found at path: %s", file_path)
        return DocumentContent(
            extraction_method=DocumentExtractionMethod.FILE_NOT_FOUND,
            warnings=["Document file was not found at the stored path."],
            provider_metadata={"source_mime_type": mime_type},
        )

    file_size_bytes = path.stat().st_size
    source_metadata: dict[str, object] = {
        "source_mime_type": mime_type,
        "source_suffix": path.suffix.lower(),
        "file_size_bytes": file_size_bytes,
    }
    logger.info(
        "Extracting content from %s (MIME: %s, Size: %.1f KB)",
        path.name,
        mime_type,
        file_size_bytes / 1024,
    )

    if mime_type == "application/pdf" or path.suffix.lower() == ".pdf":
        return _extract_pdf_content(
            path,
            source_metadata,
            max_pdf_pages,
            pdf_render_dpi,
            max_rendered_page_pixels,
        )

    if mime_type in SUPPORTED_IMAGE_MIMES or path.suffix.lower() in {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    }:
        image_b64 = image_to_base64(file_path)
        if image_b64:
            descriptive_text = (
                f"[IMAGE DOCUMENT] Filename: {path.name}, MIME: {mime_type}\n"
                "This is an invoice or receipt image. "
                "Extract all visible financial data from the image."
            )
            return DocumentContent(
                text=descriptive_text,
                visual_pages=[
                    DocumentVisualPage(
                        page_number=1,
                        mime_type=mime_type,
                        image_base64=image_b64,
                        source="uploaded_image",
                    )
                ],
                extraction_method=DocumentExtractionMethod.IMAGE_VISION,
                provider_metadata={
                    **source_metadata,
                    "image_encoder": "base64",
                    "visual_page_count": 1,
                },
            )

    logger.warning(
        "Unsupported file type for extraction: %s (MIME: %s)", path.name, mime_type
    )
    return DocumentContent(
        extraction_method=DocumentExtractionMethod.UNSUPPORTED,
        warnings=["Document type is not supported for content extraction."],
        provider_metadata=source_metadata,
    )
