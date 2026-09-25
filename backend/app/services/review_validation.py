"""Typed, deterministic validation of effective human-reviewed extractions."""

from typing import Any

from pydantic import ConfigDict, Field, ValidationError

from app.agents.schemas import DocumentExtractionResult, ExtractedLineItem
from app.services.extraction_validation import (
    ExtractionFieldError,
    ExtractionResultValidation,
    validate_extraction_result,
)

CORRECTION_FIELDS = frozenset(
    {
        "document_type",
        "vendor_name",
        "transaction_date",
        "currency",
        "subtotal_amount",
        "tax_amount",
        "total_amount",
        "line_items",
    }
)
LINE_ITEM_FIELDS = frozenset({"description", "quantity", "unit_price", "amount"})


class ReviewedLineItem(ExtractedLineItem):
    model_config = ConfigDict(strict=True)


class ReviewedExtraction(DocumentExtractionResult):
    model_config = ConfigDict(strict=True)
    currency: str = ""
    line_items: list[ReviewedLineItem] = Field(default_factory=list)


class ExtractionCorrectionError(ValueError):
    """Validation failed before any review mutation or downstream invocation."""

    def __init__(self, validation: ExtractionResultValidation) -> None:
        super().__init__("The extraction still contains fields that must be corrected.")
        self.validation = validation


def allowlisted_correction(payload: dict[str, Any]) -> dict[str, Any]:
    """Discard transport fields and prevent overrides of agent evidence or journals."""
    allowed = {key: value for key, value in payload.items() if key in CORRECTION_FIELDS}
    if isinstance(allowed.get("line_items"), list):
        allowed["line_items"] = [
            {key: value for key, value in item.items() if key in LINE_ITEM_FIELDS}
            if isinstance(item, dict)
            else item
            for item in allowed["line_items"]
        ]
    return allowed


def validate_review_extraction(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply structural checks and the same accounting rules as document intake."""
    try:
        extraction = ReviewedExtraction.model_validate(allowlisted_correction(payload))
    except ValidationError as exc:
        details = [
            ExtractionFieldError(
                field=".".join(str(part) for part in error["loc"]),
                code="invalid_" + str(error["loc"][0]),
                message=error["msg"],
            )
            for error in exc.errors(include_input=False, include_url=False)
        ]
        raise ExtractionCorrectionError(
            ExtractionResultValidation(
                is_valid=False,
                field_errors=details,
                risk_flags=list(dict.fromkeys(error.code for error in details)),
            )
        ) from None

    validation = validate_extraction_result(extraction)
    if not validation.is_valid:
        raise ExtractionCorrectionError(validation)
    return {**payload, **extraction.model_dump(include=CORRECTION_FIELDS)}
