"""Deterministic validation for document content and extracted accounting fields."""

import math
import re
from datetime import date

from pydantic import BaseModel, Field

from app.agents.schemas import DocumentExtractionResult
from app.schemas.document_content import DocumentContent, DocumentExtractionMethod

AMOUNT_TOLERANCE = 0.05
ISO_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
UNREADABLE_EXTRACTION_METHODS = {
    DocumentExtractionMethod.FILE_NOT_FOUND,
    DocumentExtractionMethod.UNSUPPORTED,
    DocumentExtractionMethod.SCANNED_PDF_FALLBACK,
}


class DocumentContentValidation(BaseModel):
    """Whether extracted source content is safe to send to the intake agent."""

    can_process: bool
    needs_review: bool
    warnings: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    confidence_cap: float | None = Field(default=None, ge=0.0, le=1.0)


class ExtractionResultValidation(BaseModel):
    """Deterministic validation outcome for LLM-extracted accounting fields."""

    is_valid: bool
    warnings: list[str] = Field(default_factory=list)
    low_confidence_fields: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    confidence_cap: float | None = Field(default=None, ge=0.0, le=1.0)


def validate_document_content(content: DocumentContent) -> DocumentContentValidation:
    """Reject unreadable content and flag partial visual extraction for review."""
    warnings = list(content.warnings)
    risk_flags: list[str] = []
    has_text = bool(content.text.strip())
    has_visual_pages = bool(content.visual_pages)

    if content.extraction_method in UNREADABLE_EXTRACTION_METHODS:
        _append_unique(warnings, "Document content could not be read safely.")
        risk_flags.append("unreadable_document_content")
        return DocumentContentValidation(
            can_process=False,
            needs_review=True,
            warnings=warnings,
            risk_flags=risk_flags,
            confidence_cap=0.0,
        )

    if not has_text and not has_visual_pages:
        _append_unique(warnings, "Document contains no readable text or visual pages.")
        risk_flags.append("empty_document_content")
        return DocumentContentValidation(
            can_process=False,
            needs_review=True,
            warnings=warnings,
            risk_flags=risk_flags,
            confidence_cap=0.0,
        )

    needs_review = False
    if content.provider_metadata.get("page_limit_applied") is True:
        needs_review = True
        risk_flags.append("partial_document_page_limit")
        _append_unique(
            warnings,
            "Only part of the document was processed because the page limit "
            "was reached.",
        )

    vision_pages = _page_number_set(
        content.provider_metadata.get("vision_page_numbers")
    )
    rendered_pages = {page.page_number for page in content.visual_pages}
    missing_visual_pages = sorted(vision_pages - rendered_pages)
    if missing_visual_pages:
        needs_review = True
        risk_flags.append("unrendered_visual_pages")
        _append_unique(
            warnings,
            "Pages requiring vision were not rendered: "
            + ", ".join(str(page) for page in missing_visual_pages)
            + ".",
        )

    if (
        content.extraction_method == DocumentExtractionMethod.PDF_VISION
        and not has_visual_pages
    ):
        needs_review = True
        risk_flags.append("missing_pdf_visual_pages")
        _append_unique(warnings, "Scanned PDF has no rendered visual pages.")

    return DocumentContentValidation(
        can_process=has_text or has_visual_pages,
        needs_review=needs_review,
        warnings=warnings,
        risk_flags=risk_flags,
        confidence_cap=0.70 if needs_review else None,
    )


def validate_extraction_result(
    result: DocumentExtractionResult,
) -> ExtractionResultValidation:
    """Validate essential fields and monetary relationships deterministically."""
    warnings: list[str] = []
    low_confidence_fields: list[str] = []
    risk_flags: list[str] = []
    confidence_caps: list[float] = []

    if result.document_type == "unknown":
        _record_issue(
            warnings,
            low_confidence_fields,
            risk_flags,
            confidence_caps,
            warning="Document type could not be determined.",
            field="document_type",
            risk_flag="unknown_document_type",
            confidence_cap=0.70,
        )

    if not result.vendor_name or not result.vendor_name.strip():
        _record_issue(
            warnings,
            low_confidence_fields,
            risk_flags,
            confidence_caps,
            warning="Vendor name is missing.",
            field="vendor_name",
            risk_flag="missing_vendor_name",
            confidence_cap=0.70,
        )

    if not result.transaction_date:
        _record_issue(
            warnings,
            low_confidence_fields,
            risk_flags,
            confidence_caps,
            warning="Transaction date is missing.",
            field="transaction_date",
            risk_flag="missing_transaction_date",
            confidence_cap=0.70,
        )
    else:
        try:
            if not ISO_DATE_PATTERN.fullmatch(result.transaction_date):
                raise ValueError
            date.fromisoformat(result.transaction_date)
        except ValueError:
            _record_issue(
                warnings,
                low_confidence_fields,
                risk_flags,
                confidence_caps,
                warning="Transaction date must use a valid YYYY-MM-DD date.",
                field="transaction_date",
                risk_flag="invalid_transaction_date",
                confidence_cap=0.70,
            )

    if not ISO_CURRENCY_PATTERN.fullmatch(result.currency):
        _record_issue(
            warnings,
            low_confidence_fields,
            risk_flags,
            confidence_caps,
            warning="Currency must be a three-letter uppercase ISO code.",
            field="currency",
            risk_flag="invalid_currency",
            confidence_cap=0.70,
        )

    amount_values = {
        "subtotal_amount": result.subtotal_amount,
        "tax_amount": result.tax_amount,
        "total_amount": result.total_amount,
    }
    for field, value in amount_values.items():
        if value is not None and (not math.isfinite(value) or value < 0):
            _record_issue(
                warnings,
                low_confidence_fields,
                risk_flags,
                confidence_caps,
                warning=f"{field} must be a finite, non-negative amount.",
                field=field,
                risk_flag=f"invalid_{field}",
                confidence_cap=0.70,
            )

    if result.total_amount is None:
        _record_issue(
            warnings,
            low_confidence_fields,
            risk_flags,
            confidence_caps,
            warning="Total amount is missing.",
            field="total_amount",
            risk_flag="missing_total_amount",
            confidence_cap=0.70,
        )
    elif result.total_amount == 0:
        _record_issue(
            warnings,
            low_confidence_fields,
            risk_flags,
            confidence_caps,
            warning="Total amount must be greater than zero.",
            field="total_amount",
            risk_flag="invalid_total_amount",
            confidence_cap=0.70,
        )

    amounts_are_valid = all(
        value is None or (math.isfinite(value) and value >= 0)
        for value in amount_values.values()
    )
    if (
        amounts_are_valid
        and result.subtotal_amount is not None
        and result.tax_amount is not None
        and result.total_amount is not None
    ):
        expected_total = round(result.subtotal_amount + result.tax_amount, 2)
        actual_total = round(result.total_amount, 2)
        if abs(expected_total - actual_total) > AMOUNT_TOLERANCE:
            _record_issue(
                warnings,
                low_confidence_fields,
                risk_flags,
                confidence_caps,
                warning=(
                    f"Subtotal ({result.subtotal_amount}) + Tax "
                    f"({result.tax_amount}) = {expected_total}, "
                    f"does not match Total ({result.total_amount})."
                ),
                field="tax_amount",
                risk_flag="subtotal_tax_total_mismatch",
                confidence_cap=0.75,
            )

    line_item_amounts = [item.amount for item in result.line_items]
    line_items_are_valid = True
    for item in result.line_items:
        numeric_values = (item.quantity, item.unit_price, item.amount)
        if any(
            value is not None and (not math.isfinite(value) or value < 0)
            for value in numeric_values
        ):
            line_items_are_valid = False
            _record_issue(
                warnings,
                low_confidence_fields,
                risk_flags,
                confidence_caps,
                warning="Line item numeric values must be finite and non-negative.",
                field="line_items",
                risk_flag="invalid_line_item_amount",
                confidence_cap=0.70,
            )

    if (
        amounts_are_valid
        and line_items_are_valid
        and result.subtotal_amount is not None
        and line_item_amounts
        and all(
            amount is not None and math.isfinite(amount) for amount in line_item_amounts
        )
    ):
        line_item_total = round(
            sum(amount for amount in line_item_amounts if amount is not None), 2
        )
        subtotal = round(result.subtotal_amount, 2)
        if abs(line_item_total - subtotal) > AMOUNT_TOLERANCE:
            _record_issue(
                warnings,
                low_confidence_fields,
                risk_flags,
                confidence_caps,
                warning=(
                    f"Line item total ({line_item_total}) does not match "
                    f"Subtotal ({result.subtotal_amount})."
                ),
                field="line_items",
                risk_flag="line_item_subtotal_mismatch",
                confidence_cap=0.75,
            )

    return ExtractionResultValidation(
        is_valid=not risk_flags,
        warnings=warnings,
        low_confidence_fields=low_confidence_fields,
        risk_flags=risk_flags,
        confidence_cap=min(confidence_caps) if confidence_caps else None,
    )


def _page_number_set(value: object) -> set[int]:
    if not isinstance(value, list):
        return set()
    return {
        page_number
        for page_number in value
        if isinstance(page_number, int) and page_number >= 1
    }


def _record_issue(
    warnings: list[str],
    low_confidence_fields: list[str],
    risk_flags: list[str],
    confidence_caps: list[float],
    *,
    warning: str,
    field: str,
    risk_flag: str,
    confidence_cap: float,
) -> None:
    _append_unique(warnings, warning)
    _append_unique(low_confidence_fields, field)
    _append_unique(risk_flags, risk_flag)
    confidence_caps.append(confidence_cap)


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
