"""Document Text Extraction Utilities for ReconAI.

Extracts raw text from PDF files and images (JPG, PNG, WEBP) to feed into
the Document Intake LLM Agent. Uses pypdf for text-based PDFs and falls
back to passing image bytes directly to the LLM vision API for scanned/image PDFs.
"""

import base64
import logging
from pathlib import Path

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
) -> tuple[str, str | None]:
    """Extract text content and optional image base64 from a document file.

    Strategy:
    1. PDF with text → extract text via pypdf.
    2. PDF with no text (scanned) → build descriptive fallback string with image hint.
    3. Image (JPEG/PNG/WEBP) → build descriptive string and return base64 for LLM vision.

    Args:
        file_path: Absolute path to the stored file.
        mime_type: MIME type of the file (application/pdf, image/jpeg, etc.)

    Returns:
        Tuple of (raw_text, image_base64_or_None).
        - raw_text: Text to pass to document_intake LLM prompt.
        - image_base64: Base64-encoded image bytes (None if not an image input).
    """
    path = Path(file_path)

    if not path.exists():
        logger.error("Document file not found at path: %s", file_path)
        return "", None

    file_size_kb = path.stat().st_size / 1024
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
            return text, None

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
        return fallback_text, None

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
            return descriptive_text, image_b64

    logger.warning(
        "Unsupported file type for extraction: %s (MIME: %s)", path.name, mime_type
    )
    return "", None
