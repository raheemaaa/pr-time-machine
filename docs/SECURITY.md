# Threat model

| Threat | Mitigation | Residual risk |
|---|---|---|
| Malicious ZIP (path traversal, absolute paths, symlinks) | Archives are read in memory; any unsafe entry rejects the whole upload | None known for reading |
| Zip bombs / huge repos | Compression-ratio check, per-file, total-size and file-count limits | Limits are configurable; very low limits may skip real files |
| Code execution from analyzed repositories | Uploaded code is only parsed with `ast`; it is never imported or run | `ast.parse` on hostile input is CPU-bounded by the size limits |
| Prompt injection in comments/docstrings | Code is wrapped as `<untrusted_repository_content>`; system instruction forbids following it; all citations are validated; model output never triggers actions | A model may still be misled into a wrong verdict; that is why verdicts stay hypotheses |
| Hallucinated files, lines, symbols, or dependencies | `evidence_validator.py` checks each against the scanned repository and graph | Reasoning text itself is not machine-checkable |
| API key leakage | Key only read from `.env`/environment; never shown in the UI, prompts, logs, or reports; `.env` is git-ignored | Users can still paste keys into code they analyze; do not analyze secrets on the free tier |
| Test execution (opt-in) | Local Git repos only, explicit checkbox with warning, temporary worktree, secret-like env vars removed, timeout | **Not a sandbox.** The repository's tests run with your user permissions. Only enable for trusted code |
| Private code sent to a hosted model | Users choose what to analyze; mock and static-only modes never send code | On the Gemini API free tier, Google may use inputs to improve products. Use a paid tier or a local provider for private code |
