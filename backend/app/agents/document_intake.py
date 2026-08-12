"""Document Intake Agent for ReconAI.

Extracts structured financial data from uploaded invoice/receipt documents or raw OCR
text using LLMs with Pydantic Structured Outputs.
"""

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.prompts import DOCUMENT_INTAKE_SYSTEM_PROMPT
from app.agents.schemas import DocumentExtractionResult, DocumentIntakeResponse
from app.core.llm import get_llm

logger = logging.getLogger(__name__)


def run_document_intake_agent(
    raw_text: str | None = None,
    original_filename: str = "document.pdf",
    mime_type: str = "application/pdf",
    demo_currency: str = "IDR",
    provider: str | None = None,
    model_name: str | None = None,
) -> DocumentIntakeResponse:
    """Execute Document Intake Agent to extract structured invoice/receipt data.

    Args:
        raw_text: Raw text or OCR output from the document.
        original_filename: Original file name.
        mime_type: MIME type of the uploaded file.
        demo_currency: Configured fallback demo currency (default "IDR").
        provider: Optional LLM provider override ('gemini' or 'openai').
        model_name: Optional LLM model override.

    Returns:
        DocumentIntakeResponse containing confidence score, rationale, and result.
    """
    logger.info("Executing Document Intake Agent for file: %s", original_filename)

    if not raw_text or not raw_text.strip():
        logger.warning("Empty text input provided to Document Intake Agent.")
        return DocumentIntakeResponse(
            agent_name="document_intake_agent",
            status="needs_review",
            confidence_score=0.0,
            rationale="No text content or readable OCR text was provided.",
            warnings=["Document contains no readable text content."],
            result=DocumentExtractionResult(
                document_type="unknown",
                currency=demo_currency,
                extraction_notes="Failed to extract: empty document text.",
            ),
        )

    try:
        llm = get_llm(provider=provider, model_name=model_name, temperature=0.0)
        structured_llm = llm.with_structured_output(DocumentIntakeResponse)

        system_prompt = DOCUMENT_INTAKE_SYSTEM_PROMPT.format(
            demo_currency=demo_currency
        )

        user_content = (
            f"Filename: {original_filename}\n"
            f"MIME Type: {mime_type}\n"
            f"Default Currency: {demo_currency}\n\n"
            f"--- DOCUMENT TEXT BEGIN ---\n"
            f"{raw_text}\n"
            f"--- DOCUMENT TEXT END ---"
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ]

        logger.info(
            "Sending document text (%d chars) to LLM (%s)...",
            len(raw_text),
            provider or "default",
        )

        response: DocumentIntakeResponse = structured_llm.invoke(messages)

        logger.info(
            "🤖 [LLM DocumentIntake] Extracted Vendor: '%s' | Date: '%s' | Total: %s %s | Conf: %.2f | Rationale: %s",
            response.result.vendor_name,
            response.result.transaction_date,
            response.result.total_amount,
            response.result.currency,
            response.confidence_score,
            response.rationale,
        )
        result = response.result
        warnings = list(response.warnings or [])

        # Heuristic 1: Check missing essential fields
        if not result.vendor_name or not result.total_amount:
            if "Vendor name or total amount is missing." not in warnings:
                warnings.append("Vendor name or total amount is missing.")
            status = "needs_review"
            confidence = min(response.confidence_score, 0.70)
        else:
            status = response.status
            confidence = response.confidence_score

        # Heuristic 2: Check subtotal + tax math consistency if both present
        if (
            result.subtotal_amount is not None
            and result.tax_amount is not None
            and result.total_amount is not None
        ):
            expected_total = round(result.subtotal_amount + result.tax_amount, 2)
            actual_total = round(result.total_amount, 2)
            if abs(expected_total - actual_total) > 0.05:
                math_warning = (
                    f"Subtotal ({result.subtotal_amount}) + Tax "
                    f"({result.tax_amount}) = {expected_total}, "
                    f"does not match Total ({result.total_amount})."
                )
                if math_warning not in warnings:
                    warnings.append(math_warning)
                status = "needs_review"
                confidence = min(confidence, 0.75)

        return DocumentIntakeResponse(
            agent_name="document_intake_agent",
            status=status,
            confidence_score=confidence,
            rationale=response.rationale,
            warnings=warnings,
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
            result=DocumentExtractionResult(
                document_type="unknown",
                currency=demo_currency,
                extraction_notes=f"Error: {str(e)}",
            ),
        )
