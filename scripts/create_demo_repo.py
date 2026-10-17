"""Create a local Git repository from sample_project/ with a pull-request branch.

Usage (from the project folder):
    python scripts/create_demo_repo.py            # creates ./demo_repo
    python scripts/create_demo_repo.py my_folder

Result: branch `main` (original code) and branch `pr/discount-fraction` (the sample change).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pr_time_machine.diff_parser import apply_diff, parse_unified_diff  # noqa: E402

IDENTITY = ["-c", "user.name=PR Time Machine Demo", "-c", "user.email=demo@example.invalid"]


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "demo_repo"
    if target.exists():
        print(f"{target} already exists. Delete it first or choose another folder.")
        sys.exit(1)
    shutil.copytree(ROOT / "sample_project", target, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    git(target, "init", "-q")
    git(target, "checkout", "-q", "-b", "main")
    git(target, "add", ".")
    git(target, *IDENTITY, "commit", "-q", "-m", "Shop with percentage discounts")

    diff_text = (ROOT / "sample_changes" / "discount_fraction.diff").read_text(encoding="utf-8")
    files = {p.relative_to(target).as_posix(): p.read_text(encoding="utf-8")
             for p in target.rglob("*.py") if ".git" not in p.parts}
    new_files, problems = apply_diff(files, parse_unified_diff(diff_text))
    if problems:
        print("Could not apply the sample diff:", *problems, sep="\n  ")
        sys.exit(1)
    git(target, "checkout", "-q", "-b", "pr/discount-fraction")
    for path, text in new_files.items():
        if files.get(path) != text:
            (target / path).write_text(text, encoding="utf-8", newline="\n")
    git(target, "add", ".")
    git(target, *IDENTITY, "commit", "-q", "-m", "Use fractional discounts to match the payments API")
    git(target, "checkout", "-q", "main")
    print(f"Demo repository ready: {target.resolve()}")
    print("In the app choose 'Local Git repository' with base = main and head = pr/discount-fraction.")


if __name__ == "__main__":
    main()
