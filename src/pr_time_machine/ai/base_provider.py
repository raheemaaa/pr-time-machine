"""The interface every AI backend implements, so the analysis engine never depends on one vendor SDK."""

from __future__ import annotations

from abc import ABC, abstractmethod


class AIProviderError(RuntimeError):
    """A model call failed. The message is safe to show to users (never contains the API key)."""

    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class AIProvider(ABC):
    name: str = "unknown"
    model: str = ""
    is_mock: bool = False

    @abstractmethod
    def generate(self, system_instruction: str, prompt: str, context: dict) -> str:
        """Return the raw text reply. `context` holds structured facts (used by the mock provider)."""
