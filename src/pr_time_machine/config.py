"""Settings for PR Time Machine, loaded from environment variables (.env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Gemma 4 models listed in the official "Run Gemma with the Gemini API" docs:
# https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api
SUPPORTED_GEMMA_MODELS = ("gemma-4-26b-a4b-it", "gemma-4-31b-it")
DEFAULT_GEMMA_MODEL = "gemma-4-26b-a4b-it"


@dataclass
class Settings:
    ai_provider: str = "gemma"            # "gemma" or "mock"
    gemma_model: str = DEFAULT_GEMMA_MODEL
    api_key: str | None = None
    request_timeout_seconds: int = 120
    max_files: int = 2000                 # Python files read from one repository
    max_file_bytes: int = 512_000         # larger files are skipped
    max_total_bytes: int = 25_000_000     # total size of Python files read
    max_depth: int = 4                    # how many caller hops to follow
    max_nodes: int = 200                  # stop traversal after this many symbols
    context_budget_chars: int = 30_000    # source code sent to the model
    test_timeout_seconds: int = 180


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_settings() -> Settings:
    """Read settings from the environment. Never logs or returns the key in text form."""
    load_dotenv()
    return Settings(
        ai_provider=os.getenv("PRTM_AI_PROVIDER", "gemma").strip().lower(),
        gemma_model=os.getenv("PRTM_GEMMA_MODEL", DEFAULT_GEMMA_MODEL).strip(),
        api_key=(os.getenv("GEMINI_API_KEY") or "").strip() or None,
        request_timeout_seconds=_int_env("PRTM_REQUEST_TIMEOUT", 120),
        max_depth=_int_env("PRTM_MAX_DEPTH", 4),
        max_nodes=_int_env("PRTM_MAX_NODES", 200),
        context_budget_chars=_int_env("PRTM_CONTEXT_BUDGET", 30_000),
    )
