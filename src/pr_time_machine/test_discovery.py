"""Find existing test functions in a repository (by pytest naming conventions)."""

from __future__ import annotations

from .symbol_index import Symbol, SymbolIndex


def discover_tests(index: SymbolIndex) -> list[Symbol]:
    """Test functions and test methods, e.g. tests/test_cart.py::test_add or TestCart.test_add."""
    found = [
        s for s in index.symbols.values()
        if s.is_test and s.kind in ("function", "method") and s.name.startswith("test")
        and s.status == "present"
    ]
    return sorted(found, key=lambda s: (s.file, s.start_line))
