import io
import zipfile

import pytest

from pr_time_machine.repository_scanner import snapshot_from_zip
from pr_time_machine.security import UnsafeArchiveError


def make_zip(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buffer.getvalue()


@pytest.mark.parametrize("name", ["../evil.py", "/abs/evil.py", "a/../../evil.py", "C:/evil.py", "a\\..\\evil.py"])
def test_path_traversal_is_rejected(settings, name):
    with pytest.raises(UnsafeArchiveError):
        snapshot_from_zip(make_zip({name: "x = 1"}), settings)


def test_ignored_folders_skipped_and_github_root_stripped(settings):
    data = make_zip({
        "repo-main/app.py": "x = 1",
        "repo-main/.venv/lib/site.py": "y = 1",
        "repo-main/node_modules/pkg/z.py": "z = 1",
        "repo-main/README.md": "hi",
    })
    snap = snapshot_from_zip(data, settings)
    assert snap.files == {"app.py": "x = 1"}


def test_zip_bomb_ratio_and_invalid_zip(settings):
    with pytest.raises(UnsafeArchiveError):
        snapshot_from_zip(make_zip({"big.py": "a" * 400_000}), settings)
    with pytest.raises(UnsafeArchiveError):
        snapshot_from_zip(b"not a zip", settings)
