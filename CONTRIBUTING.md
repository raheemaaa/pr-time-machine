# Contributing to PR Time Machine

Thanks for helping. Small, focused pull requests are easiest to review.

## Set up

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest
```

Tests and the static benchmark run without an API key.

## Ground rules

- Keep the deterministic analyzer independent of the AI layer. `src/pr_time_machine/ai/` may import from the analyzer, never the other way round.
- Never present a model claim as a fact. New output must keep the labels: confirmed dependency, potential impact, hypothesis, tested failure, not verified.
- Add or update a test for every behaviour change. If you change impact detection, add a benchmark scenario in `benchmark/scenarios/` with `base/`, `head/` and `expected.json`, then run `python benchmark/evaluate.py`.
- Do not commit `.env`, API keys, or private code.

## Good first contributions

- Resolve more call patterns statically (for example, simple type annotations on parameters).
- New benchmark scenarios, especially tricky ones the analyzer currently gets wrong.
- A local inference provider (for example Gemma 4 through Ollama) implementing `AIProvider`.
