"""Find what a diff changed and what depends on it.

Priority rules are deliberately simple and documented (see docs/ARCHITECTURE.md):

* high       - directly uses a symbol whose signature changed or that was removed
* potential  - directly uses a changed symbol, or is 2 hops from a signature change/removal,
               or depends on a shared utility (5+ direct dependents)
* low        - further away
These rank *where to look first*; they are not probabilities of a bug.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .ast_analyzer import Edge, RepoAnalysis, UnresolvedCall
from .dependency_graph import DependencyGraph, Reach
from .diff_parser import FileDiff

PRIORITY_LABELS = {
    "changed": "Directly changed",
    "high": "High-priority review",
    "potential": "Potential downstream impact",
    "low": "Low-priority potential impact",
    "insufficient": "Insufficient evidence",
}
PRIORITY_ORDER = {"high": 0, "potential": 1, "low": 2, "insufficient": 3}
SHARED_UTILITY_THRESHOLD = 5


@dataclass
class ChangedSymbol:
    id: str
    kind: str
    file: str
    change_type: str                    # modified | added | removed
    signature_before: str | None = None
    signature_after: str | None = None
    old_range: tuple[int, int] | None = None
    new_range: tuple[int, int] | None = None

    @property
    def signature_changed(self) -> bool:
        return bool(self.signature_before and self.signature_after and self.signature_before != self.signature_after)


@dataclass
class ModuleLevelChange:
    file: str
    lines: list[int]
    side: str            # "old" (removed lines) or "new" (added lines)
    description: str


@dataclass
class ImpactedSymbol:
    id: str
    kind: str
    file: str
    start_line: int
    end_line: int
    depth: int
    root: str
    path: list[Edge]
    priority: str
    reasons: list[str]
    heuristic: bool
    is_test: bool
    tests: list[str] = field(default_factory=list)   # tests whose path runs through this symbol

    @property
    def path_ids(self) -> list[str]:
        return [self.root] + [e.source for e in self.path]

    @property
    def call_site(self) -> Edge | None:
        return self.path[-1] if self.path else None


@dataclass
class ImpactReport:
    changed_files: list[str]
    other_changed_files: list[str]
    changed_symbols: list[ChangedSymbol]
    module_level_changes: list[ModuleLevelChange]
    impacted: list[ImpactedSymbol]
    related_tests: list[ImpactedSymbol]
    truncated: bool
    unresolved_notes: list[UnresolvedCall]
    parse_errors: dict[str, str]


def _ranges(lines: list[int]) -> list[list[int]]:
    groups: list[list[int]] = []
    for n in sorted(lines):
        if groups and n == groups[-1][-1] + 1:
            groups[-1].append(n)
        else:
            groups.append([n])
    return groups


def detect_changed_symbols(diffs: list[FileDiff], old: RepoAnalysis, new: RepoAnalysis,
                           old_files: dict[str, str], new_files: dict[str, str]):
    touched: dict[str, ChangedSymbol] = {}
    module_changes: list[ModuleLevelChange] = []

    def mark(sym, side: str) -> None:
        entry = touched.setdefault(sym.id, ChangedSymbol(sym.id, sym.kind, sym.file, "modified"))
        if side == "old":
            entry.old_range = (sym.start_line, sym.end_line)
        else:
            entry.new_range = (sym.start_line, sym.end_line)
            entry.file = sym.file

    for fd in diffs:
        if not fd.is_python:
            continue
        for side, path, lines, analysis, files in (
            ("old", fd.old_path, fd.deleted_old_lines(), old, old_files),
            ("new", fd.new_path, fd.added_new_lines(), new, new_files),
        ):
            if path is None:
                continue
            loose: list[int] = []
            for line in sorted(lines):
                sym = analysis.index.innermost_at(path, line)
                if sym is not None:
                    mark(sym, side)
                else:
                    loose.append(line)
            source_lines = (files.get(path) or "").split("\n")
            for group in _ranges(loose):
                text = " ".join(source_lines[n - 1].strip() for n in group if 0 < n <= len(source_lines))
                if not text:
                    continue
                kind = "import change" if text.startswith(("import ", "from ")) else "module-level code"
                module_changes.append(ModuleLevelChange(path, group, side, kind))

    for sym_id, entry in touched.items():
        before, after = old.index.get(sym_id), new.index.get(sym_id)
        before = before if before and before.status == "present" else None
        after = after if after and after.status == "present" else None
        if before and after:
            entry.change_type = "modified"
        elif after:
            entry.change_type = "added"
        else:
            entry.change_type = "removed"
        if before is not None:
            entry.signature_before = before.signature or None
        if after is not None:
            entry.signature_after = after.signature or None
    return sorted(touched.values(), key=lambda c: (c.file, c.id)), module_changes


def classify(depth: int, root: ChangedSymbol, reach: Reach, fan_in: int) -> tuple[str, list[str]]:
    breaking = root.signature_changed or root.change_type == "removed"
    why = "was removed" if root.change_type == "removed" else "changed its signature"
    reasons: list[str] = []
    if depth == 1 and breaking:
        priority = "high"
        reasons.append(f"Directly uses {root.id}, which {why}.")
    elif depth == 1:
        priority = "potential"
        reasons.append(f"Directly uses {root.id}, whose code changed.")
    elif depth == 2 and breaking:
        priority = "potential"
        reasons.append(f"Two hops from {root.id}, which {why}.")
    else:
        priority = "low"
        reasons.append(f"{depth} hops away from {root.id}.")
    if fan_in >= SHARED_UTILITY_THRESHOLD and priority == "low":
        priority = "potential"
        reasons.append(f"{root.id} is a shared utility with {fan_in} direct dependents.")
    if reach.heuristic:
        reasons.append("At least one link was resolved by matching a module name, not an exact import path.")
    return priority, reasons


def build_impact_report(
    diffs: list[FileDiff], old: RepoAnalysis, new: RepoAnalysis,
    old_files: dict[str, str], new_files: dict[str, str], max_depth: int, max_nodes: int,
) -> tuple[ImpactReport, DependencyGraph]:
    changed, module_changes = detect_changed_symbols(diffs, old, new, old_files, new_files)
    graph = DependencyGraph(new.edges)
    roots = {c.id: c for c in changed}
    reached, truncated = graph.reverse_reachable(list(roots), max_depth, max_nodes)

    impacted: list[ImpactedSymbol] = []
    tests: list[ImpactedSymbol] = []
    for sym_id, reach in reached.items():
        if reach.depth == 0 or sym_id in roots:
            continue
        sym = new.index.get(sym_id)
        if sym is None:
            continue
        root = roots[reach.root]
        fan_in = len({e.source for e in graph.direct_dependents(root.id)})
        priority, reasons = classify(reach.depth, root, reach, fan_in)
        item = ImpactedSymbol(
            id=sym_id, kind=sym.kind, file=sym.file, start_line=sym.start_line, end_line=sym.end_line,
            depth=reach.depth, root=root.id, path=reach.path, priority=priority, reasons=reasons,
            heuristic=reach.heuristic, is_test=sym.is_test,
        )
        (tests if sym.is_test else impacted).append(item)

    by_id = {i.id: i for i in impacted}
    for test in tests:
        for comp_id in test.path_ids:
            if comp_id in by_id:
                by_id[comp_id].tests.append(test.id)

    changed_names = {c.id.rsplit(".", 1)[-1] for c in changed}
    notes = [u for u in new.unresolved if "dynamic" in u.reason or u.expression.split("(")[0].rsplit(".", 1)[-1] in changed_names]

    impacted.sort(key=lambda i: (PRIORITY_ORDER[i.priority], i.depth, i.id))
    tests.sort(key=lambda t: (t.depth, t.id))
    report = ImpactReport(
        changed_files=[d.path for d in diffs if d.is_python],
        other_changed_files=[d.path for d in diffs if not d.is_python],
        changed_symbols=changed,
        module_level_changes=module_changes,
        impacted=impacted,
        related_tests=tests,
        truncated=truncated,
        unresolved_notes=notes[:25],
        parse_errors={**new.parse_errors},
    )
    return report, graph
