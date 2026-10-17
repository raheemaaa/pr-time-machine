"""The JSON structure Gemma must return, validated with Pydantic."""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

Severity = Literal["high", "medium", "low"]
Verdict = Literal["likely_affected", "possibly_affected", "likely_unaffected", "insufficient_context"]

SEVERITY_ALIASES = {"critical": "high", "major": "high", "moderate": "medium", "minor": "low", "info": "low"}
VERDICT_LABELS = {
    "likely_affected": "Likely affected",
    "possibly_affected": "Possibly affected",
    "likely_unaffected": "Likely unaffected",
    "insufficient_context": "Insufficient context",
}


class AIResponseError(ValueError):
    """The model's reply could not be turned into a valid analysis."""


class Evidence(BaseModel):
    file: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    description: str = ""


class AIFinding(BaseModel):
    title: str
    severity: Severity
    changed_symbol: str
    affected_symbol: str
    verdict: Verdict
    reasoning: str
    failure_scenario: str = ""
    impact_path: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    recommended_tests: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("severity", mode="before")
    @classmethod
    def _normalize_severity(cls, value):
        text = str(value).strip().lower()
        return SEVERITY_ALIASES.get(text, text)

    @field_validator("verdict", mode="before")
    @classmethod
    def _normalize_verdict(cls, value):
        return str(value).strip().lower().replace(" ", "_").replace("-", "_")


class AIAnalysis(BaseModel):
    summary: str
    findings: list[AIFinding] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)


def extract_json_object(text: str) -> dict:
    """Pull the first JSON object out of a model reply (tolerates ```json fences and extra prose)."""
    if not text or not text.strip():
        raise AIResponseError("The model returned an empty response.")
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise AIResponseError("The model reply did not contain a JSON object.")
    try:
        data = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as exc:
        raise AIResponseError(f"The model reply was not valid JSON ({exc.msg} at position {exc.pos}).") from exc
    if not isinstance(data, dict):
        raise AIResponseError("The model reply was JSON but not an object.")
    return data


def parse_ai_response(text: str) -> AIAnalysis:
    data = extract_json_object(text)
    try:
        return AIAnalysis.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:5])
        raise AIResponseError(f"The model reply did not match the required schema: {problems}") from exc
