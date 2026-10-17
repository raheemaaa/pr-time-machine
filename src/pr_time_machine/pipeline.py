"""The end-to-end analysis pipeline used by the Streamlit app and the benchmark.

1. Parse the diff and both versions of the code (deterministic).
2. Find changed symbols and everything that depends on them (deterministic).
3. Optionally ask Gemma 4 to judge each dependent, then validate its claims.
4. Optionally run the test suite at both revisions (local Git repos only, opt-in).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from .ai.base_provider import AIProvider, AIProviderError
from .ai.prompts import SYSTEM_INSTRUCTION, build_reasoning_request
from .ai.schemas import AIAnalysis, AIFinding, AIResponseError, parse_ai_response
from .ast_analyzer import RepoAnalysis, analyze_repository, collect_definitions
from .config import Settings
from .dependency_graph import DependencyGraph
from .diff_parser import FileDiff, parse_unified_diff
from .evidence_validator import ValidationResult, validate_finding
from .impact_analyzer import ImpactReport, build_impact_report
from .test_discovery import discover_tests
from .test_recommender import ExistingTest, TestRecommendation, static_recommendation
from .test_runner import TestExecution, compare_revisions

PREDICTED_VERDICTS = {"likely_affected", "possibly_affected"}


@dataclass
class AnalysisInput:
    old_files: dict[str, str]
    new_files: dict[str, str]
    diff_text: str
    label: str
    repo_path: Path | None = None
    base_rev: str | None = None
    head_rev: str | None = None
    run_tests: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class Finding:
    id: str
    affected_symbol: str
    changed_symbol: str
    priority: str                      # high | potential | low | insufficient
    priority_reasons: list[str]
    dependency_status: str             # confirmed_dependency | unverified_relationship | invalid_reference
    scenario_status: str               # not_analyzed | hypothesis | tested_failure | tests_passed | not_verified
    path: list[str]
    call_site: str | None
    file: str | None
    tests: list[str]
    static_recommendation: str | None
    ai: AIFinding | None = None
    validation: ValidationResult | None = None
    source: str = "static"             # "static" or "ai_only"


@dataclass
class TestComparison:
    predicted: list[str]
    actual: list[str]
    true_positives: list[str]
    precision: float | None
    recall: float | None
    basis: str


@dataclass
class AnalysisResult:
    label: str
    diffs: list[FileDiff]
    report: ImpactReport
    graph: DependencyGraph
    old: RepoAnalysis
    new: RepoAnalysis
    findings: list[Finding]
    existing_tests: list[ExistingTest]
    all_tests_found: int
    recommendations: list[TestRecommendation]
    provider_name: str | None
    is_mock: bool
    ai_summary: str | None
    ai_unknowns: list[str]
    ai_error: str | None
    context_omitted: list[str]
    execution: TestExecution | None
    comparison: TestComparison | None
    warnings: list[str]
    durations: dict[str, float]


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def run_ai(provider: AIProvider, prompt: str, context: dict, retries: int = 1) -> AIAnalysis:
    """Call the model, validate its JSON, and retry once with the error if the reply is malformed."""
    last_error: Exception | None = None
    current_prompt = prompt
    for attempt in range(retries + 1):
        try:
            raw = provider.generate(SYSTEM_INSTRUCTION, current_prompt, context)
            return parse_ai_response(raw)
        except AIResponseError as exc:
            last_error = exc
            current_prompt = (prompt + f"\n\nYour previous reply was rejected: {exc}. "
                              "Reply again with one valid JSON object that follows the structure exactly.")
        except AIProviderError as exc:
            last_error = exc
            if not exc.retryable or attempt == retries:
                break
            time.sleep(3)
    raise last_error  # type: ignore[misc]


def analyze(inp: AnalysisInput, settings: Settings, provider: AIProvider | None) -> AnalysisResult:
    durations: dict[str, float] = {}
    warnings = list(inp.warnings)
    t0 = time.monotonic()

    diffs = parse_unified_diff(inp.diff_text)
    old = analyze_repository(inp.old_files)
    new_index, _, _ = collect_definitions(inp.new_files)
    changed_paths = {d.old_path for d in diffs if d.old_path}
    removed = [s for sid, s in old.index.symbols.items()
               if sid not in new_index and s.file in changed_paths and s.kind != "module"]
    for sym in removed:
        sym.status = "removed"
    new = analyze_repository(inp.new_files, extra_symbols=removed)
    report, graph = build_impact_report(diffs, old, new, inp.old_files, inp.new_files,
                                        settings.max_depth, settings.max_nodes)
    durations["static_analysis"] = round(time.monotonic() - t0, 3)

    if not report.changed_files:
        warnings.append("The diff does not change any Python files, so there is nothing to trace.")
    for path, err in report.parse_errors.items():
        warnings.append(f"{path} could not be parsed ({err}); its symbols are missing from the analysis.")
    if report.truncated:
        warnings.append(f"Traversal stopped at depth {settings.max_depth} or {settings.max_nodes} symbols; some distant dependents are not listed.")

    roots = {c.id: c for c in report.changed_symbols}
    findings: list[Finding] = []
    for n, item in enumerate(report.impacted, start=1):
        site = item.call_site
        findings.append(Finding(
            id=f"F{n}", affected_symbol=item.id, changed_symbol=item.root, priority=item.priority,
            priority_reasons=item.reasons, dependency_status="confirmed_dependency",
            scenario_status="not_analyzed", path=item.path_ids,
            call_site=f"{site.file}:{site.line}" if site else None, file=item.file, tests=list(item.tests),
            static_recommendation=static_recommendation(item, roots[item.root]),
        ))

    ai_summary = ai_error = None
    ai_unknowns: list[str] = []
    omitted: list[str] = []
    if provider is not None and report.changed_symbols:
        t1 = time.monotonic()
        prompt, context, omitted = build_reasoning_request(
            report, old, new, inp.old_files, inp.new_files, settings.context_budget_chars)
        try:
            analysis = run_ai(provider, prompt, context)
            ai_summary, ai_unknowns = analysis.summary, analysis.unknowns
            by_symbol = {f.affected_symbol: f for f in findings}
            for ai_finding in analysis.findings:
                validation = validate_finding(ai_finding, report, new, old, graph, inp.new_files, inp.old_files)
                target = by_symbol.get(ai_finding.affected_symbol)
                if target is not None and target.ai is None:
                    target.ai, target.validation = ai_finding, validation
                    target.scenario_status = "hypothesis"
                    continue
                if ai_finding.affected_symbol in roots:
                    continue
                findings.append(Finding(
                    id=f"F{len(findings) + 1}", affected_symbol=ai_finding.affected_symbol,
                    changed_symbol=ai_finding.changed_symbol, priority="insufficient",
                    priority_reasons=["Suggested by the model; static analysis found no dependency path."],
                    dependency_status=validation.dependency_status, scenario_status="hypothesis",
                    path=ai_finding.impact_path, call_site=None, file=None, tests=[],
                    static_recommendation=None, ai=ai_finding, validation=validation, source="ai_only",
                ))
        except (AIProviderError, AIResponseError) as exc:
            ai_error = str(exc)
        durations["ai_reasoning"] = round(time.monotonic() - t1, 3)

    recommendations: list[TestRecommendation] = []
    for f in findings:
        if f.static_recommendation:
            recommendations.append(TestRecommendation(f.id, f.affected_symbol, f.static_recommendation, "static"))
        if f.ai and f.ai.verdict != "likely_unaffected":
            for text in f.ai.recommended_tests:
                recommendations.append(TestRecommendation(f.id, f.affected_symbol, text, "gemma"))

    test_symbols = {t.id: t for t in discover_tests(new.index)}
    existing = []
    for t in report.related_tests:
        sym = test_symbols.get(t.id)
        if sym:
            on_path = [p for p in t.path_ids if p in {i.id for i in report.impacted}]
            existing.append(ExistingTest(t.id, sym.file, sym.start_line, on_path, t.depth == 1))

    execution = comparison = None
    if inp.run_tests and inp.repo_path and inp.base_rev and inp.head_rev:
        t2 = time.monotonic()
        execution = compare_revisions(inp.repo_path, inp.base_rev, inp.head_rev, settings.test_timeout_seconds)
        durations["test_execution"] = round(time.monotonic() - t2, 3)
        newly = execution.newly_failing
        for f in findings:
            if not f.tests:
                f.scenario_status = "not_verified" if f.scenario_status != "hypothesis" else f.scenario_status
            elif any(t in newly for t in f.tests):
                f.scenario_status = "tested_failure"
            elif all(t in execution.head.passed for t in f.tests):
                f.scenario_status = "tests_passed"
        comparison = compare_predictions(findings, existing, newly, provider is not None and not getattr(provider, "is_mock", True) and ai_error is None)

    durations["total"] = round(time.monotonic() - t0, 3)
    return AnalysisResult(
        label=inp.label, diffs=diffs, report=report, graph=graph, old=old, new=new, findings=findings,
        existing_tests=existing, all_tests_found=len(test_symbols), recommendations=recommendations,
        provider_name=provider.name if provider else None, is_mock=bool(provider and provider.is_mock),
        ai_summary=ai_summary, ai_unknowns=ai_unknowns, ai_error=ai_error, context_omitted=omitted,
        execution=execution, comparison=comparison, warnings=warnings, durations=durations,
    )


def compare_predictions(findings: list[Finding], existing: list[ExistingTest], newly_failing: set[str],
                        used_model: bool) -> TestComparison:
    """Test-level check: which tests did we flag, and which actually started failing?"""
    if used_model:
        flagged = {f.affected_symbol for f in findings
                   if f.dependency_status == "confirmed_dependency"
                   and (f.ai is None or f.ai.verdict in PREDICTED_VERDICTS)}
        basis = "Gemma 4 verdicts (likely or possibly affected; components without a verdict count as flagged)"
    else:
        flagged = {f.affected_symbol for f in findings if f.dependency_status == "confirmed_dependency"}
        basis = "static analysis only (every connected component counts as flagged)"
    predicted = sorted({t.id for t in existing if t.tests_changed_code_directly or set(t.exercises) & flagged})
    actual = sorted(newly_failing)
    hits = sorted(set(predicted) & set(actual))
    return TestComparison(predicted, actual, hits, _ratio(len(hits), len(predicted)), _ratio(len(hits), len(actual)), basis)
