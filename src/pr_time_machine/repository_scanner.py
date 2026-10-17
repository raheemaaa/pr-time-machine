"""Build in-memory snapshots ({path: source}) of Python repositories.

A snapshot can come from a folder on disk, an uploaded ZIP, or a Git revision.
Files are read as text only; analyzed code is never imported or executed.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .config import Settings
from .security import read_python_files_from_zip

IGNORED_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "__pycache__", "node_modules",
    "site-packages", "build", "dist", ".tox", ".nox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".eggs", ".idea", ".vscode",
}


class GitError(RuntimeError):
    """Raised when a Git command fails, with a message safe to show users."""


@dataclass
class RepositorySnapshot:
    files: dict[str, str]
    label: str
    warnings: list[str] = field(default_factory=list)


def is_ignored(path: str) -> bool:
    parts = PurePosixPath(path).parts[:-1]
    return any(p in IGNORED_DIRS or p.endswith(".egg-info") for p in parts)


def strip_common_root(files: dict[str, str]) -> dict[str, str]:
    """GitHub ZIP downloads wrap everything in one folder (repo-main/). Remove it."""
    if not files:
        return files
    firsts = {PurePosixPath(p).parts[0] for p in files}
    if len(firsts) == 1 and all(len(PurePosixPath(p).parts) > 1 for p in files):
        return {str(PurePosixPath(*PurePosixPath(p).parts[1:])): src for p, src in files.items()}
    return files


def snapshot_from_directory(root: Path, settings: Settings, label: str | None = None) -> RepositorySnapshot:
    files: dict[str, str] = {}
    warnings: list[str] = []
    total = 0
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if is_ignored(rel):
            continue
        size = path.stat().st_size
        if size > settings.max_file_bytes:
            warnings.append(f"Skipped {rel}: larger than {settings.max_file_bytes:,} bytes.")
            continue
        total += size
        if len(files) >= settings.max_files or total > settings.max_total_bytes:
            warnings.append("Stopped reading files: repository size limit reached.")
            break
        files[rel] = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    return RepositorySnapshot(files, label or str(root), warnings)


def snapshot_from_zip(data: bytes, settings: Settings) -> RepositorySnapshot:
    files, warnings = read_python_files_from_zip(
        data,
        max_files=settings.max_files,
        max_file_bytes=settings.max_file_bytes,
        max_total_bytes=settings.max_total_bytes,
        is_ignored=is_ignored,
    )
    if not files:
        warnings.append("No Python files were found in the archive.")
    return RepositorySnapshot(strip_common_root(files), "uploaded ZIP", warnings)


def run_git(repo: Path, args: list[str], timeout: int = 60) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace",
        )
    except FileNotFoundError as exc:
        raise GitError("Git is not installed or not on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"Git command timed out: git {' '.join(args[:2])}") from exc
    if proc.returncode != 0:
        raise GitError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def verify_revision(repo: Path, revision: str) -> str:
    if not revision or revision.startswith("-"):
        raise GitError("Enter a branch name, tag, or commit hash.")
    try:
        return run_git(repo, ["rev-parse", "--verify", "--quiet", f"{revision}^{{commit}}"]).strip()
    except GitError as exc:
        raise GitError(f"Revision '{revision}' was not found in this repository.") from exc


def snapshot_from_git(repo: Path, revision: str, settings: Settings) -> RepositorySnapshot:
    if not (repo / ".git").exists() and not repo.joinpath("HEAD").exists():
        raise GitError(f"{repo} is not a Git repository (no .git folder found).")
    commit = verify_revision(repo, revision)
    listing = run_git(repo, ["ls-tree", "-r", "-z", "--name-only", commit])
    paths = [p for p in listing.split("\0") if p.endswith(".py") and not is_ignored(p)]
    files: dict[str, str] = {}
    warnings: list[str] = []
    total = 0
    for path in paths[: settings.max_files]:
        text = run_git(repo, ["show", f"{commit}:{path}"])
        if len(text) > settings.max_file_bytes:
            warnings.append(f"Skipped {path}: larger than {settings.max_file_bytes:,} bytes.")
            continue
        total += len(text)
        if total > settings.max_total_bytes:
            warnings.append("Stopped reading files: repository size limit reached.")
            break
        files[path] = text.replace("\r\n", "\n")
    if len(paths) > settings.max_files:
        warnings.append(f"Only the first {settings.max_files} Python files were analyzed.")
    return RepositorySnapshot(files, f"{revision} ({commit[:8]})", warnings)


def git_diff(repo: Path, base: str, head: str) -> str:
    base_commit = verify_revision(repo, base)
    head_commit = verify_revision(repo, head)
    return run_git(repo, ["diff", "--no-color", "--find-renames", base_commit, head_commit])
