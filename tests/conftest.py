from pathlib import Path

import pytest

from pr_time_machine.config import Settings
from pr_time_machine.diff_parser import apply_diff, parse_unified_diff
from pr_time_machine.repository_scanner import snapshot_from_directory

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def settings():
    return Settings(ai_provider="mock")


@pytest.fixture
def sample(settings):
    """(old_files, new_files, diff_text) for the bundled sample change."""
    old = snapshot_from_directory(ROOT / "sample_project", settings).files
    diff = (ROOT / "sample_changes" / "discount_fraction.diff").read_text(encoding="utf-8")
    new, problems = apply_diff(old, parse_unified_diff(diff))
    assert problems == []
    return old, new, diff
