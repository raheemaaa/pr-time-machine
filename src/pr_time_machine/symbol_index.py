"""A searchable index of the functions, classes, methods and variables in a repository."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Symbol:
    id: str            # e.g. "shop.pricing.calculate_total" or "shop.cart.Cart.add"
    name: str
    kind: str          # function | method | class | variable | module
    file: str
    module: str
    start_line: int
    end_line: int
    signature: str = ""
    parent: str | None = None
    decorators: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)
    is_test: bool = False
    status: str = "present"   # "removed" for symbols deleted by the change

    @property
    def location(self) -> str:
        return f"{self.file}:{self.start_line}"


class SymbolIndex:
    def __init__(self) -> None:
        self.symbols: dict[str, Symbol] = {}
        self._by_file: dict[str, list[Symbol]] = defaultdict(list)

    def add(self, symbol: Symbol) -> None:
        old = self.symbols.get(symbol.id)
        if old is not None:
            self._by_file[old.file].remove(old)
        self.symbols[symbol.id] = symbol
        self._by_file[symbol.file].append(symbol)

    def get(self, symbol_id: str) -> Symbol | None:
        return self.symbols.get(symbol_id)

    def __contains__(self, symbol_id: str) -> bool:
        return symbol_id in self.symbols

    def __len__(self) -> int:
        return len(self.symbols)

    def in_file(self, path: str) -> list[Symbol]:
        return list(self._by_file.get(path, []))

    def innermost_at(self, path: str, line: int) -> Symbol | None:
        """The smallest function/class/variable containing `line` (module pseudo-symbols excluded)."""
        best: Symbol | None = None
        for sym in self._by_file.get(path, []):
            if sym.kind == "module" or not (sym.start_line <= line <= sym.end_line):
                continue
            if best is None or (sym.end_line - sym.start_line) < (best.end_line - best.start_line):
                best = sym
        return best
