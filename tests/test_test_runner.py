import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pr_time_machine.pipeline import AnalysisInput, analyze
from pr_time_machine.repository_scanner import git_diff, snapshot_from_git

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def test_test_execution_finds_exactly_the_newly_failing_tests(tmp_path, settings):
    repo = tmp_path / "demo"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "create_demo_repo.py"), str(repo)], check=True,
                   capture_output=True)
    base, head = "main", "pr/discount-fraction"
    inp = AnalysisInput(snapshot_from_git(repo, base, settings).files, snapshot_from_git(repo, head, settings).files,
                        git_diff(repo, base, head), "demo", repo, base, head, run_tests=True)
    res = analyze(inp, settings, None)
    assert res.execution.newly_failing == {
        "tests.test_checkout.test_place_order_with_coupon",
        "tests.test_checkout.test_checkout_endpoint_returns_created",
        "tests.test_refunds.test_refund_keeps_restocking_fee",
    }
    assert res.comparison.recall == 1.0 and res.comparison.precision == pytest.approx(0.6)
