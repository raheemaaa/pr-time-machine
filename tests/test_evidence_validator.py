from pr_time_machine.ai.schemas import AIFinding
from pr_time_machine.evidence_validator import validate_finding
from pr_time_machine.pipeline import AnalysisInput, analyze


def make(affected, path, evidence=None, changed="shop.pricing.calculate_total"):
    return AIFinding(title="t", severity="high", changed_symbol=changed, affected_symbol=affected,
                     verdict="likely_affected", reasoning="r", impact_path=path, evidence=evidence or [])


def run(sample, settings, finding):
    old, new, diff = sample
    res = analyze(AnalysisInput(old, new, diff, "sample"), settings, None)
    return validate_finding(finding, res.report, res.new, res.old, res.graph, new, old)


def test_claim_backed_by_static_path_is_confirmed(sample, settings):
    finding = make("shop.checkout.place_order", ["shop.pricing.calculate_total", "shop.checkout.place_order"],
                   [{"file": "shop/checkout.py", "start_line": 7, "end_line": 7}])
    result = run(sample, settings, finding)
    assert result.dependency_status == "confirmed_dependency" and result.problems == []


def test_plausible_claim_without_dependency_path_is_unverified(sample, settings):
    finding = make("shop.pricing.subtotal", ["shop.pricing.calculate_total", "shop.api.checkout_endpoint"])
    result = run(sample, settings, finding)
    assert result.dependency_status == "unverified_relationship"
    assert any("No static dependency" in p for p in result.problems)


def test_invented_symbols_files_and_lines_are_flagged(sample, settings):
    finding = make("shop.payments.charge", [], [
        {"file": "shop/payments.py", "start_line": 1, "end_line": 2},
        {"file": "shop/checkout.py", "start_line": 5, "end_line": 400},
    ], changed="shop.pricing.nonexistent")
    result = run(sample, settings, finding)
    assert result.dependency_status == "invalid_reference"
    assert len(result.problems) == 4 and result.valid_evidence == []
