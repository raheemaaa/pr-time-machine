import json
from types import SimpleNamespace

import pytest

from pr_time_machine.ai import create_provider
from pr_time_machine.ai.base_provider import AIProviderError
from pr_time_machine.ai.gemma_provider import GemmaProvider
from pr_time_machine.ai.mock_provider import MockProvider
from pr_time_machine.ai.prompts import build_reasoning_request
from pr_time_machine.ai.schemas import AIResponseError, parse_ai_response
from pr_time_machine.config import Settings
from pr_time_machine.pipeline import AnalysisInput, analyze, run_ai

VALID = {"summary": "s", "findings": [{
    "title": "t", "severity": "Critical", "changed_symbol": "a", "affected_symbol": "b",
    "verdict": "Likely affected", "reasoning": "r"}], "unknowns": []}


def test_parses_fenced_json_and_normalizes_labels():
    result = parse_ai_response("Here you go:\n```json\n" + json.dumps(VALID) + "\n```")
    assert result.findings[0].severity == "high" and result.findings[0].verdict == "likely_affected"


@pytest.mark.parametrize("text", ["", "no json here", "{not json}", json.dumps({"findings": []})])
def test_invalid_replies_raise_clear_errors(text):
    with pytest.raises(AIResponseError):
        parse_ai_response(text)


class FakeModels:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "system": config.system_instruction})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(text=reply)


def test_gemma_provider_uses_documented_call_and_retries_bad_json():
    models = FakeModels(["oops, not json", json.dumps(VALID)])
    provider = GemmaProvider("", "gemma-4-26b-a4b-it", client=SimpleNamespace(models=models))
    analysis = run_ai(provider, "prompt", {})
    assert analysis.summary == "s" and len(models.calls) == 2
    assert models.calls[0]["model"] == "gemma-4-26b-a4b-it" and "untrusted" in models.calls[0]["system"]


def test_rate_limit_error_is_mapped_to_friendly_message():
    from google.genai import errors

    models = FakeModels([errors.ClientError(429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}})])
    provider = GemmaProvider("", "gemma-4-31b-it", client=SimpleNamespace(models=models))
    with pytest.raises(AIProviderError, match="rate limit"):
        provider.generate("s", "p", {})


def test_unknown_model_names_are_refused():
    with pytest.raises(AIProviderError):
        GemmaProvider("key", "gemma-4-made-up", client=object())


def test_provider_factory_falls_back_to_labelled_mock():
    provider, warning = create_provider(Settings(ai_provider="gemma", api_key=None))
    assert isinstance(provider, MockProvider) and "GEMINI_API_KEY" in warning


def test_prompt_respects_budget_and_wraps_untrusted_code(sample, settings):
    old, new, diff = sample
    res = analyze(AnalysisInput(old, new, diff, "sample"), settings, None)
    prompt, context, omitted = build_reasoning_request(res.report, res.old, res.new, old, new, budget_chars=700)
    assert "<untrusted_repository_content>" in prompt and omitted
    assert len(context["candidates"]) == 5


def test_model_claim_outside_static_graph_becomes_unverified_finding(sample, settings):
    old, new, diff = sample
    reply = {"summary": "s", "unknowns": [], "findings": [{
        "title": "made up", "severity": "high", "changed_symbol": "shop.pricing.calculate_total",
        "affected_symbol": "shop.pricing.subtotal", "verdict": "likely_affected", "reasoning": "guess",
        "impact_path": ["shop.pricing.calculate_total", "shop.pricing.subtotal"]}]}
    provider = GemmaProvider("", "gemma-4-26b-a4b-it",
                             client=SimpleNamespace(models=FakeModels([json.dumps(reply)])))
    res = analyze(AnalysisInput(old, new, diff, "sample"), settings, provider)
    extra = [f for f in res.findings if f.source == "ai_only"]
    assert len(extra) == 1 and extra[0].priority == "insufficient"
    assert extra[0].dependency_status == "unverified_relationship"
