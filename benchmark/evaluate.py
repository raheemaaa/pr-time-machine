"""Reproducible benchmark for PR Time Machine.

Run from the project folder:
    python benchmark/evaluate.py              # static analysis only (no API key needed)
    python benchmark/evaluate.py --with-ai    # also asks Gemma 4 (needs GEMINI_API_KEY)

Metrics (per scenario and summed over all scenarios):
    recall    = correctly flagged affected components / all known affected components
    precision = correctly flagged affected components / all components flagged
    false positives = flagged components listed as not affected in the ground truth
A ratio with a zero denominator is reported as "n/a" instead of being guessed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pr_time_machine.ai import create_provider  # noqa: E402
from pr_time_machine.ai.schemas import AIFinding  # noqa: E402
from pr_time_machine.config import load_settings  # noqa: E402
from pr_time_machine.diff_parser import make_unified_diff  # noqa: E402
from pr_time_machine.evidence_validator import validate_finding  # noqa: E402
from pr_time_machine.pipeline import PREDICTED_VERDICTS, AnalysisInput, analyze  # noqa: E402
from pr_time_machine.repository_scanner import snapshot_from_directory  # noqa: E402

SCENARIOS = Path(__file__).resolve().parent / "scenarios"


def ratio(n: int, d: int) -> float | None:
    return None if d == 0 else n / d


def fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def score(flagged: set[str], expected: dict) -> dict:
    affected, not_affected = set(expected["affected"]), set(expected["not_affected"])
    hits = flagged & affected
    return {"flagged": sorted(flagged), "hits": len(hits), "flagged_count": len(flagged), "expected_count": len(affected),
            "false_positives": sorted(flagged & not_affected),
            "precision": ratio(len(hits), len(flagged)), "recall": ratio(len(hits), len(affected))}


def run(with_ai: bool) -> dict:
    settings = load_settings()
    provider = None
    if with_ai:
        provider, warning = create_provider(settings)
        if provider.is_mock:
            sys.exit(f"--with-ai needs a working Gemma 4 configuration: {warning}")
    rows = []
    for scenario in sorted(p for p in SCENARIOS.iterdir() if p.is_dir()):
        expected = json.loads((scenario / "expected.json").read_text(encoding="utf-8"))
        old = snapshot_from_directory(scenario / "base", settings).files
        new = snapshot_from_directory(scenario / "head", settings).files
        result = analyze(AnalysisInput(old, new, make_unified_diff(old, new), scenario.name), settings, provider)
        changed = {c.id for c in result.report.changed_symbols}
        static_flagged = {f.affected_symbol for f in result.findings if f.source == "static"}
        row = {
            "scenario": scenario.name,
            "changed_symbols_correct": changed == set(expected["changed"]),
            "static": score(static_flagged, expected),
            "tests_found": sorted(t.id for t in result.existing_tests),
            "unresolved_notes": len(result.report.unresolved_notes),
        }
        wanted_tests = set(expected.get("tests", []))
        row["tests_recall"] = ratio(len(wanted_tests & set(row["tests_found"])), len(wanted_tests))
        row["unwanted_tests"] = sorted(set(expected.get("not_tests", [])) & set(row["tests_found"]))
        if expected.get("expect_unresolved_note"):
            row["limitation_reported"] = row["unresolved_notes"] > 0
        if "fake_model_claim" in expected:
            claim = AIFinding.model_validate(expected["fake_model_claim"])
            check = validate_finding(claim, result.report, result.new, result.old, result.graph, new, old)
            row["fake_claim_status"] = check.dependency_status
            row["fake_claim_check_passed"] = check.dependency_status == expected["expected_claim_status"]
        if provider is not None:
            if result.ai_error:
                row["ai_error"] = result.ai_error
            gemma_flagged = {f.affected_symbol for f in result.findings
                             if f.ai and f.ai.verdict in PREDICTED_VERDICTS}
            combined = {f.affected_symbol for f in result.findings if f.source == "static"
                        and (f.ai is None or f.ai.verdict in PREDICTED_VERDICTS)}
            row["gemma"] = score(gemma_flagged, expected)
            row["combined"] = score(combined, expected)
            row["unverified_ai_claims"] = sum(f.source == "ai_only" for f in result.findings)
        rows.append(row)

    def total(mode: str) -> dict:
        hits = sum(r[mode]["hits"] for r in rows if mode in r)
        flagged = sum(r[mode]["flagged_count"] for r in rows if mode in r)
        expected = sum(r[mode]["expected_count"] for r in rows if mode in r)
        fps = sum(len(r[mode]["false_positives"]) for r in rows if mode in r)
        return {"precision": ratio(hits, flagged), "recall": ratio(hits, expected), "false_positives": fps}

    modes = ["static"] + (["gemma", "combined"] if provider else [])
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": provider.name if provider else None, "scenarios": rows,
            "totals": {m: total(m) for m in modes}}


def to_markdown(results: dict) -> str:
    lines = [f"# Benchmark results ({results['generated_at']})", "",
             f"Model: {results['model'] or 'none (static analysis only)'}", "",
             "| Scenario | Changed symbols correct | Static precision | Static recall | Static false positives | Notes |",
             "|---|---|---|---|---|---|"]
    for r in results["scenarios"]:
        notes = []
        if "limitation_reported" in r:
            notes.append("dynamic call reported as limitation" if r["limitation_reported"] else "limitation NOT reported")
        if "fake_claim_status" in r:
            notes.append(f"fake model claim labelled {r['fake_claim_status']}")
        if r["tests_recall"] is not None:
            notes.append(f"test recall {fmt(r['tests_recall'])}")
        if "gemma" in r:
            notes.append(f"Gemma P/R {fmt(r['gemma']['precision'])}/{fmt(r['gemma']['recall'])}")
        s = r["static"]
        lines.append(f"| {r['scenario']} | {'yes' if r['changed_symbols_correct'] else 'NO'} | {fmt(s['precision'])} | "
                     f"{fmt(s['recall'])} | {', '.join(s['false_positives']) or '-'} | {'; '.join(notes) or '-'} |")
    lines += ["", "| Mode | Precision | Recall | False positives |", "|---|---|---|---|"]
    for mode, t in results["totals"].items():
        lines.append(f"| {mode} | {fmt(t['precision'])} | {fmt(t['recall'])} | {t['false_positives']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--with-ai", action="store_true", help="also evaluate Gemma 4 (requires GEMINI_API_KEY)")
    args = parser.parse_args()
    results = run(args.with_ai)
    out_dir = Path(__file__).resolve().parent / "results"
    out_dir.mkdir(exist_ok=True)
    suffix = "with_ai" if args.with_ai else "static"
    (out_dir / f"results_{suffix}.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    markdown = to_markdown(results)
    (out_dir / f"RESULTS_{suffix}.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"Saved to {out_dir}")


if __name__ == "__main__":
    main()
