from pr_time_machine.ai.mock_provider import MockProvider
from pr_time_machine.diff_parser import make_unified_diff
from pr_time_machine.pipeline import AnalysisInput, analyze


def test_sample_change_signature_and_dependents(sample, settings):
    old, new, diff = sample
    result = analyze(AnalysisInput(old, new, diff, "sample"), settings, None)
    [changed] = result.report.changed_symbols
    assert changed.id == "shop.pricing.calculate_total" and changed.signature_changed
    priorities = {i.id: i.priority for i in result.report.impacted}
    assert priorities == {
        "shop.checkout.place_order": "high", "shop.refunds.refund_amount": "high",
        "shop.invoices.build_invoice": "high", "shop.reports.daily_revenue": "high",
        "shop.api.checkout_endpoint": "potential",
    }
    assert len(result.existing_tests) == 5
    assert all(f.static_recommendation for f in result.findings)


def test_removed_function_still_called_is_high_priority(settings):
    old = {"lib.py": "def old_total(x):\n    return x\n\ndef keep():\n    return 1\n",
           "report.py": "from lib import old_total\n\ndef build():\n    return old_total(3)\n"}
    new = {"lib.py": "def keep():\n    return 1\n", "report.py": old["report.py"]}
    result = analyze(AnalysisInput(old, new, make_unified_diff(old, new), "t"), settings, None)
    assert [(c.id, c.change_type) for c in result.report.changed_symbols] == [("lib.old_total", "removed")]
    assert [(i.id, i.priority) for i in result.report.impacted] == [("report.build", "high")]


def test_unrelated_change_has_no_dependents(settings):
    old = {"a.py": "def used():\n    return 1\n", "b.py": "from a import used\n\ndef x():\n    return used()\n",
           "notes.py": "def lonely():\n    return 'a'\n"}
    new = dict(old, **{"notes.py": "def lonely():\n    return 'b'\n"})
    result = analyze(AnalysisInput(old, new, make_unified_diff(old, new), "t"), settings, None)
    assert [c.id for c in result.report.changed_symbols] == ["notes.lonely"]
    assert result.report.impacted == []


def test_module_level_import_change_is_reported_without_inventing_a_symbol(settings):
    old = {"m.py": "import os\n\ndef f():\n    return 1\n"}
    new = {"m.py": "import sys\n\ndef f():\n    return 1\n"}
    result = analyze(AnalysisInput(old, new, make_unified_diff(old, new), "t"), settings, None)
    assert result.report.changed_symbols == []
    assert {m.description for m in result.report.module_level_changes} == {"import change"}


def test_mock_mode_is_labelled_and_never_claims_reasoning(sample, settings):
    old, new, diff = sample
    result = analyze(AnalysisInput(old, new, diff, "sample"), settings, MockProvider())
    assert result.is_mock and result.ai_summary.startswith("[MOCK]")
    assert {f.ai.verdict for f in result.findings} == {"insufficient_context"}
