# Benchmark results (2026-10-17T10:39:22+00:00)

Model: none (static analysis only)

| Scenario | Changed symbols correct | Static precision | Static recall | Static false positives | Notes |
|---|---|---|---|---|---|
| 01_parameter_change | yes | 0.50 | 1.00 | invoice.make_invoice | - |
| 02_return_value_change | yes | 0.50 | 1.00 | log.log_price | - |
| 03_boundary_condition | yes | 1.00 | 1.00 | - | - |
| 04_shared_utility | yes | 1.00 | 1.00 | - | - |
| 05_unrelated_change | yes | n/a | n/a | - | - |
| 06_dependency_cycle | yes | 1.00 | 1.00 | - | - |
| 07_deleted_function | yes | 1.00 | 1.00 | - | - |
| 08_dynamic_call | yes | n/a | 0.00 | - | dynamic call reported as limitation |
| 09_existing_test_covers_change | yes | 1.00 | 1.00 | - | test recall 1.00 |
| 10_unsupported_model_claim | yes | 1.00 | 1.00 | - | fake model claim labelled unverified_relationship |

| Mode | Precision | Recall | False positives |
|---|---|---|---|
| static | 0.85 | 0.92 | 2 |
