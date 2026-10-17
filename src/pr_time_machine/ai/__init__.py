"""AI providers. `create_provider` picks Gemma 4 when configured and the mock otherwise."""

from __future__ import annotations

from ..config import Settings
from .base_provider import AIProvider, AIProviderError
from .mock_provider import MockProvider


def create_provider(settings: Settings) -> tuple[AIProvider, str | None]:
    """Return (provider, warning). The warning explains why mock mode is active, if it is."""
    if settings.ai_provider == "mock":
        return MockProvider(), "Mock mode is selected (PRTM_AI_PROVIDER=mock). No AI model is called."
    if not settings.api_key:
        return MockProvider(), "GEMINI_API_KEY is not set, so mock mode is active. No AI model is called."
    try:
        from .gemma_provider import GemmaProvider

        return GemmaProvider(settings.api_key, settings.gemma_model, settings.request_timeout_seconds), None
    except AIProviderError as exc:
        return MockProvider(), f"{exc} Mock mode is active instead."


__all__ = ["AIProvider", "AIProviderError", "MockProvider", "create_provider"]
