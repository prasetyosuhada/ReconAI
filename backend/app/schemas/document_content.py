"""Structured content produced by document file extraction."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class DocumentExtractionMethod(StrEnum):
    """How readable content was obtained from an uploaded document."""

    PDF_TEXT = "pdf_text"
    PDF_VISION = "pdf_vision"
    PDF_HYBRID = "pdf_hybrid"
    SCANNED_PDF_FALLBACK = "scanned_pdf_fallback"
    IMAGE_VISION = "image_vision"
    FILE_NOT_FOUND = "file_not_found"
    UNSUPPORTED = "unsupported"


class DocumentVisualPage(BaseModel):
    """One page of visual document content prepared for a vision provider."""

    page_number: int = Field(..., ge=1)
    mime_type: str = Field(..., min_length=1)
    image_base64: str = Field(..., min_length=1, repr=False)
    source: Literal["uploaded_image", "rendered_pdf_page"]
    width_pixels: int | None = Field(default=None, ge=1)
    height_pixels: int | None = Field(default=None, ge=1)
    render_dpi: float | None = Field(default=None, gt=0)


class DocumentContent(BaseModel):
    """Provider-neutral text and visual content extracted from one document."""

    text: str = ""
    visual_pages: list[DocumentVisualPage] = Field(default_factory=list)
    extraction_method: DocumentExtractionMethod
    warnings: list[str] = Field(default_factory=list)
    provider_metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def primary_visual_page(self) -> DocumentVisualPage | None:
        """Return the first visual page as a convenience for preview consumers."""
        return self.visual_pages[0] if self.visual_pages else None
