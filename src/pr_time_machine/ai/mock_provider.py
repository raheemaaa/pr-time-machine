"""A clearly labelled stand-in used when no Gemma API key is configured.

It performs NO reasoning: it echoes the static analysis in the same JSON shape
Gemma uses, so the full pipeline and interface can be developed and tested offline.
The UI shows a banner whenever this provider is active.
"""

from __future__ import annotations

import json

from .base_provider import AIProvider

SEVERITY = {"high": "high", "potential": "medium", "low": "low", "insufficient": "low"}


class MockProvider(AIProvider):
    name = "Mock provider (no AI model is called)"
    model = "mock"
    is_mock = True

    def generate(self, system_instruction: str, prompt: str, context: dict) -> str:
        findings = []
        for cand in context.get("candidates", []):
            findings.append({
                "title": "[MOCK] Structural dependency on changed code",
                "severity": SEVERITY.get(cand["priority"], "low"),
                "changed_symbol": cand["root"],
                "affected_symbol": cand["id"],
                "verdict": "insufficient_context",
                "reasoning": "Mock mode: no model was called. This repeats the static dependency path only.",
                "failure_scenario": "",
                "impact_path": cand["path"],
                "evidence": [cand["evidence"]] if cand.get("evidence") else [],
                "recommended_tests": [],
                "limitations": ["Mock provider: configure GEMINI_API_KEY to get real Gemma 4 reasoning."],
            })
        return json.dumps({
            "summary": "[MOCK] No AI reasoning was performed. Static analysis results are shown as-is.",
            "findings": findings,
            "unknowns": ["Mock mode is active."],
        })
