"""Document Intake Agent for ReconAI.

Extracts structured financial data from uploaded invoice/receipt documents or raw OCR
text using LLMs with Pydantic Structured Outputs.
"""

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.prompts import DOCUMENT_INTAKE_SYSTEM_PROMPT
from app.agents.schemas import (
    DocumentExtractionResult,
    DocumentIntakeModelResponse,
    DocumentIntakeResponse,
)
from app.core.llm import get_llm
from app.schemas.document_content import DocumentContent, DocumentVisualPage
from app.services.extraction_validation import (
    DocumentContentValidation,
    validate_document_content,
    validate_extraction_result,
)

logger = logging.getLogger(__name__)


def run_document_intake_agent(
    raw_text: str | None = None,
    document_content: DocumentContent | None = None,
    original_filename: str = "document.pdf",
    mime_type: str = "application/pdf",
    demo_currency: str = "IDR",
    provider: str | None = None,
    model_name: str | None = None,
) -> DocumentIntakeResponse:
    """Execute Document Intake Agent to extract structured invoice/receipt data.

    Args:
        raw_text: Raw text or OCR output from the document.
        document_content: Structured text and visual pages from file extraction.
        original_filename: Original file name.
        mime_type: MIME type of the uploaded file.
        demo_currency: Configured fallback demo currency (default "IDR").
        provider: Optional LLM provider override ('gemini' or 'openai').
        model_name: Optional LLM model override.

    Returns:
        DocumentIntakeResponse containing confidence score, rationale, and result.
    """
    logger.info("Executing Document Intake Agent for file: %s", original_filename)

    effective_text = document_content.text if document_content else raw_text
    readable_text = (
        effective_text if effective_text and effective_text.strip() else None
    )
    visual_pages = document_content.visual_pages if document_content else []
    content_validation = (
        validate_document_content(document_content) if document_content else None
    )

    if content_validation and not content_validation.can_process:
        logger.warning(
            "Document content is not processable: %s",
            content_validation.risk_flags,
        )
        return _unreadable_content_response(
            demo_currency=demo_currency,
            validation=content_validation,
        )

    if not readable_text and not visual_pages:
        logger.warning("No readable content provided to Document Intake Agent.")
        return DocumentIntakeResponse(
            agent_name="document_intake_agent",
            status="needs_review",
            confidence_score=0.0,
            rationale="No readable text or visual page content was provided.",
            warnings=["Document contains no readable text or visual page content."],
            low_confidence_fields=[
                "document_type",
                "vendor_name",
                "transaction_date",
                "total_amount",
            ],
            risk_flags=["empty_document_content"],
            result=DocumentExtractionResult(
                document_type="unknown",
                currency=demo_currency,
                extraction_notes="Failed to extract: empty document text.",
            ),
        )

    try:
        llm = get_llm(provider=provider, model_name=model_name, temperature=0.0)
        structured_llm = llm.with_structured_output(DocumentIntakeModelResponse)

        system_prompt = DOCUMENT_INTAKE_SYSTEM_PROMPT.format(
            demo_currency=demo_currency
        )

        user_content = (
            f"Source MIME Type: {mime_type}\n"
            f"Default Currency: {demo_currency}\n\n"
            f"--- DOCUMENT TEXT BEGIN ---\n"
            f"{readable_text or '[No embedded text; use the visual pages.]'}\n"
            f"--- DOCUMENT TEXT END ---"
        )

        human_content: str | list[dict[str, object]] = user_content
        if visual_pages:
            human_content = [{"type": "text", "text": user_content}]
            for visual_page in visual_pages:
                human_content.extend(_visual_page_blocks(visual_page))

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_content),
        ]

        logger.info(
            "Sending document text (%d chars) and %d visual pages to LLM (%s)...",
            len(readable_text or ""),
            len(visual_pages),
            provider or "default",
        )

        response: DocumentIntakeModelResponse = structured_llm.invoke(messages)

        logger.info(
            "🤖 [LLM Intake] Vendor: '%s' | Total: %s %s | Conf: %.2f | Rationale: %s",
            response.result.vendor_name,
            response.result.total_amount,
            response.result.currency,
            response.confidence_score,
            response.rationale,
        )
        result = response.result
        result_validation = validate_extraction_result(result)
        warnings = _merge_unique(
            response.warnings,
            content_validation.warnings if content_validation else [],
            result_validation.warnings,
        )
        low_confidence_fields = _merge_unique(
            response.low_confidence_fields,
            result_validation.low_confidence_fields,
        )
        risk_flags = _merge_unique(
            content_validation.risk_flags if content_validation else [],
            result_validation.risk_flags,
        )
        confidence_caps = [
            cap
            for cap in (
                content_validation.confidence_cap if content_validation else None,
                result_validation.confidence_cap,
            )
            if cap is not None
        ]

        status = response.status
        confidence = response.confidence_score
        if response.status == "failed":
            status = "needs_review"
            confidence_caps.append(0.50)
            _append_unique(risk_flags, "model_reported_unreadable_document")
            _append_unique(
                warnings,
                "The model reported that the document content was unreadable.",
            )
        if (
            content_validation and content_validation.needs_review
        ) or not result_validation.is_valid:
            status = "needs_review"
        if confidence_caps:
            confidence = min(confidence, min(confidence_caps))

        return DocumentIntakeResponse(
            agent_name="document_intake_agent",
            status=status,
            confidence_score=confidence,
            rationale=response.rationale,
            warnings=warnings,
            low_confidence_fields=low_confidence_fields,
            risk_flags=risk_flags,
            result=result,
        )

    except Exception as e:
        logger.error("Error executing Document Intake Agent: %s", str(e), exc_info=True)
        return DocumentIntakeResponse(
            agent_name="document_intake_agent",
            status="failed",
            confidence_score=0.0,
            rationale=f"LLM execution error: {str(e)}",
            warnings=[f"Execution exception: {str(e)}"],
            risk_flags=["llm_provider_failure"],
            result=DocumentExtractionResult(
                document_type="unknown",
                currency=demo_currency,
                extraction_notes=f"Error: {str(e)}",
            ),
        )


def _visual_page_blocks(
    visual_page: DocumentVisualPage,
) -> list[dict[str, object]]:
    """Build ordered LangChain content blocks for one visual document page."""
    return [
        {
            "type": "text",
            "text": (
                f"--- VISUAL PAGE {visual_page.page_number} "
                f"({visual_page.mime_type}) ---"
            ),
        },
        {
            "type": "image_url",
            "image_url": {
                "url": (
                    f"data:{visual_page.mime_type};base64,{visual_page.image_base64}"
                )
            },
        },
    ]


def _unreadable_content_response(
    *,
    demo_currency: str,
    validation: DocumentContentValidation,
) -> DocumentIntakeResponse:
    """Create a reviewable response without invoking an LLM on unreadable content."""
    return DocumentIntakeResponse(
        agent_name="document_intake_agent",
        status="needs_review",
        confidence_score=0.0,
        rationale="Document content could not be read safely.",
        warnings=validation.warnings,
        low_confidence_fields=[
            "document_type",
            "vendor_name",
            "transaction_date",
            "total_amount",
        ],
        risk_flags=validation.risk_flags,
        result=DocumentExtractionResult(
            document_type="unknown",
            currency=demo_currency,
            extraction_notes="No readable document content was available.",
        ),
    )


def _merge_unique(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for value in group:
            _append_unique(merged, value)
    return merged


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
