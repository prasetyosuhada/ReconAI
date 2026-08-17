import logging
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

LLMProvider = Literal["gemini", "openai"]


def get_llm(
    provider: LLMProvider | None = None,
    model_name: str | None = None,
    temperature: float = 0.0,
) -> BaseChatModel:
    """Factory function to initialize and return a LangChain Chat Model instance.

    Supports 'gemini' and 'openai'.
    Defaults to 'gemini' if GEMINI_API_KEY is set, otherwise 'openai'.
    """
    # Auto-select provider if not specified
    if not provider:
        if settings.GEMINI_API_KEY:
            provider = "gemini"
        elif settings.OPENAI_API_KEY:
            provider = "openai"
        else:
            raise ValueError(
                "No LLM API key configured. "
                "Please set GEMINI_API_KEY or OPENAI_API_KEY in your .env file."
            )

    if provider == "gemini":
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is missing from environment variables.")

        selected_model = model_name or "gemini-3-flash-preview"
        logger.info("Initializing Gemini LLM model: %s", selected_model)
        return ChatGoogleGenerativeAI(
            model=selected_model,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=temperature,
        )

    elif provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is missing from environment variables.")

        selected_model = model_name or "gpt-4o-mini"
        logger.info("Initializing OpenAI LLM model: %s", selected_model)
        return ChatOpenAI(
            model=selected_model,
            api_key=settings.OPENAI_API_KEY,
            temperature=temperature,
        )

    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")
