"""A directed graph of "A depends on B" relationships between symbols.

Edges point from the dependent symbol (a caller) to the symbol it uses.
Impact analysis walks the graph backwards: from a changed symbol to everything
that depends on it, using breadth-first search so each path is the shortest one.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from .ast_analyzer import Edge

# Relationships through which a change can propagate. Plain imports are excluded:
# importing a name does not prove it is ever called.
TRAVERSAL_KINDS = frozenset({"call", "instantiation", "reference", "inheritance", "decorator"})


@dataclass
class Reach:
    depth: int
    path: list[Edge] = field(default_factory=list)  # path[0].target is the changed symbol

    @property
    def root(self) -> str | None:
        return self.path[0].target if self.path else None

    @property
    def heuristic(self) -> bool:
        return any(e.status != "resolved" for e in self.path)


class DependencyGraph:
    def __init__(self, edges: list[Edge]) -> None:
        self.edges = edges
        self.dependents: dict[str, list[Edge]] = defaultdict(list)   # target -> edges into it
        self.dependencies: dict[str, list[Edge]] = defaultdict(list)  # source -> edges out of it
        for edge in edges:
            self.dependents[edge.target].append(edge)
            self.dependencies[edge.source].append(edge)

    def has_edge(self, a: str, b: str) -> bool:
        """True if a direct relationship exists between a and b in either direction."""
        return any(e.target == b for e in self.dependencies.get(a, [])) or any(
            e.target == a for e in self.dependencies.get(b, [])
        )

    def direct_dependents(self, symbol: str, kinds: frozenset[str] = TRAVERSAL_KINDS) -> list[Edge]:
        return [e for e in self.dependents.get(symbol, []) if e.kind in kinds]

    def reverse_reachable(
        self, starts: list[str], max_depth: int, max_nodes: int, kinds: frozenset[str] = TRAVERSAL_KINDS
    ) -> tuple[dict[str, Reach], bool]:
        """Everything that (transitively) depends on `starts`.

        Returns ({symbol: Reach}, truncated). Visited symbols are never revisited,
        so cycles cannot cause infinite loops.
        """
        reached: dict[str, Reach] = {s: Reach(0) for s in starts}
        queue: deque[str] = deque(starts)
        truncated = False
        while queue:
            node = queue.popleft()
            current = reached[node]
            if current.depth >= max_depth:
                if self.direct_dependents(node, kinds):
                    truncated = True
                continue
            for edge in self.direct_dependents(node, kinds):
                if edge.source in reached:
                    continue
                if len(reached) >= max_nodes:
                    return reached, True
                reached[edge.source] = Reach(current.depth + 1, current.path + [edge])
                queue.append(edge.source)
        return reached, truncated
