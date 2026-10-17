"""Export analysis results as Markdown or JSON. Reports never include settings or API keys."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone

from .ai.schemas import VERDICT_LABELS
from .evidence_validator import DEPENDENCY_LABELS
from .impact_analyzer import PRIORITY_LABELS
from .pipeline import AnalysisResult

SCENARIO_LABELS = {
    "not_analyzed": "Not analyzed by the model",
    "hypothesis": "Hypothesized failure scenario",
    "tested_failure": "Tested failure",
    "tests_passed": "Existing tests passed (does not prove safety)",
    "not_verified": "Not verified",
}


def _pct(value: float | None) -> str:
    return "n/a (no items)" if value is None else f"{value:.0%}"


def result_to_dict(result: AnalysisResult) -> dict:
    report = result.report
    data = {
        "tool": "PR Time Machine",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input": result.label,
        "ai_provider": result.provider_name,
        "mock_mode": result.is_mock,
        "ai_summary": result.ai_summary,
        "ai_error": result.ai_error,
        "changed_files": report.changed_files,
        "other_changed_files": report.other_changed_files,
        "changed_symbols": [asdict(c) | {"signature_changed": c.signature_changed} for c in report.changed_symbols],
        "module_level_changes": [asdict(m) for m in report.module_level_changes],
        "findings": [],
        "existing_tests": [asdict(t) for t in result.existing_tests],
        "recommended_tests": [asdict(r) for r in result.recommendations],
        "static_analysis_limits": [asdict(u) for u in report.unresolved_notes],
        "ai_unknowns": result.ai_unknowns,
        "context_omitted_for_budget": result.context_omitted,
        "warnings": result.warnings,
        "durations_seconds": result.durations,
    }
    for f in result.findings:
        data["findings"].append({
            "id": f.id, "affected_symbol": f.affected_symbol, "changed_symbol": f.changed_symbol,
            "priority": f.priority, "priority_label": PRIORITY_LABELS[f.priority],
            "priority_reasons": f.priority_reasons, "dependency_status": f.dependency_status,
            "scenario_status": f.scenario_status, "path": f.path, "call_site": f.call_site,
            "existing_tests": f.tests, "static_recommendation": f.static_recommendation, "source": f.source,
            "ai": f.ai.model_dump() if f.ai else None,
            "validation_problems": f.validation.problems if f.validation else [],
        })
    if result.execution:
        ex = result.execution
        data["test_execution"] = {
            "base": {"revision": ex.base.revision, "ran": ex.base.ran, "passed": sorted(ex.base.passed),
                     "failed": sorted(ex.base.failed), "errors": ex.base.errors},
            "head": {"revision": ex.head.revision, "ran": ex.head.ran, "passed": sorted(ex.head.passed),
                     "failed": sorted(ex.head.failed), "errors": ex.head.errors},
            "newly_failing": sorted(ex.newly_failing),
        }
    if result.comparison:
        data["prediction_check"] = asdict(result.comparison)
    return data


def to_json(result: AnalysisResult) -> str:
    return json.dumps(result_to_dict(result), indent=2, default=str)


def to_markdown(result: AnalysisResult) -> str:
    r = result.report
    out = [
        "# PR Time Machine impact report", "",
        f"- **Input:** {result.label}",
        f"- **AI reasoning:** {result.provider_name or 'off'}" + (" (MOCK: no model was called)" if result.is_mock else ""),
        f"- **Generated:** {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}", "",
        "> Static links show where a change *can* propagate. They are not proof that anything breaks. "
        "Model output is a hypothesis unless a test run confirms it.", "",
    ]
    if result.ai_summary:
        out += ["## Change summary", "", result.ai_summary, ""]
    if result.ai_error:
        out += ["## AI reasoning error", "", result.ai_error, ""]
    out += ["## Changed symbols", ""]
    for c in r.changed_symbols:
        sig = f" — signature `{c.signature_before}` → `{c.signature_after}`" if c.signature_changed else ""
        out.append(f"- `{c.id}` ({c.change_type}, {c.file}){sig}")
    for m in r.module_level_changes:
        out.append(f"- {m.file} lines {m.lines[0]}–{m.lines[-1]}: {m.description} ({m.side} version)")
    out += ["", "## Findings", ""]
    if not result.findings:
        out.append("No dependents of the changed code were found by static analysis.")
    for f in result.findings:
        out += [
            f"### {f.id}. `{f.affected_symbol}` — {PRIORITY_LABELS[f.priority]}", "",
            f"- **Dependency:** {DEPENDENCY_LABELS.get(f.dependency_status, f.dependency_status)}",
            f"- **Scenario status:** {SCENARIO_LABELS.get(f.scenario_status, f.scenario_status)}",
            f"- **Path:** {' ← '.join(f'`{p}`' for p in f.path)}" if f.path else "- **Path:** none found",
        ]
        if f.call_site:
            out.append(f"- **Call site:** {f.call_site}")
        out += [f"- **Why it is ranked here:** {' '.join(f.priority_reasons)}"]
        if f.ai:
            out += [f"- **Gemma verdict:** {VERDICT_LABELS[f.ai.verdict]} ({f.ai.severity})",
                    f"- **Reasoning:** {f.ai.reasoning}"]
            if f.ai.failure_scenario:
                out.append(f"- **Failure scenario:** {f.ai.failure_scenario}")
            for ev in f.ai.evidence:
                out.append(f"- **Evidence:** {ev.file}:{ev.start_line}-{ev.end_line} {ev.description}")
        if f.validation and f.validation.problems:
            out.append(f"- **Evidence check problems:** {'; '.join(f.validation.problems)}")
        if f.tests:
            out.append(f"- **Existing tests on this path:** {', '.join(f'`{t}`' for t in f.tests)}")
        out.append("")
    out += ["## Test plan", "", "### Existing tests that reach the change", ""]
    out += [f"- `{t.id}` ({t.file}:{t.line})" for t in result.existing_tests] or ["- None found."]
    out += ["", "### Recommended tests", ""]
    out += [f"- [{rec.finding_id}, {rec.source}] {rec.text}" for rec in result.recommendations] or ["- None."]
    if result.execution:
        ex = result.execution
        out += ["", "### Test execution (ran locally)", "",
                f"- Base `{ex.base.revision}`: {len(ex.base.passed)} passed, {len(ex.base.failed)} failed",
                f"- Head `{ex.head.revision}`: {len(ex.head.passed)} passed, {len(ex.head.failed)} failed",
                f"- Newly failing: {', '.join(f'`{t}`' for t in sorted(ex.newly_failing)) or 'none'}"]
        for err in ex.base.errors + ex.head.errors:
            out.append(f"- Problem: {err}")
    if result.comparison:
        c = result.comparison
        out += ["", "### Prediction check", "", f"Basis: {c.basis}.", "",
                f"- Predicted tests: {len(c.predicted)}; newly failing tests: {len(c.actual)}; overlap: {len(c.true_positives)}",
                f"- Precision: {_pct(c.precision)}; recall: {_pct(c.recall)}"]
    out += ["", "## Limitations of this analysis", ""]
    limits = [f"{u.file}:{u.line} `{u.expression}` — {u.reason}" for u in r.unresolved_notes]
    limits += result.warnings
    if result.context_omitted:
        limits.append(f"Not sent to the model (context budget): {', '.join(result.context_omitted)}")
    limits.append("Only Python files are analyzed; calls resolved at runtime may be missing.")
    out += [f"- {item}" for item in limits]
    return "\n".join(out) + "\n"
