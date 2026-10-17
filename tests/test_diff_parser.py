import pytest

from pr_time_machine.diff_parser import DiffParseError, apply_diff, make_unified_diff, parse_unified_diff

OLD = {"pkg/a.py": "def f(x):\n    return x\n\n\ndef g():\n    return 1\n"}
NEW = {"pkg/a.py": "def f(x, y=0):\n    return x + y\n\n\ndef g():\n    return 1\n", "pkg/b.py": "VALUE = 3\n"}


def test_round_trip_generated_diff():
    diff = make_unified_diff(OLD, NEW)
    files = parse_unified_diff(diff)
    assert {f.path: f.status for f in files} == {"pkg/a.py": "modified", "pkg/b.py": "added"}
    applied, problems = apply_diff(OLD, files)
    assert problems == [] and applied == NEW


def test_line_numbers_for_changes():
    fd = parse_unified_diff(make_unified_diff(OLD, NEW))[0]
    assert fd.deleted_old_lines() == {1, 2}
    assert fd.added_new_lines() == {1, 2}


def test_git_headers_rename_delete_and_no_newline_marker():
    diff = (
        "diff --git a/old.py b/new.py\nsimilarity index 90%\nrename from old.py\nrename to new.py\n"
        "--- a/old.py\n+++ b/new.py\n@@ -1 +1 @@\n-x = 1\n\\ No newline at end of file\n+x = 2\n"
        "diff --git a/gone.py b/gone.py\ndeleted file mode 100644\n--- a/gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-y = 1\n"
    )
    files = parse_unified_diff(diff)
    assert [(f.old_path, f.new_path, f.status) for f in files] == [
        ("old.py", "new.py", "renamed"), ("gone.py", None, "deleted")]
    applied, problems = apply_diff({"old.py": "x = 1", "gone.py": "y = 1\n"}, files)
    assert problems == [] and applied == {"new.py": "x = 2\n"}


def test_mismatched_diff_is_reported_not_applied():
    files = parse_unified_diff(make_unified_diff(OLD, NEW))
    applied, problems = apply_diff({"pkg/a.py": "def other():\n    pass\n"}, files)
    assert any("does not match" in p for p in problems)
    assert applied["pkg/a.py"] == "def other():\n    pass\n"


@pytest.mark.parametrize("text", ["", "   ", "hello world"])
def test_empty_or_non_diff_input_raises(text):
    with pytest.raises(DiffParseError):
        parse_unified_diff(text)
