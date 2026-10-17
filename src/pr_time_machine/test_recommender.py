"""Turn impact findings into a concrete, change-specific test plan."""

from __future__ import annotations

from dataclasses import dataclass, field

from .impact_analyzer import ChangedSymbol, ImpactedSymbol


@dataclass
class TestRecommendation:
    finding_id: str
    target: str
    text: str
    source: str  # "static" (rule-based) or "gemma"


@dataclass
class ExistingTest:
    id: str
    file: str
    line: int
    exercises: list[str] = field(default_factory=list)  # components on its path to the change
    tests_changed_code_directly: bool = False


def static_recommendation(item: ImpactedSymbol, root: ChangedSymbol) -> str:
    site = item.call_site
    where = f"{site.file}:{site.line}" if site else item.file
    first_hop = item.path[-1].target if item.path else root.id
    if root.change_type == "removed":
        return (f"`{item.id}` still depends on `{root.id}` (see {where}), which this change removes. "
                f"Run a test that exercises `{item.id}`; expect a failure until the dependency is updated.")
    if root.signature_changed and item.depth == 1:
        return (f"Call `{item.id}` and check that its use of `{root.id}` at {where} matches the new signature "
                f"`{root.signature_after}` (previously `{root.signature_before}`).")
    if item.depth == 1:
        return (f"Exercise `{item.id}` (uses `{root.id}` at {where}) and assert its result under the new "
                f"behaviour of `{root.id}`.")
    chain = " -> ".join(reversed(item.path_ids))
    return (f"Exercise `{item.id}` end to end; it reaches the change through {chain} "
            f"(first link at {where}, via `{first_hop}`).")
