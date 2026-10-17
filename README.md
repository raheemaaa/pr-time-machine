# PR Time Machine

**See what a pull request could affect before you merge it.**

A developer changes one small function. It looks harmless, but five other parts of the codebase use it, and two of them now break. Diff viewers show what changed; AI reviewers comment on whether the change looks right. PR Time Machine asks a different question: *what else depends on this, does it rely on what changed, and what is the evidence?*

## How it works

1. **Map dependencies (deterministic).** Python's `ast` module parses both versions of the code. The tool finds the changed functions (including signature changes and deletions) and walks the call graph backwards to every function, class, and test that depends on them, with file and line evidence for each link.
2. **Reason about consequences (Gemma 4).** Gemma 4 receives the before/after code and only the dependents the graph selected. For each one, it judges whether that code actually relies on what changed (argument names, return types, boundary conditions) and explains the failure chain.
3. **Check the claims.** Every file, line, symbol, and path Gemma cites is checked against the real repository. Claims without a static dependency path are labelled *not verified*.
4. **Prove it (optional).** For local Git repositories, the tool can run the test suite at both revisions and compare its predictions with the tests that actually started failing.

Being connected is never treated as proof of breakage. Every finding carries one of: confirmed dependency, potential impact, hypothesis, tested failure, or not verified.

## Why Gemma 4 is essential

Static analysis finds *who is connected*, but it can't tell which connections matter. In the sample project, all four direct callers of `calculate_total()` are equally "connected". Only two of them break: one passes a keyword that no longer exists, and one passes `10` meaning 10%, which now means 1000%. Deciding that requires reading and understanding the code at each call site, which is what Gemma 4 does here. Gemma 4 is open-weight (Apache 2.0), so the same reasoning layer can later run locally for private code.

## Features

- Three inputs: built-in sample, ZIP upload plus diff, or two revisions of a local Git repo
- Changed-symbol detection, including signature changes, removals, and module-level/import changes
- Interactive dependency map with a text fallback
- Findings with priority, evidence, Gemma's reasoning, and validation results, filterable by status
- Change-specific test recommendations (rule-based and from Gemma)
- Optional test execution with a prediction check (precision/recall against newly failing tests)
- Markdown and JSON export
- Clearly labelled mock mode that works without an API key
- 41 unit tests and a 10-scenario reproducible benchmark

## Setup (Windows PowerShell)

Requires Python 3.10–3.12 and Git.

```powershell
cd pr-time-machine
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

If activation is blocked, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` and try again.

### Configure Gemma 4

1. Create a key at https://aistudio.google.com/apikey.
2. In `.env`, set `GEMINI_API_KEY=` to your key. Keep `PRTM_AI_PROVIDER=gemma`.
3. Choose `PRTM_GEMMA_MODEL=gemma-4-26b-a4b-it` (faster) or `gemma-4-31b-it` (larger). These are the Gemma 4 ids listed in the official [Gemma on Gemini API docs](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api).

Without a key, the app runs in mock mode and says so in the sidebar. Check your free-tier limits at https://aistudio.google.com/rate-limit. On the free tier, Google may use inputs to improve its products, so don't analyze private code there.

Inference is hosted (Gemini API). A local provider (for example Gemma 4 through Ollama) can be added by implementing `AIProvider` in `src/pr_time_machine/ai/`.

## Run

```powershell
streamlit run app.py
```

Open the URL Streamlit prints (usually http://localhost:8501).

## Demo walkthrough

1. **Start → Built-in sample → Analyze sample change.** One changed symbol (`shop.pricing.calculate_total`, signature changed), five dependents, five related tests.
2. **Dependency map.** The change on the left fans out to checkout, refunds, invoices, and reports, then to the API handler.
3. **Findings.** Static analysis ranks all four direct callers as high priority. With Gemma 4 on, each finding shows a verdict. The expected story is: checkout and refunds are likely affected, while invoices and reports are likely unaffected because they never pass a discount.
4. **Prove it.** Run `python scripts/create_demo_repo.py`, then choose **Local Git repository** with folder `demo_repo`, base `main`, head `pr/discount-fraction`, and tick *run the test suite*. The **Test plan** tab shows 3 newly failing tests and the prediction check. Static-only precision is 60% and recall is 100%; compare that with Gemma's run.
5. **Export** the Markdown report.

## Tests and benchmark

```powershell
python -m pytest                          # 41 tests, no API key needed
python benchmark/evaluate.py              # static benchmark
python benchmark/evaluate.py --with-ai    # adds Gemma 4 scores (uses ~10 API requests)
```

Static benchmark from an actual run (`benchmark/results/RESULTS_static.md`): precision 0.85, recall 0.92, 2 false positives over 10 scenarios. Both false positives are callers that are connected but don't use what changed, which is the gap Gemma's reasoning targets. The `getattr()` scenario is a known blind spot and is reported as a limitation.

## Project structure

```
app.py                     Streamlit interface
src/pr_time_machine/       analysis engine (see docs/ARCHITECTURE.md)
  ai/                      Gemma 4 provider, mock provider, prompts, schemas
tests/                     unit and integration tests
benchmark/                 scenarios, evaluate.py, results
sample_project/            demo shop + tests;  sample_changes/ its PR diff
scripts/create_demo_repo.py  builds a local Git repo with a PR branch
docs/                      architecture, threat model, limitations
```

## Limitations

Python only. Calls made through `getattr()`, registries, or objects of unknown type are not resolved (they're listed instead). Priorities are structural, not probabilities. Model explanations are hypotheses until a test confirms them. Test execution is not sandboxed. See `docs/LIMITATIONS.md`.

## License

MIT. See `LICENSE`. Gemma 4 itself is released by Google under Apache 2.0.
