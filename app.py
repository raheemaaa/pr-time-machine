"""PR Time Machine: Streamlit interface.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import streamlit as st  # noqa: E402

from pr_time_machine.ai import create_provider  # noqa: E402
from pr_time_machine.config import load_settings  # noqa: E402
from pr_time_machine.diff_parser import DiffParseError, apply_diff, parse_unified_diff  # noqa: E402
from pr_time_machine.evidence_validator import DEPENDENCY_LABELS  # noqa: E402
from pr_time_machine.impact_analyzer import PRIORITY_LABELS  # noqa: E402
from pr_time_machine.pipeline import AnalysisInput, AnalysisResult, analyze  # noqa: E402
from pr_time_machine.report_generator import SCENARIO_LABELS, to_json, to_markdown  # noqa: E402
from pr_time_machine.repository_scanner import (  # noqa: E402
    GitError, git_diff, snapshot_from_directory, snapshot_from_git, snapshot_from_zip,
)
from pr_time_machine.security import UnsafeArchiveError  # noqa: E402

MAX_DIFF_BYTES = 2_000_000
COLORS = {
    "changed": "#6B2FBF", "high": "#B42318", "potential": "#B54708", "low": "#667085",
    "insufficient": "#98A2B3", "test": "#0E7490", "ink": "#172033",
}

st.set_page_config(page_title="PR Time Machine", page_icon="🕰️", layout="wide")
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&family=Public+Sans:wght@400;600&display=swap');
html, body, [data-testid="stMarkdownContainer"], .stTextInput, .stTextArea, .stButton button {
  font-family: 'Public Sans', 'Segoe UI', system-ui, sans-serif;
}
h1, h2, h3 { font-family: 'Bricolage Grotesque', 'Segoe UI', system-ui, sans-serif; letter-spacing: -0.01em; }
.wordmark { font-family: 'Bricolage Grotesque', 'Segoe UI', sans-serif; font-weight: 800; font-size: 2.6rem;
  line-height: 1.05; color: #172033; margin: 0.2rem 0 0.3rem 0; }
.wordmark .ripple { color: #6B2FBF; }
.lede { font-size: 1.08rem; max-width: 62ch; color: #344054; margin-bottom: 1.2rem; }
.chip { display: inline-block; padding: 0.12rem 0.55rem; border-radius: 999px; font-size: 0.82rem;
  font-weight: 600; margin: 0 0.35rem 0.35rem 0; border: 1.5px solid currentColor; }
.path { font-family: 'Source Code Pro', ui-monospace, monospace; font-size: 0.86rem; color: #344054; }
[data-testid="stExpander"] details { border-radius: 10px; transition: border-color .18s ease, box-shadow .18s ease; }
[data-testid="stExpander"] details:hover { border-color: #2A55C4; box-shadow: 0 4px 14px rgba(23, 32, 51, .07); }
[data-testid="stMetric"] { background: #FFFFFF; border: 1px solid #E4E7EC; border-radius: 12px; padding: .7rem .9rem; }
.stTabs [data-baseweb="tab"] { font-weight: 600; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>
""",
    unsafe_allow_html=True,
)


def chip(text: str, color: str) -> str:
    return f'<span class="chip" style="color:{color}">{text}</span>'


FRIENDLY_VERDICT = {
    "likely_affected": "🔴 Likely affected",
    "possibly_affected": "🟠 Possibly affected",
    "likely_unaffected": "🟢 Probably not affected",
    "insufficient_context": "⚪ Not enough information",
}
PRIORITY_ICON = {"high": "🔴", "potential": "🟠", "low": "⚪", "insufficient": "❔"}

# The hero illustration shows the built-in sample exactly as its real test run behaves:
# checkout and refunds break, invoices and reports stay correct, the API breaks through checkout.
HERO_HTML = """
<style>
.ptm-hero { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.15fr); gap: 2rem; align-items: center;
  margin: .4rem 0 1.4rem 0; }
@media (max-width: 900px) { .ptm-hero { grid-template-columns: 1fr; } }
.ptm-word { font-family: 'Bricolage Grotesque', 'Segoe UI', sans-serif; font-weight: 800; font-size: 2.7rem;
  line-height: 1.04; color: #172033; margin: 0 0 .6rem 0; }
.ptm-word span { color: #6B2FBF; }
.ptm-lede { font-family: 'Public Sans', 'Segoe UI', sans-serif; font-size: 1.06rem; line-height: 1.6;
  color: #344054; max-width: 56ch; margin: 0; }
.ptm-fig { margin: 0; background: #FFFFFF; border: 1px solid #E4E7EC; border-radius: 16px; padding: .8rem .8rem .4rem; }
.ptm-fig svg { width: 100%; height: auto; display: block; font-family: 'Public Sans', 'Segoe UI', sans-serif; }
.ptm-fig figcaption { font-family: 'Public Sans', 'Segoe UI', sans-serif; font-size: .82rem; color: #667085;
  padding: .3rem .4rem .2rem; }
.ptm-edge { fill: none; stroke: #98A2B3; stroke-width: 2; stroke-dasharray: 220; stroke-dashoffset: 220;
  animation: ptm-draw .7s ease-out both; }
.ptm-node rect { fill: #FFFFFF; stroke: #98A2B3; stroke-width: 1.6; transition: stroke-width .15s ease; }
.ptm-node:hover rect { stroke-width: 3; }
.ptm-node { cursor: help; }
.ptm-node text { font-size: 13px; fill: #172033; font-weight: 600; }
.ptm-status { font-size: 11px; opacity: 0; animation: ptm-fade .4s ease-out both; }
.ptm-changed rect { fill: #6B2FBF; stroke: #6B2FBF; }
.ptm-changed text { fill: #FFFFFF; }
.ptm-pulse { fill: none; stroke: #6B2FBF; stroke-width: 2; opacity: 0; transform-box: fill-box; transform-origin: center;
  animation: ptm-pulse 1.1s ease-out .1s both; }
.ptm-breaks rect { animation: ptm-red .45s ease-out both; }
.ptm-safe rect { animation: ptm-green .45s ease-out both; }
.ptm-via rect { animation: ptm-amber .45s ease-out both; }
.d1 { animation-delay: .5s; } .d2 { animation-delay: .7s; } .d3 { animation-delay: .9s; } .d4 { animation-delay: 1.1s; }
.d5 { animation-delay: 1.5s; } .s1 { animation-delay: 1.9s; } .s2 { animation-delay: 2.3s; }
@keyframes ptm-draw { to { stroke-dashoffset: 0; } }
@keyframes ptm-fade { to { opacity: 1; } }
@keyframes ptm-pulse { 0% { opacity: .7; transform: scale(1); } 100% { opacity: 0; transform: scale(1.35); } }
@keyframes ptm-red { to { fill: #FEF3F2; stroke: #B42318; } }
@keyframes ptm-green { to { fill: #ECFDF3; stroke: #067647; } }
@keyframes ptm-amber { to { fill: #FFFAEB; stroke: #B54708; } }
@media (prefers-reduced-motion: reduce) {
  .ptm-fig * { animation-duration: .001s !important; animation-delay: 0s !important; }
}
</style>
<div class="ptm-hero">
  <div>
    <div class="ptm-word">PR Time <span>Machine</span></div>
    <p class="ptm-lede">A pull request changes one function, but other code depends on it. PR Time Machine finds
    every place that uses the changed code, asks Gemma 4 which of them actually rely on what changed, and backs each
    answer with the exact file and line.</p>
  </div>
  <figure class="ptm-fig">
    <svg viewBox="0 0 640 275" role="img" aria-labelledby="ptm-title">
      <title id="ptm-title">A change to calculate_total spreads to five places; two break, two stay correct, one breaks indirectly</title>
      <path class="ptm-edge d1" d="M170 132 C 210 132, 210 36, 250 36"/>
      <path class="ptm-edge d2" d="M170 132 C 210 132, 210 101, 250 101"/>
      <path class="ptm-edge d3" d="M170 132 C 210 132, 210 166, 250 166"/>
      <path class="ptm-edge d4" d="M170 132 C 210 132, 210 231, 250 231"/>
      <path class="ptm-edge d5" d="M400 36 L 480 36"/>
      <g class="ptm-node ptm-changed"><title>shop/pricing.py: the discount changed from a percent (10) to a fraction (0.1), and the parameter was renamed</title>
        <rect x="20" y="113" width="150" height="38" rx="10"/><text x="95" y="137" text-anchor="middle">calculate_total()</text></g>
      <rect class="ptm-pulse" x="20" y="113" width="150" height="38" rx="10"/>
      <text x="95" y="172" text-anchor="middle" font-size="11" fill="#6B2FBF">the change</text>
      <g class="ptm-node ptm-breaks s1"><title>shop/checkout.py line 7 passes discount_percent=..., a parameter that no longer exists</title>
        <rect x="250" y="19" width="150" height="34" rx="9"/><text x="325" y="41" text-anchor="middle">place_order()</text></g>
      <text class="ptm-status s1" x="325" y="68" text-anchor="middle" fill="#B42318">breaks: old parameter name</text>
      <g class="ptm-node ptm-breaks s1"><title>shop/refunds.py passes 10, which now means 1000% instead of 10%</title>
        <rect x="250" y="84" width="150" height="34" rx="9"/><text x="325" y="106" text-anchor="middle">refund_amount()</text></g>
      <text class="ptm-status s1" x="325" y="133" text-anchor="middle" fill="#B42318">breaks: 10 now means 1000%</text>
      <g class="ptm-node ptm-safe s1"><title>shop/invoices.py never passes a discount, so its result is unchanged</title>
        <rect x="250" y="149" width="150" height="34" rx="9"/><text x="325" y="171" text-anchor="middle">build_invoice()</text></g>
      <text class="ptm-status s1" x="325" y="198" text-anchor="middle" fill="#067647">safe: no discount used</text>
      <g class="ptm-node ptm-safe s1"><title>shop/reports.py never passes a discount, so its result is unchanged</title>
        <rect x="250" y="214" width="150" height="34" rx="9"/><text x="325" y="236" text-anchor="middle">daily_revenue()</text></g>
      <text class="ptm-status s1" x="325" y="263" text-anchor="middle" fill="#067647">safe: no discount used</text>
      <g class="ptm-node ptm-via s2"><title>shop/api.py calls place_order(), so it fails when checkout fails</title>
        <rect x="480" y="19" width="150" height="34" rx="9"/><text x="555" y="41" text-anchor="middle">checkout_endpoint()</text></g>
      <text class="ptm-status s2" x="555" y="68" text-anchor="middle" fill="#B54708">breaks through checkout</text>
    </svg>
    <figcaption>The built-in sample, as its real test run confirms. Hover over a box to see why.</figcaption>
  </figure>
</div>
"""

STEPS_HTML = """
<style>
.ptm-steps { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .9rem; margin: .2rem 0 1.6rem 0; }
@media (max-width: 1000px) { .ptm-steps { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 560px) { .ptm-steps { grid-template-columns: 1fr; } }
.ptm-step { background: #FFFFFF; border: 1px solid #E4E7EC; border-radius: 14px; padding: 1rem 1.05rem;
  font-family: 'Public Sans', 'Segoe UI', sans-serif; transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease; }
.ptm-step:hover { transform: translateY(-3px); border-color: #2A55C4; box-shadow: 0 8px 22px rgba(23, 32, 51, .08); }
.ptm-step .n { display: inline-flex; width: 1.7rem; height: 1.7rem; border-radius: 50%; background: #F4EBFF;
  color: #6B2FBF; font-weight: 800; align-items: center; justify-content: center; font-size: .9rem; }
.ptm-step h4 { font-family: 'Bricolage Grotesque', 'Segoe UI', sans-serif; font-size: 1.12rem; margin: .55rem 0 .3rem 0;
  color: #172033; }
.ptm-step p { margin: 0; font-size: .92rem; line-height: 1.5; color: #475467; }
.ptm-step .who { margin-top: .55rem; font-size: .8rem; color: #667085; }
@media (prefers-reduced-motion: reduce) { .ptm-step { transition: none; } .ptm-step:hover { transform: none; } }
</style>
<div class="ptm-steps">
  <div class="ptm-step"><span class="n">1</span><h4>Map the connections</h4>
    <p>Python's built-in parser reads your code and lists every function that uses the changed code, directly or through others.</p>
    <div class="who">Done by code, so these links are facts.</div></div>
  <div class="ptm-step"><span class="n">2</span><h4>Judge each one</h4>
    <p>Gemma 4 reads each call site next to the before-and-after code and decides whether it relies on what changed.</p>
    <div class="who">Done by Gemma 4. Treated as a hypothesis.</div></div>
  <div class="ptm-step"><span class="n">3</span><h4>Check the evidence</h4>
    <p>Every file, line, and function Gemma mentions is checked against your real code. Anything unproven is labelled.</p>
    <div class="who">Done by code. Catches made-up claims.</div></div>
  <div class="ptm-step"><span class="n">4</span><h4>Prove it with tests</h4>
    <p>Optionally run your tests before and after the change and see which predictions turned out right.</p>
    <div class="who">Local Git repositories only. You choose.</div></div>
</div>
"""


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def plain_summary(result: AnalysisResult) -> tuple[str, list[str]]:
    """A short, plain-language explanation of the result and what to review first."""
    r = result.report
    if not r.changed_symbols:
        return ("This change does not modify any function, class, or module variable, so there is nothing to trace. "
                "Any module-level changes are listed below."), []
    names = ", ".join(f"`{c.id.rsplit('.', 1)[-1]}`" for c in r.changed_symbols[:3])
    if len(r.changed_symbols) > 3:
        names += f" and {len(r.changed_symbols) - 3} more"
    count = len(r.impacted)
    text = f"This change modifies {names}. "
    if count == 0:
        return text + "No other code uses it, so the risk stays inside the changed code itself.", []
    text += f"**{_plural(count, 'other place', 'other places')}** in the code depend on it. "
    static = [f for f in result.findings if f.source == "static"]
    used_model = not result.is_mock and not result.ai_error and any(f.ai for f in static)
    if used_model:
        likely = [f.affected_symbol for f in static if f.ai and f.ai.verdict == "likely_affected"]
        maybe = [f.affected_symbol for f in static if f.ai and f.ai.verdict == "possibly_affected"]
        safe = [f for f in static if f.ai and f.ai.verdict == "likely_unaffected"]
        text += (f"After reading the code, Gemma 4 judged **{len(likely)} likely affected**, "
                 f"**{len(maybe)} possibly affected**, and **{len(safe)} probably not affected**.")
        review = likely + maybe
    else:
        high = [f.affected_symbol for f in static if f.priority == "high"]
        text += ("AI reasoning was not used, so every connected place is listed. "
                 f"**{len(high)}** are high priority because they directly use code whose signature changed or was removed.")
        review = high or [f.affected_symbol for f in static[:3]]
    if result.execution:
        failing = len(result.execution.newly_failing)
        text += f"\n\n**Test run:** {_plural(failing, 'test', 'tests')} started failing after the change. See the Test plan tab for how the predictions compare."
    return text, review


@st.cache_resource
def provider_and_warning():
    settings = load_settings()
    provider, warning = create_provider(settings)
    return settings, provider, warning


# --------------------------------------------------------------------------- inputs

def sample_input(settings) -> AnalysisInput:
    old = snapshot_from_directory(ROOT / "sample_project", settings, "built-in sample project")
    diff = (ROOT / "sample_changes" / "discount_fraction.diff").read_text(encoding="utf-8")
    new, problems = apply_diff(old.files, parse_unified_diff(diff))
    return AnalysisInput(old.files, new, diff, "Built-in sample: discount changes from percent to fraction",
                         warnings=old.warnings + problems)


def zip_input(zip_bytes: bytes, diff_text: str, settings) -> AnalysisInput:
    snapshot = snapshot_from_zip(zip_bytes, settings)
    diffs = parse_unified_diff(diff_text)
    new, problems = apply_diff(snapshot.files, diffs)
    python_diffs = [d for d in diffs if d.is_python]
    if python_diffs and len(problems) >= len(python_diffs):
        raise DiffParseError("The diff could not be applied to the uploaded code:\n- " + "\n- ".join(problems))
    return AnalysisInput(snapshot.files, new, diff_text, "Uploaded ZIP with pasted diff",
                         warnings=snapshot.warnings + problems)


def git_input(path: str, base: str, head: str, run_tests: bool, settings) -> AnalysisInput:
    repo = Path(path.strip().strip('"')).expanduser()
    if not repo.is_dir():
        raise GitError(f"Folder not found: {repo}")
    old = snapshot_from_git(repo, base.strip(), settings)
    new = snapshot_from_git(repo, head.strip(), settings)
    diff = git_diff(repo, base.strip(), head.strip())
    if not diff.strip():
        raise GitError(f"There are no differences between {base} and {head}.")
    return AnalysisInput(old.files, new.files, diff, f"{repo.name}: {old.label} → {new.label}", repo,
                         base.strip(), head.strip(), run_tests, warnings=old.warnings + new.warnings)


def run_analysis(make_input, settings, provider) -> None:
    try:
        with st.status("Analyzing the change…", expanded=True) as status:
            st.write("Reading the repository and parsing the diff")
            inp = make_input()
            st.write("Mapping dependencies with the Python AST")
            if provider is not None:
                st.write(f"Asking {provider.name} to assess each dependent")
            if inp.run_tests:
                st.write("Running the test suite at both revisions")
            result = analyze(inp, settings, provider)
            status.update(label="Analysis complete", state="complete", expanded=False)
        st.session_state["result"] = result
        st.success("Done. Open the Overview, Dependency map, Findings and Test plan tabs.")
    except (DiffParseError, UnsafeArchiveError, GitError) as exc:
        st.error(str(exc))
    except Exception as exc:  # keep the app usable and explain what happened
        st.error(f"Unexpected error ({type(exc).__name__}): {exc}")


# --------------------------------------------------------------------------- tabs

def render_start(settings, provider) -> None:
    st.html(HERO_HTML)
    st.subheader("How it works")
    st.html(STEPS_HTML)
    st.subheader("Try it")
    method = st.radio(
        "Choose what to analyze",
        ["Built-in sample", "Upload ZIP and diff", "Local Git repository"],
        captions=[
            "The fastest way to see results. No setup needed.",
            "Your code as a ZIP, plus the change as a diff.",
            "Compare two branches on your computer, and optionally run the tests.",
        ],
        horizontal=True,
    )
    if method == "Built-in sample":
        st.write("A small shop where `calculate_total()` switches from percentage discounts (10) to fractions (0.1). "
                 "It has five dependents and five tests.")
        st.caption("To also run the tests and check predictions, create the demo Git repo with "
                   "`python scripts/create_demo_repo.py` and use the Local Git repository option.")
        if st.button("Analyze sample change", type="primary"):
            run_analysis(lambda: sample_input(settings), settings, provider)
    elif method == "Upload ZIP and diff":
        zip_file = st.file_uploader("Repository ZIP (the code before the change)", type=["zip"])
        diff_file = st.file_uploader("Diff file (optional, or paste below)", type=["diff", "patch", "txt"])
        diff_text = st.text_area("Unified diff, e.g. the output of `git diff`", height=200,
                                 placeholder="diff --git a/app/pricing.py b/app/pricing.py\n--- a/app/pricing.py\n+++ b/app/pricing.py\n@@ ...")
        st.caption("Uploaded code is only parsed. It is never imported, installed, or executed.")
        if st.button("Analyze ZIP and diff", type="primary"):
            if zip_file is None:
                st.error("Upload a ZIP of the repository first.")
                return
            text = diff_file.getvalue().decode("utf-8", errors="replace") if diff_file else diff_text
            if not text.strip():
                st.error("Add a diff: upload a .diff file or paste one into the box.")
                return
            if len(text.encode("utf-8")) > MAX_DIFF_BYTES:
                st.error("The diff is larger than 2 MB. Analyze a smaller change.")
                return
            run_analysis(lambda: zip_input(zip_file.getvalue(), text, settings), settings, provider)
    else:
        path = st.text_input("Repository folder", placeholder=r"C:\Users\you\projects\demo_repo")
        col1, col2 = st.columns(2)
        base = col1.text_input("Base revision (before)", value="main")
        head = col2.text_input("Proposed revision (after)", value="pr/discount-fraction")
        run_tests = st.checkbox("Also run the test suite at both revisions to check the predictions")
        if run_tests:
            st.warning("This runs the repository's own code on your computer. Only enable it for repositories "
                       "you trust, such as your own. Tests run in a temporary Git worktree with secrets removed "
                       "from the environment, but this is not a sandbox.")
        if st.button("Analyze revisions", type="primary"):
            if not path.strip():
                st.error("Enter the path to a local Git repository.")
                return
            run_analysis(lambda: git_input(path, base, head, run_tests, settings), settings, provider)

    with st.expander("What this tool can and cannot establish"):
        st.markdown(
            "- **Can:** prove that code is statically connected to the change, with file and line evidence.\n"
            "- **Can:** ask Gemma 4 to judge whether each connection depends on what changed, and check its citations.\n"
            "- **Can (opt-in, local repos):** run the tests at both revisions and report which ones started failing.\n"
            "- **Cannot:** see calls made through `getattr()`, plugin registries, dependency injection, or other languages.\n"
            "- **Cannot:** turn a model's explanation into a fact. Model findings stay hypotheses until a test confirms them."
        )


def render_overview(result: AnalysisResult) -> None:
    r = result.report
    high = sum(f.priority == "high" for f in result.findings)
    summary, review = plain_summary(result)
    with st.container(border=True):
        st.markdown("#### The short version")
        st.markdown(summary)
        if review:
            st.markdown("**Review these first:** " + ", ".join(f"`{name}`" for name in review))
        st.caption("Next: open **Findings** to see why each one is listed, or **Test plan** to see what to test.")
    cols = st.columns(5)
    cols[0].metric("Python files changed", len(r.changed_files), help="Python files touched by the diff.")
    cols[1].metric("Symbols changed", len(r.changed_symbols),
                   help="Functions, classes, methods, or module variables whose lines changed.")
    cols[2].metric("Dependents found", len(r.impacted),
                   help="Code that calls or uses a changed symbol, directly or through other functions. "
                        "Found by parsing the code, so each link is a fact, not a guess.")
    cols[3].metric("Related tests", len(result.existing_tests),
                   help="Existing tests whose calls reach the changed code.")
    cols[4].metric("High-priority findings", high,
                   help="Code that directly uses something whose signature changed or that was removed. "
                        "Look at these first. This is not a probability of a bug.")
    if result.is_mock:
        st.warning("Mock mode: no AI model was called. Findings show static analysis only.")
    if result.ai_error:
        st.error(f"Gemma reasoning failed, so only static results are shown. {result.ai_error}")
    if result.ai_summary and not result.is_mock:
        st.subheader("What the change does")
        st.write(result.ai_summary)
    st.subheader("Changed symbols")
    if r.changed_symbols:
        st.dataframe([{
            "Symbol": c.id, "Change": c.change_type, "File": c.file,
            "Signature before": c.signature_before or "", "Signature after": c.signature_after or "",
        } for c in r.changed_symbols], hide_index=True)
    else:
        st.info("No function, class, or module variable was changed. See module-level changes below.")
    if r.module_level_changes:
        st.markdown("**Module-level changes** (outside any function, so no symbol is claimed)")
        for m in r.module_level_changes:
            st.write(f"{m.file}, lines {m.lines[0]}–{m.lines[-1]}: {m.description} ({m.side} version)")
    if r.other_changed_files:
        st.caption("Non-Python files in the diff (not analyzed): " + ", ".join(r.other_changed_files))
    for warning in result.warnings:
        st.warning(warning)
    st.caption(f"Input: {result.label}. Timings (s): " + ", ".join(f"{k} {v}" for k, v in result.durations.items()))


def build_dot(result: AnalysisResult) -> str:
    def esc(text: str) -> str:
        return text.replace('"', "'")

    lines = ['digraph G {', 'rankdir=LR; bgcolor="transparent"; nodesep=0.35; ranksep=0.9;',
             'node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11, penwidth=1.6];',
             'edge [fontname="Helvetica", fontsize=9, color="#667085"];']
    for c in result.report.changed_symbols:
        lines.append(f'"{esc(c.id)}" [label="{esc(c.id)}\\nchanged ({c.change_type})", fillcolor="{COLORS["changed"]}", '
                     f'fontcolor="white", color="{COLORS["changed"]}"];')
    seen_edges: set[tuple[str, str]] = set()
    for item in result.report.impacted + result.report.related_tests:
        color = COLORS["test"] if item.is_test else COLORS[item.priority]
        label = f"{item.id}\\n{item.file}:{item.start_line}"
        lines.append(f'"{esc(item.id)}" [label="{esc(label)}", fillcolor="white", color="{color}", fontcolor="{COLORS["ink"]}"'
                     + (', shape=note' if item.is_test else '') + '];')
        for edge in item.path:
            key = (edge.target, edge.source)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            style = ', style=dashed' if edge.status != "resolved" else ''
            lines.append(f'"{esc(edge.target)}" -> "{esc(edge.source)}" [label="{edge.kind} L{edge.line}"{style}];')
    for f in result.findings:
        if f.source == "ai_only":
            lines.append(f'"{esc(f.affected_symbol)}" [label="{esc(f.affected_symbol)}\\nmodel claim, unverified", '
                         f'style="rounded,dashed", fillcolor="white", color="{COLORS["insufficient"]}"];')
            lines.append(f'"{esc(f.changed_symbol)}" -> "{esc(f.affected_symbol)}" [style=dashed, color="{COLORS["insufficient"]}", label="unverified"];')
    lines.append("}")
    return "\n".join(lines)


def render_map(result: AnalysisResult) -> None:
    r = result.report
    if not r.changed_symbols:
        st.info("No changed symbols, so there is nothing to map.")
        return
    legend = "".join([
        chip("Changed", COLORS["changed"]), chip("High-priority review", COLORS["high"]),
        chip("Potential impact", COLORS["potential"]), chip("Low priority", COLORS["low"]),
        chip("Existing test", COLORS["test"]), chip("Model claim, not verified", COLORS["insufficient"]),
    ])
    st.markdown(legend, unsafe_allow_html=True)
    st.caption("Arrows show how a change can travel: from the changed code to everything that uses it. "
               "Solid lines are exact static links; dashed lines were matched heuristically or claimed by the model.")
    try:
        st.graphviz_chart(build_dot(result), width="stretch")
    except Exception as exc:
        st.warning(f"The graph could not be drawn ({type(exc).__name__}); see the text version below.")
    with st.expander("Text version of every path", expanded=not r.impacted):
        if not r.impacted and not r.related_tests:
            st.write("Static analysis found no code that depends on the changed symbols.")
        for item in r.impacted + r.related_tests:
            chain = " ← ".join(item.path_ids)
            site = item.call_site
            where = f" (first link: {site.file}:{site.line})" if site else ""
            st.markdown(f'<div class="path">{chain}{where}</div>', unsafe_allow_html=True)
    if r.unresolved_notes:
        with st.expander(f"Calls static analysis could not resolve ({len(r.unresolved_notes)})"):
            for u in r.unresolved_notes:
                st.write(f"{u.file}:{u.line} `{u.expression}`: {u.reason}")


def render_findings(result: AnalysisResult) -> None:
    if not result.findings:
        st.info("No findings: static analysis found no code that depends on the change.")
        return
    use_verdicts = not result.is_mock and not result.ai_error
    st.markdown("**At a glance**")
    st.dataframe([{
        "Code that uses the change": f.affected_symbol,
        "Review priority": f"{PRIORITY_ICON[f.priority]} {PRIORITY_LABELS[f.priority]}",
        "Gemma 4's judgement": FRIENDLY_VERDICT[f.ai.verdict] if (f.ai and use_verdicts) else "Not analyzed",
        "Existing tests on this path": len(f.tests),
        "Status": SCENARIO_LABELS[f.scenario_status],
    } for f in result.findings], hide_index=True)
    st.caption("Review priority comes from how the code connects. Gemma 4's judgement comes from reading the code. "
               "Only a test run turns a judgement into a fact.")
    st.markdown("**Details**")
    col1, col2 = st.columns(2)
    priorities = col1.multiselect("Review priority", list(PRIORITY_LABELS)[1:], default=list(PRIORITY_LABELS)[1:],
                                  format_func=PRIORITY_LABELS.get)
    statuses = col2.multiselect("Verification status", list(SCENARIO_LABELS), default=list(SCENARIO_LABELS),
                                format_func=SCENARIO_LABELS.get)
    shown = [f for f in result.findings if f.priority in priorities and f.scenario_status in statuses]
    st.caption(f"Showing {len(shown)} of {len(result.findings)} findings. Click one to see the reasoning and evidence.")
    for f in shown:
        verdict = f": {FRIENDLY_VERDICT[f.ai.verdict]}" if (f.ai and use_verdicts) else ""
        with st.expander(f"{PRIORITY_ICON[f.priority]} {f.id}. {f.affected_symbol} ({PRIORITY_LABELS[f.priority]}){verdict}"):
            chips = chip(DEPENDENCY_LABELS[f.dependency_status],
                         COLORS["changed"] if f.dependency_status == "confirmed_dependency" else COLORS["insufficient"])
            scenario_color = COLORS["high"] if f.scenario_status == "tested_failure" else COLORS["low"]
            chips += chip(SCENARIO_LABELS[f.scenario_status], scenario_color)
            st.markdown(chips, unsafe_allow_html=True)
            if f.path:
                st.markdown(f'<div class="path">{" ← ".join(f.path)}</div>', unsafe_allow_html=True)
            if f.call_site:
                st.write(f"Call site: `{f.call_site}`")
            st.write("**Why it is ranked here:** " + " ".join(f.priority_reasons))
            if f.ai and not result.is_mock:
                st.write(f"**Gemma's reasoning ({f.ai.severity} severity):** {f.ai.reasoning}")
                if f.ai.failure_scenario:
                    st.write(f"**Failure scenario (hypothesis):** {f.ai.failure_scenario}")
                for n, ev in enumerate(f.ai.evidence):
                    ok = f.validation and n in f.validation.valid_evidence
                    st.write(f"{'✅' if ok else '⚠️'} Evidence {ev.file}:{ev.start_line}-{ev.end_line} {ev.description}")
                for limit in f.ai.limitations:
                    st.caption(f"Model limitation: {limit}")
            if f.validation and f.validation.problems:
                st.warning("Evidence check: " + " ".join(f.validation.problems))
            if f.tests:
                st.write("**Existing tests on this path:** " + ", ".join(f"`{t}`" for t in f.tests))
            recs = [r.text for r in result.recommendations if r.finding_id == f.id]
            if recs:
                st.write("**Recommended tests:**")
                for text in recs:
                    st.markdown(f"- {text}")


def render_tests(result: AnalysisResult) -> None:
    st.subheader("Existing tests that reach the change")
    if result.existing_tests:
        st.dataframe([{
            "Test": t.id, "Location": f"{t.file}:{t.line}",
            "Exercises": ", ".join(t.exercises) or ("the changed code directly" if t.tests_changed_code_directly else ""),
        } for t in result.existing_tests], hide_index=True)
    else:
        st.info(f"None of the {result.all_tests_found} tests found in the repository reach the changed code.")
    st.subheader("Recommended tests")
    if result.recommendations:
        for rec in result.recommendations:
            st.markdown(f"- **{rec.finding_id}** ({'Gemma 4' if rec.source == 'gemma' else 'rule-based'}): {rec.text}")
    else:
        st.write("No recommendations, because nothing depends on the change.")
    st.subheader("Test execution")
    ex = result.execution
    if ex is None:
        st.caption("Not run. Test execution is off by default and only available for local Git repositories.")
        return
    col1, col2, col3 = st.columns(3)
    col1.metric(f"Passed at {ex.base.revision}", len(ex.base.passed), help=f"{len(ex.base.failed)} failed")
    col2.metric(f"Passed at {ex.head.revision}", len(ex.head.passed), help=f"{len(ex.head.failed)} failed")
    col3.metric("Newly failing", len(ex.newly_failing))
    for err in ex.base.errors + ex.head.errors:
        st.error(err)
    if ex.newly_failing:
        st.write("Newly failing: " + ", ".join(f"`{t}`" for t in sorted(ex.newly_failing)))
    if result.comparison:
        c = result.comparison
        st.markdown("**Prediction check**")
        st.caption(f"Basis: {c.basis}.")
        st.dataframe([
            {"Measure": "Tests predicted as relevant", "Value": str(len(c.predicted))},
            {"Measure": "Tests that newly failed", "Value": str(len(c.actual))},
            {"Measure": "Overlap", "Value": str(len(c.true_positives))},
            {"Measure": "Precision", "Value": "n/a" if c.precision is None else f"{c.precision:.0%}"},
            {"Measure": "Recall", "Value": "n/a" if c.recall is None else f"{c.recall:.0%}"},
        ], hide_index=True)
    with st.expander("pytest output (last lines)"):
        st.code(ex.head.output_tail or "(no output)", language="text")


def render_export(result: AnalysisResult) -> None:
    st.write("Download the full analysis. Reports never include API keys or environment variables.")
    col1, col2 = st.columns(2)
    col1.download_button("Download Markdown report", to_markdown(result), "pr-time-machine-report.md", "text/markdown")
    col2.download_button("Download JSON report", to_json(result), "pr-time-machine-report.json", "application/json")
    with st.expander("Preview Markdown"):
        st.markdown(to_markdown(result))


# --------------------------------------------------------------------------- layout

def main() -> None:
    base_settings, provider, warning = provider_and_warning()
    with st.sidebar:
        st.header("AI reasoning")
        if provider.is_mock:
            st.warning(f"**Mock mode.** {warning}")
        else:
            st.success(f"Connected: {provider.name}")
        use_ai = st.toggle("Use AI reasoning", value=True, help="Off = static analysis only.")
        st.header("Analysis limits")
        depth = st.slider("Caller hops to follow", 1, 8, base_settings.max_depth)
        budget = st.select_slider("Code sent to the model (characters)", [10_000, 20_000, 30_000, 60_000],
                                  value=base_settings.context_budget_chars
                                  if base_settings.context_budget_chars in (10_000, 20_000, 30_000, 60_000) else 30_000)
        st.caption("Settings come from your .env file. The API key is never displayed or exported.")
        with st.expander("How to read the results"):
            st.markdown(
                "- **Dependent**: code that calls or uses the changed code. Proven by parsing.\n"
                "- **Review priority**: where to look first, based on how the code connects. Not a bug probability.\n"
                "- **Gemma 4's judgement**: whether that code relies on what changed, after reading it. A hypothesis.\n"
                "- **Confirmed dependency**: the link exists in the code.\n"
                "- **Tested failure**: a real test on this path started failing.\n"
                "- **Not verified**: nobody has proven it yet."
            )
    settings = replace(base_settings, max_depth=depth, context_budget_chars=budget)
    active_provider = provider if use_ai else None

    tabs = st.tabs(["Start", "Overview", "Dependency map", "Findings", "Test plan", "Export"])
    with tabs[0]:
        render_start(settings, active_provider)
    result: AnalysisResult | None = st.session_state.get("result")
    renderers = [render_overview, render_map, render_findings, render_tests, render_export]
    for tab, render in zip(tabs[1:], renderers):
        with tab:
            if result is None:
                st.info("Run an analysis from the Start tab to see results here.")
            else:
                render(result)


if __name__ == "__main__":
    main()