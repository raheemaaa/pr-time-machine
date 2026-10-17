# Benchmark

Ten synthetic scenarios, each with `base/` (before), `head/` (after) and `expected.json` (ground truth):

| # | Scenario | What it tests |
|---|---|---|
| 01 | parameter_change | Renamed keyword: one caller breaks, one does not |
| 02 | return_value_change | float → str: arithmetic caller breaks, f-string caller does not |
| 03 | boundary_condition | `>= 18` → `> 18` |
| 04 | shared_utility | One formatter, three dependents (three import styles) |
| 05 | unrelated_change | Nothing should be flagged |
| 06 | dependency_cycle | Mutual recursion; traversal must terminate |
| 07 | deleted_function | Removed function still called |
| 08 | dynamic_call | `getattr()` dispatch (known blind spot) |
| 09 | existing_test_covers_change | Relevant test discovered, unrelated test not |
| 10 | unsupported_model_claim | A plausible model claim without a dependency path must be labelled unverified |

```powershell
python benchmark/evaluate.py            # static analysis only
python benchmark/evaluate.py --with-ai  # adds Gemma 4 and combined scores (needs GEMINI_API_KEY)
```

Results are written to `benchmark/results/`. `RESULTS_static.md` in this repository comes from an actual run; no AI results are included until you run `--with-ai` yourself.

Metrics: recall = correctly flagged affected components / known affected components; precision = correctly flagged / all flagged; ratios with a zero denominator are shown as `n/a`.
