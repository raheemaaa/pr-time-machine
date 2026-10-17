# Architecture

PR Time Machine answers one question: **what else could this change affect, why, and what evidence should we check before merging?**

```
 diff + code (before)          deterministic layer (no AI)                     AI layer (Gemma 4)
 ───────────────────   ┌──────────────────────────────────────────┐   ┌──────────────────────────────┐
 sample / ZIP / Git ──▶│ repository_scanner → diff_parser          │   │ prompts: context selection   │
                       │ ast_analyzer (symbols, imports, calls)    │──▶│ gemma_provider / mock        │
                       │ dependency_graph (reverse BFS)            │   │ schemas: Pydantic validation │
                       │ impact_analyzer (changed symbols, ranks)  │   └──────────────┬───────────────┘
                       └──────────────────────────────────────────┘                  │
                                         │                                            ▼
                                         └────────────▶ evidence_validator ◀── model findings
                                                              │
                                   test_recommender, test_runner (opt-in), report_generator
                                                              │
                                                     Streamlit app / benchmark
```

## Modules

| Module | Responsibility |
|---|---|
| `config.py` | Settings from `.env`; list of supported Gemma 4 model ids |
| `security.py` | Safe in-memory ZIP reading (traversal, symlink, zip-bomb, size checks) |
| `repository_scanner.py` | Snapshots `{path: source}` from a folder, ZIP, or Git revision; ignore rules |
| `diff_parser.py` | Parse, apply, and generate unified diffs; map changes to line numbers |
| `symbol_index.py` | `Symbol` records and line → innermost symbol lookup |
| `ast_analyzer.py` | Two-pass AST analysis: definitions, then calls/references/inheritance/decorators |
| `dependency_graph.py` | Directed graph; cycle-safe reverse breadth-first search with depth and node limits |
| `impact_analyzer.py` | Changed-symbol detection (incl. signature changes and removals), priority rules |
| `test_discovery.py`, `test_recommender.py` | Find pytest tests; write change-specific test suggestions |
| `ai/` | Provider interface, Gemma 4 provider, mock provider, prompts, output schema |
| `evidence_validator.py` | Checks model claims against files, line ranges, symbols, and graph edges |
| `test_runner.py` | Optional pytest run at two revisions in temporary Git worktrees |
| `pipeline.py` | Orchestrates everything; merges static results with validated model output |
| `report_generator.py` | Markdown and JSON export |

Changes from the original plan: `pipeline.py` (orchestration) and `test_runner.py` (opt-in execution) were added. Test fixtures live in `sample_project/` and `benchmark/scenarios/` instead of `tests/fixtures/`.

## How symbols are linked

Each symbol has a stable id: `package.module.function` or `package.module.Class.method`. Module-level code belongs to `package.module.<module>`. The analyzer resolves:

- `from x import f` / `from .x import f as g` → calls to `f`/`g`
- `import x` / `import a.b as m` → `x.f()`, `m.f()`, `a.b.f()`
- `self.method()` / `cls.method()` inside a class
- Class instantiation, base classes, decorators, and references to module variables or functions passed as values

Module names are matched exactly first. If an import only matches by suffix (for example a `src/` layout), the edge is marked **heuristic** and drawn dashed. Anything else (getattr, registries, untyped objects) is listed as an **unresolved call**, never guessed.

Code that calls a symbol the change *removed* is still linked: removed symbols are registered before the second pass.

## Priority rules (structural, not probabilities)

| Label | Rule |
|---|---|
| Directly changed | Symbol contains an added or removed line |
| High-priority review | Depth 1 and the changed symbol's signature changed or it was removed |
| Potential downstream impact | Depth 1 (other changes), or depth 2 with a signature change/removal, or any depth when the changed symbol has ≥ 5 direct dependents |
| Low-priority potential impact | Everything else that is reachable |
| Insufficient evidence | Suggested by the model, but static analysis found no dependency path |

## Verification statuses

- **Dependency:** confirmed (a static path exists) / not verified (model-only) / invalid reference (cites something that does not exist).
- **Scenario:** not analyzed / hypothesis (model's explanation) / tested failure (a test on this path newly failed) / existing tests passed (not proof of safety) / not verified.

## Gemma 4 integration

`GemmaProvider` calls `client.models.generate_content(model=..., contents=prompt, config=GenerateContentConfig(system_instruction=...))` with the `google-genai` SDK, as documented at https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api. The prompt contains:

1. Static facts as JSON: changed symbols with old/new signatures, every candidate dependent with its path, related tests, and known static-analysis limits.
2. Numbered source snippets selected by the graph within the character budget: before/after versions of changed symbols, then dependents by depth, then tests. Omitted symbols are listed so the model knows what it did not see.

Gemma must return one JSON object per candidate. The reply is validated with Pydantic; a malformed reply is retried once with the validation error. Every finding is then checked by `evidence_validator.py`. If the model fails, the deterministic results are still shown.

Hosted vs local: this version uses hosted inference (Gemini API). Gemma 4 weights are open, so a local provider (for example through Ollama) can implement `AIProvider` without touching the analyzer; it is not implemented yet.
