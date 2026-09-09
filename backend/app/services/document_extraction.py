"""Document content extraction utilities for ReconAI.

Produces provider-neutral structured content for the Document Intake workflow.
The current implementation uses pypdf for text-based PDFs and prepares uploaded
images for the existing single-image vision adapter. PDF page rendering is handled
by a later extraction pipeline task.
"""

import base64
import logging
from pathlib import Path

from app.schemas.document_content import (
    DocumentContent,
    DocumentExtractionMethod,
    DocumentVisualPage,
)

logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_MIMES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}


def extract_text_from_pdf(file_path: str) -> str:
    """Extract plain text from a PDF file using pypdf.

    Returns the concatenated text of all pages. If the PDF contains only
    scanned images (no embedded text), the result will be an empty string.

    Args:
        file_path: Absolute path to the PDF file.

    Returns:
        Extracted text string, or empty string on failure.
    """
    try:
        from pypdf import PdfReader  # type: ignore[import-untyped]

        reader = PdfReader(file_path)
        parts: list[str] = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                parts.append(text.strip())

        result = "\n\n".join(parts)
        logger.info(
            "pypdf extracted %d characters from %s (%d pages)",
            len(result),
            Path(file_path).name,
            len(reader.pages),
        )
        return result

    except Exception as e:
        logger.warning("pypdf extraction failed for %s: %s", file_path, e)
        return ""


def image_to_base64(file_path: str) -> str:
    """Read an image file and return its base64-encoded bytes.

    Used for passing image data directly to LLM vision APIs when OCR is
    unavailable or when the document is a scanned image.

    Args:
        file_path: Absolute path to the image file.

    Returns:
        Base64-encoded string of the image bytes.
    """
    try:
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        logger.warning("Failed to read image file %s: %s", file_path, e)
        return ""


def extract_document_content(
    file_path: str,
    mime_type: str,
) -> DocumentContent:
    """Extract provider-neutral text and visual content from a document file.

    Strategy:
    1. PDF with text → extract text via pypdf.
    2. PDF with no text (scanned) → build fallback string.
    3. Image (JPEG/PNG/WEBP) → build descriptive string and return base64.

    Args:
        file_path: Absolute path to the stored file.
        mime_type: MIME type of the file (application/pdf, image/jpeg, etc.)

    Returns:
        Structured content containing text, visual pages, extraction method,
        warnings, and provider metadata.
    """
    path = Path(file_path)

    if not path.exists():
        logger.error("Document file not found at path: %s", file_path)
        return DocumentContent(
            extraction_method=DocumentExtractionMethod.FILE_NOT_FOUND,
            warnings=["Document file was not found at the stored path."],
            provider_metadata={"source_mime_type": mime_type},
        )

    file_size_bytes = path.stat().st_size
    file_size_kb = file_size_bytes / 1024
    source_metadata = {
        "source_mime_type": mime_type,
        "source_suffix": path.suffix.lower(),
        "file_size_bytes": file_size_bytes,
    }
    logger.info(
        "Extracting content from %s (MIME: %s, Size: %.1f KB)",
        path.name,
        mime_type,
        file_size_kb,
    )

    # PDF documents
    if mime_type == "application/pdf" or path.suffix.lower() == ".pdf":
        text = extract_text_from_pdf(file_path)
        if text and len(text.strip()) > 30:
            logger.info("PDF text extraction succeeded (%d chars)", len(text))
            return DocumentContent(
                text=text,
                extraction_method=DocumentExtractionMethod.PDF_TEXT,
                provider_metadata={
                    **source_metadata,
                    "text_extractor": "pypdf",
                    "embedded_text_char_count": len(text),
                },
            )

        # PDF appears to be scanned — pass a descriptive fallback so LLM can
        # attempt extraction from filename context, or mark as needs_review.
        logger.warning(
            "PDF %s appears to be scanned/image-based (empty text), "
            "passing filename context to LLM.",
            path.name,
        )
        fallback_text = (
            f"[SCANNED PDF] Filename: {path.name}\n"
            "This document could not be read as plain text. "
            "It is likely a scanned invoice or receipt. "
            "Please extract any available structured data or flag for human review."
        )
        return DocumentContent(
            text=fallback_text,
            extraction_method=DocumentExtractionMethod.SCANNED_PDF_FALLBACK,
            warnings=[
                "PDF contains insufficient embedded text; scanned-page rendering "
                "is not yet available."
            ],
            provider_metadata={
                **source_metadata,
                "text_extractor": "pypdf",
                "embedded_text_char_count": len(text),
            },
        )

    # Image documents (JPEG, PNG, WEBP)
    if mime_type in SUPPORTED_IMAGE_MIMES or path.suffix.lower() in {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    }:
        image_b64 = image_to_base64(file_path)
        if image_b64:
            logger.info(
                "Image file %s encoded as base64 (%d bytes)",
                path.name,
                len(image_b64),
            )
            # Provide a descriptive text context alongside the image
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
