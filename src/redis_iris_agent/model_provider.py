"""Builds a Pydantic AI model object from .env configuration.

Configure these three variables in your .env — nothing else needed:

    PROVIDER=anthropic          # anthropic | openai | openrouter | google
    MODEL_NAME=claude-sonnet-4-6
    API_KEY=sk-ant-...

The function ``build_model()`` reads them and returns a ready-to-use Pydantic AI
model that can be passed directly to ``Agent(...)``.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic_ai.models import Model

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class ModelConfigError(ValueError):
    """Raised when PROVIDER / MODEL_NAME / API_KEY are missing or unsupported."""


def build_model() -> Model:
    """Read PROVIDER, MODEL_NAME, API_KEY from env and return a Pydantic AI model."""
    load_dotenv()
    provider = os.getenv("PROVIDER", "").strip().lower()
    model_name = os.getenv("MODEL_NAME", "").strip()
    api_key = os.getenv("API_KEY", "").strip()

    if not provider:
        raise ModelConfigError(
            "PROVIDER is not set. Add one of these to your .env:\n"
            "  PROVIDER=anthropic\n"
            "  PROVIDER=openai\n"
            "  PROVIDER=openrouter\n"
            "  PROVIDER=google\n"
        )
    if not model_name:
        raise ModelConfigError(
            "MODEL_NAME is not set. Example:\n"
            "  MODEL_NAME=claude-sonnet-4-6\n"
            "  MODEL_NAME=gpt-4o\n"
            "  MODEL_NAME=meta-llama/llama-3.3-70b-instruct\n"
        )
    if not api_key:
        raise ModelConfigError(
            f"API_KEY is not set. Add your {provider} API key to .env:\n"
            "  API_KEY=your-key-here\n"
        )

    if provider == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider
        return AnthropicModel(model_name, provider=AnthropicProvider(api_key=api_key))

    if provider == "openai":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        return OpenAIChatModel(model_name, provider=OpenAIProvider(api_key=api_key))

    if provider == "openrouter":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        return OpenAIChatModel(
            model_name,
            provider=OpenAIProvider(base_url=OPENROUTER_BASE_URL, api_key=api_key),
        )

    if provider == "google":
        from pydantic_ai.models.gemini import GeminiModel
        from pydantic_ai.providers.google import GoogleProvider
        return GeminiModel(model_name, provider=GoogleProvider(api_key=api_key))

    raise ModelConfigError(
        f"Unsupported PROVIDER={provider!r}. "
        "Choose one of: anthropic, openai, openrouter, google"
    )
