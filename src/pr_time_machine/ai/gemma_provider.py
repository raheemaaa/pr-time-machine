"""Gemma 4 through the Gemini API, using the official Google Gen AI SDK (`google-genai`).

Follows https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api :
    client = genai.Client()
    client.models.generate_content(model="gemma-4-26b-a4b-it", contents=..., config=GenerateContentConfig(system_instruction=...))
"""

from __future__ import annotations

from ..config import SUPPORTED_GEMMA_MODELS
from .base_provider import AIProvider, AIProviderError


class GemmaProvider(AIProvider):
    is_mock = False

    def __init__(self, api_key: str, model: str, timeout_seconds: int = 120, client=None) -> None:
        if model not in SUPPORTED_GEMMA_MODELS:
            raise AIProviderError(
                f"'{model}' is not a Gemma 4 model listed for the Gemini API. "
                f"Use one of: {', '.join(SUPPORTED_GEMMA_MODELS)}."
            )
        if not api_key and client is None:
            raise AIProviderError("GEMINI_API_KEY is not set. Add it to your .env file.")
        self.model = model
        self.name = f"Gemma 4 ({model}) via Gemini API"
        from google.genai import types  # imported lazily so tests run without network access

        self._types = types
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=timeout_seconds * 1000))
        self._client = client

    def generate(self, system_instruction: str, prompt: str, context: dict) -> str:
        from google.genai import errors

        config = self._types.GenerateContentConfig(system_instruction=system_instruction, temperature=0.2)
        try:
            response = self._client.models.generate_content(model=self.model, contents=prompt, config=config)
        except errors.ClientError as exc:
            code = getattr(exc, "code", None)
            message = str(getattr(exc, "message", "") or "")
            if code == 429:
                raise AIProviderError("Gemma rate limit reached. Wait a minute and try again, or check your quota in Google AI Studio.", retryable=True) from exc
            if code in (401, 403):
                raise AIProviderError("The Gemini API rejected the API key. Check GEMINI_API_KEY in your .env file.") from exc
            if code == 404:
                raise AIProviderError(f"Model '{self.model}' was not found for this API key.") from exc
            if code == 400 and "token" in message.lower():
                raise AIProviderError("The code context is too long for the model. Lower the context budget in the sidebar.") from exc
            raise AIProviderError(f"The Gemini API returned an error ({code}): {message[:200]}") from exc
        except errors.ServerError as exc:
            raise AIProviderError("The Gemini API had a temporary server error. Try again shortly.", retryable=True) from exc
        except Exception as exc:  # network failures and timeouts come from the HTTP library
            if "timeout" in type(exc).__name__.lower() or "timed out" in str(exc).lower():
                raise AIProviderError("The request to Gemma timed out. Try again or lower the context budget.", retryable=True) from exc
            raise AIProviderError(f"Could not reach the Gemini API: {type(exc).__name__}.") from exc
        text = getattr(response, "text", None)
        if not text:
            raise AIProviderError("Gemma returned an empty response.", retryable=True)
        return text
