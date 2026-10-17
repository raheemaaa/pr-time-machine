"""Check every claim in the model's output against the real repository.

The model may suggest something static analysis missed, but such claims are
labelled "unverified" until the repository itself confirms them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .ai.schemas import AIFinding
from .ast_analyzer import RepoAnalysis
from .dependency_graph import DependencyGraph
from .impact_analyzer import ImpactReport

DEPENDENCY_LABELS = {
    "confirmed_dependency": "Confirmed dependency",
    "unverified_relationship": "Not verified: no static dependency path",
    "invalid_reference": "Invalid reference",
}


@dataclass
class ValidationResult:
    dependency_status: str                     # confirmed_dependency | unverified_relationship | invalid_reference
    problems: list[str] = field(default_factory=list)
    valid_evidence: list[int] = field(default_factory=list)   # indexes into finding.evidence that passed


def validate_finding(
    finding: AIFinding, report: ImpactReport, new: RepoAnalysis, old: RepoAnalysis,
    graph: DependencyGraph, new_files: dict[str, str], old_files: dict[str, str],
) -> ValidationResult:
    problems: list[str] = []
    changed_ids = {c.id for c in report.changed_symbols}
    reachable = {i.id for i in report.impacted} | {t.id for t in report.related_tests}

    if finding.changed_symbol not in changed_ids:
        problems.append(f"'{finding.changed_symbol}' is not one of the changed symbols.")

    affected_known = finding.affected_symbol in new.index
    if not affected_known:
        problems.append(f"'{finding.affected_symbol}' does not exist in the repository.")

    valid_evidence: list[int] = []
    for n, ev in enumerate(finding.evidence):
        source = new_files.get(ev.file) or old_files.get(ev.file)
        if source is None:
            problems.append(f"Evidence file '{ev.file}' is not in the repository.")
            continue
        line_count = source.count("\n") + 1
        if ev.start_line > ev.end_line or ev.end_line > line_count:
            problems.append(f"Evidence lines {ev.start_line}-{ev.end_line} are outside {ev.file} (it has {line_count} lines).")
            continue
        valid_evidence.append(n)

    path = finding.impact_path
    for a, b in zip(path, path[1:]):
        if not graph.has_edge(a, b):
            problems.append(f"No static dependency links '{a}' and '{b}'.")

    if not affected_known:
        status = "invalid_reference"
    elif finding.affected_symbol in reachable:
        status = "confirmed_dependency"
    else:
        status = "unverified_relationship"
    return ValidationResult(status, problems, valid_evidence)
