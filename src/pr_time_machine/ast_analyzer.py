"""Static analysis of Python source code with the built-in `ast` module.

Files are parsed, never imported or executed. The analyzer runs two passes:
1. collect every definition (functions, classes, methods, module variables);
2. walk each function body and record which project symbols it calls or uses.

Static analysis cannot see everything. Calls through getattr(), dictionaries of
functions, dependency injection, or objects whose type is only known at runtime
are recorded as *unresolved* instead of being guessed.
"""

from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from .symbol_index import Symbol, SymbolIndex

BUILTIN_NAMES = set(dir(builtins))
DYNAMIC_CALLS = {"getattr", "eval", "exec", "__import__", "globals", "locals"}


@dataclass
class Edge:
    source: str     # the symbol that depends on...
    target: str     # ...this symbol
    kind: str       # call | instantiation | reference | inheritance | decorator | import
    file: str
    line: int
    status: str     # "resolved", or "heuristic" when a module was matched by name suffix
    reason: str


@dataclass
class UnresolvedCall:
    caller: str
    expression: str
    file: str
    line: int
    reason: str


@dataclass
class RepoAnalysis:
    index: SymbolIndex
    edges: list[Edge] = field(default_factory=list)
    unresolved: list[UnresolvedCall] = field(default_factory=list)
    parse_errors: dict[str, str] = field(default_factory=dict)
    modules: dict[str, str] = field(default_factory=dict)   # module name -> file path


def module_name_for(path: str) -> str:
    parts = list(PurePosixPath(path).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else "__root__"


def module_symbol_id(module: str) -> str:
    return f"{module}.<module>"


def is_test_file(path: str) -> bool:
    p = PurePosixPath(path)
    return (
        p.name.startswith("test_") or p.name.endswith("_test.py") or p.name == "conftest.py"
        or "tests" in p.parts[:-1] or "test" in p.parts[:-1]
    )


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    sig = f"({ast.unparse(node.args)})"
    if node.returns is not None:
        sig += f" -> {ast.unparse(node.returns)}"
    return sig


def _dotted(node: ast.AST) -> str | None:
    """'a.b.c' for a Name/Attribute chain, otherwise None."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


# --------------------------------------------------------------------------- pass 1

class _DefinitionCollector(ast.NodeVisitor):
    def __init__(self, file: str, module: str, index: SymbolIndex) -> None:
        self.file, self.module, self.index = file, module, index
        self.is_test = is_test_file(file)
        self.stack: list[Symbol] = []

    def _add(self, node: ast.AST, name: str, kind: str, signature: str = "") -> Symbol:
        decorators = getattr(node, "decorator_list", [])
        prefix = self.stack[-1].id if self.stack else self.module
        sym = Symbol(
            id=f"{prefix}.{name}", name=name, kind=kind, file=self.file, module=self.module,
            start_line=min([node.lineno] + [d.lineno for d in decorators]),
            end_line=getattr(node, "end_lineno", None) or node.lineno,
            signature=signature, parent=self.stack[-1].id if self.stack else None,
            decorators=[ast.unparse(d) for d in decorators], is_test=self.is_test,
        )
        self.index.add(sym)
        return sym

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        kind = "method" if self.stack and self.stack[-1].kind == "class" else "function"
        sym = self._add(node, node.name, kind, _signature(node))
        self.stack.append(sym)
        for stmt in node.body:
            self.visit(stmt)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        sym = self._add(node, node.name, "class")
        sym.bases = [ast.unparse(b) for b in node.bases]
        self.stack.append(sym)
        for stmt in node.body:
            self.visit(stmt)
        self.stack.pop()

    def _module_variable(self, node: ast.Assign | ast.AnnAssign, targets: list[ast.expr]) -> None:
        if self.stack:
            return
        for target in targets:
            if isinstance(target, ast.Name):
                self._add(node, target.id, "variable")

    def visit_Assign(self, node: ast.Assign) -> None:
        self._module_variable(node, node.targets)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._module_variable(node, [node.target])


def collect_definitions(files: dict[str, str]) -> tuple[SymbolIndex, dict[str, ast.Module], dict[str, str]]:
    """Parse every file and index its definitions. Returns (index, trees, parse_errors)."""
    index = SymbolIndex()
    trees: dict[str, ast.Module] = {}
    errors: dict[str, str] = {}
    for path, source in sorted(files.items()):
        try:
            tree = ast.parse(source, filename=path)
        except (SyntaxError, ValueError) as exc:
            line = getattr(exc, "lineno", None)
            errors[path] = f"{type(exc).__name__}: {getattr(exc, 'msg', exc)}" + (f" (line {line})" if line else "")
            continue
        module = module_name_for(path)
        trees[path] = tree
        index.add(Symbol(
            id=module_symbol_id(module), name=module, kind="module", file=path, module=module,
            start_line=1, end_line=max(1, source.count("\n") + 1), is_test=is_test_file(path),
        ))
        _DefinitionCollector(path, module, index).visit(tree)
    return index, trees, errors


# --------------------------------------------------------------------------- pass 2

class _ReferenceCollector(ast.NodeVisitor):
    def __init__(self, file: str, module: str, analysis: RepoAnalysis, module_names: set[str],
                 callable_names: set[str]) -> None:
        self.file, self.module, self.analysis = file, module, analysis
        self.index = analysis.index
        self.module_names = module_names
        self.callable_names = callable_names
        self.is_package = PurePosixPath(file).name == "__init__.py"
        self.stack: list[str] = [module_symbol_id(module)]
        self.class_stack: list[str | None] = []
        self.imports: dict[str, tuple] = {}
        self.handled: set[int] = set()

    # ---------------------------------------------------------------- helpers
    def _prefix(self) -> str:
        return self.module if len(self.stack) == 1 else self.stack[-1]

    def _edge(self, target: str, kind: str, node: ast.AST, status: str, reason: str, source: str | None = None) -> None:
        source = source or self.stack[-1]
        if target != source:
            self.analysis.edges.append(Edge(source, target, kind, self.file, node.lineno, status, reason))

    def _unresolved(self, node: ast.AST, reason: str) -> None:
        expr = ast.unparse(node)
        self.analysis.unresolved.append(
            UnresolvedCall(self.stack[-1], expr[:120], self.file, node.lineno, reason)
        )

    def _resolve_module(self, name: str, level: int) -> tuple[str | None, str]:
        if level:
            parts = self.module.split(".") if self.is_package else self.module.split(".")[:-1]
            if level - 1 > len(parts):
                return None, ""
            parts = parts[: len(parts) - (level - 1)]
            full = ".".join(parts + ([name] if name else []))
            return (full, "resolved") if full in self.module_names else (None, "")
        if name in self.module_names:
            return name, "resolved"
        matches = [m for m in self.module_names if m.endswith("." + name)]
        return (matches[0], "heuristic") if len(matches) == 1 else (None, "")

    def _resolve_name(self, name: str) -> tuple[str, str, str] | None:
        for scope in reversed(self.stack[1:]):          # functions nested in the current function
            sym = self.index.get(scope)
            if sym and sym.kind in ("function", "method") and f"{scope}.{name}" in self.index:
                return f"{scope}.{name}", "resolved", "defined in the enclosing function"
        local = f"{self.module}.{name}"
        if local in self.index:
            return local, "resolved", "defined in the same module"
        imported = self.imports.get(name)
        if imported and imported[0] == "symbol":
            _, mod, sym_name, status = imported
            target = f"{mod}.{sym_name}"
            if target in self.index:
                return target, status, f"imported from {mod}"
        return None

    def _resolve_attribute(self, node: ast.Attribute) -> tuple[str, str, str] | None:
        dotted = _dotted(node)
        if dotted is None:
            return None
        head, _, rest = dotted.partition(".")
        if head in ("self", "cls"):
            cls = self.class_stack[-1] if self.class_stack else None
            if cls and f"{cls}.{rest}" in self.index:
                return f"{cls}.{rest}", "resolved", f"method called on {head}"
            return None
        parts = dotted.split(".")
        for i in range(len(parts) - 1, 0, -1):
            imported = self.imports.get(".".join(parts[:i]))
            if imported and imported[0] == "module":
                target = imported[1] + "." + ".".join(parts[i:])
                if target in self.index:
                    return target, imported[2], f"attribute of imported module {imported[1]}"
                return None
        base = self._resolve_name(head)
        if base and f"{base[0]}.{rest}" in self.index:
            return f"{base[0]}.{rest}", base[1], "attribute of a project class"
        return None

    def _resolve_target(self, node: ast.AST) -> tuple[str, str, str] | None:
        if isinstance(node, ast.Call):
            node = node.func
        if isinstance(node, ast.Name):
            return self._resolve_name(node.id)
        if isinstance(node, ast.Attribute):
            return self._resolve_attribute(node)
        return None

    # ---------------------------------------------------------------- imports
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            mod, status = self._resolve_module(alias.name, 0)
            if alias.asname:
                if mod:
                    self.imports[alias.asname] = ("module", mod, status)
                continue
            first = alias.name.split(".")[0]
            first_mod, first_status = self._resolve_module(first, 0)
            if first_mod:
                self.imports[first] = ("module", first_mod, first_status)
            if mod:
                self.imports[alias.name] = ("module", mod, status)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        base, status = self._resolve_module(node.module or "", node.level)
        if base is None:
            return  # third-party or standard library import
        for alias in node.names:
            if alias.name == "*":
                self._unresolved(node, "star import: imported names cannot be listed statically")
                continue
            local = alias.asname or alias.name
            submodule = f"{base}.{alias.name}"
            if submodule in self.module_names:
                self.imports[local] = ("module", submodule, status)
                continue
            self.imports[local] = ("symbol", base, alias.name, status)
            if submodule in self.index:
                self._edge(submodule, "import", node, status, f"imports {alias.name} from {base}")

    # ---------------------------------------------------------------- definitions
    def _visit_decorators(self, node: ast.AST, owner: str) -> None:
        for dec in getattr(node, "decorator_list", []):
            res = self._resolve_target(dec)
            if res:
                self._edge(res[0], "decorator", dec, res[1], f"decorated with {ast.unparse(dec)}", source=owner)
            if isinstance(dec, ast.Call):
                for arg in [*dec.args, *dec.keywords]:
                    self.visit(arg)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        sym_id = f"{self._prefix()}.{node.name}"
        self._visit_decorators(node, sym_id)
        for default in [*node.args.defaults, *[d for d in node.args.kw_defaults if d is not None]]:
            self.visit(default)
        self.stack.append(sym_id)
        self.class_stack.append(self.class_stack[-1] if self.class_stack else None)
        for stmt in node.body:
            self.visit(stmt)
        self.class_stack.pop()
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        cls_id = f"{self._prefix()}.{node.name}"
        self._visit_decorators(node, cls_id)
        for base in node.bases:
            res = self._resolve_target(base)
            if res:
                self._edge(res[0], "inheritance", base, res[1], f"inherits from {ast.unparse(base)}", source=cls_id)
        self.stack.append(cls_id)
        self.class_stack.append(cls_id)
        for stmt in node.body:
            self.visit(stmt)
        self.class_stack.pop()
        self.stack.pop()

    # ---------------------------------------------------------------- usages
    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        resolved = None
        if isinstance(func, ast.Name):
            self.handled.add(id(func))
            if func.id in DYNAMIC_CALLS:
                self._unresolved(node, f"dynamic lookup with {func.id}(); the target cannot be known statically")
            elif func.id not in BUILTIN_NAMES or f"{self.module}.{func.id}" in self.index:
                resolved = self._resolve_name(func.id)
        elif isinstance(func, ast.Attribute):
            resolved = self._resolve_attribute(func)
            if resolved:
                self.handled.add(id(func))
            elif func.attr in self.callable_names and _dotted(func) is not None:
                self._unresolved(node, f"method call on a runtime object; '{func.attr}' matches a project symbol name but the object's type is unknown")
        else:
            self._unresolved(node, "dynamic call target (the function is the result of another expression)")
        if resolved:
            target, status, reason = resolved
            kind = "instantiation" if self.index.get(target).kind == "class" else "call"
            self._edge(target, kind, node, status, reason)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if id(node) in self.handled or not isinstance(node.ctx, ast.Load) or node.id in ("self", "cls"):
            return
        res = self._resolve_name(node.id)
        if res and self.index.get(res[0]).kind != "module":
            self._edge(res[0], "reference", node, res[1], f"uses {node.id}")

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if id(node) in self.handled:
            return
        if isinstance(node.ctx, ast.Load):
            res = self._resolve_attribute(node)
            if res:
                self._edge(res[0], "reference", node, res[1], f"uses {ast.unparse(node)}")
                return
        self.generic_visit(node)


def analyze_repository(files: dict[str, str], extra_symbols: list[Symbol] | None = None) -> RepoAnalysis:
    """Build the symbol index and dependency edges for a snapshot.

    `extra_symbols` lets the caller register symbols that the change removed, so
    code that still calls them is linked to them instead of being silently missed.
    """
    index, trees, errors = collect_definitions(files)
    for sym in extra_symbols or []:
        if sym.id not in index:
            index.add(sym)
    analysis = RepoAnalysis(index=index, parse_errors=errors)
    analysis.modules = {module_name_for(p): p for p in trees}
    module_names = set(analysis.modules)
    callable_names = {s.name for s in index.symbols.values() if s.kind in ("function", "method")}
    for path, tree in trees.items():
        collector = _ReferenceCollector(path, module_name_for(path), analysis, module_names, callable_names)
        for stmt in tree.body:
            collector.visit(stmt)
    return analysis
