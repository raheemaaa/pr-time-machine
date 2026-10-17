"""Optional: run a local repository's pytest suite at two revisions and compare results.

SECURITY: this runs the repository's own code on your machine. It is off by default,
never available for uploaded ZIPs, and should only be enabled for repositories you
trust (for example your own). It is NOT a sandbox. Mitigations: each revision runs in a
temporary `git worktree` (your working copy is untouched), secrets are removed from the
environment, and a timeout stops runaway tests.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .repository_scanner import GitError, run_git, verify_revision

SENSITIVE_ENV = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH", re.IGNORECASE)


@dataclass
class TestRunResult:
    revision: str
    ran: bool
    passed: set[str] = field(default_factory=set)
    failed: set[str] = field(default_factory=set)
    skipped: set[str] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    output_tail: str = ""


@dataclass
class TestExecution:
    base: TestRunResult
    head: TestRunResult

    @property
    def newly_failing(self) -> set[str]:
        return self.head.failed - self.base.failed

    @property
    def still_failing(self) -> set[str]:
        return self.head.failed & self.base.failed


PARAM_SUFFIX = re.compile(r"\[.*\]$")


def _test_id(classname: str, name: str) -> str:
    base_name = PARAM_SUFFIX.sub("", name)
    return f"{classname}.{base_name}" if classname else base_name


def _parse_junit(path: Path, result: TestRunResult) -> None:
    root = ET.parse(path).getroot()
    for case in root.iter("testcase"):
        test_id = _test_id(case.get("classname", ""), case.get("name", ""))
        if case.find("failure") is not None or case.find("error") is not None:
            result.failed.add(test_id)
        elif case.find("skipped") is not None:
            result.skipped.add(test_id)
        else:
            result.passed.add(test_id)


def run_tests_at_revision(repo: Path, revision: str, timeout_seconds: int = 180) -> TestRunResult:
    result = TestRunResult(revision=revision, ran=False)
    try:
        commit = verify_revision(repo, revision)
    except GitError as exc:
        result.errors.append(str(exc))
        return result
    tmp = Path(tempfile.mkdtemp(prefix="prtm-"))
    worktree = tmp / "worktree"
    junit = tmp / "junit.xml"
    try:
        run_git(repo, ["worktree", "add", "--detach", str(worktree), commit])
        env = {k: v for k, v in os.environ.items() if not SENSITIVE_ENV.search(k)}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        started = time.monotonic()
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}"],
            cwd=worktree, env=env, capture_output=True, text=True, timeout=timeout_seconds,
            encoding="utf-8", errors="replace",
        )
        result.duration_seconds = round(time.monotonic() - started, 2)
        result.output_tail = (proc.stdout + proc.stderr)[-3000:]
        if junit.exists():
            _parse_junit(junit, result)
            result.ran = True
        if proc.returncode == 5:
            result.errors.append("pytest collected no tests at this revision.")
        elif proc.returncode not in (0, 1):
            result.errors.append(f"pytest exited with code {proc.returncode} (collection or usage error).")
    except subprocess.TimeoutExpired:
        result.errors.append(f"Tests did not finish within {timeout_seconds} seconds and were stopped.")
    except GitError as exc:
        result.errors.append(f"Could not create a temporary worktree: {exc}")
    finally:
        try:
            run_git(repo, ["worktree", "remove", "--force", str(worktree)])
        except GitError:
            pass
        shutil.rmtree(tmp, ignore_errors=True)
    return result


def compare_revisions(repo: Path, base: str, head: str, timeout_seconds: int = 180) -> TestExecution:
    return TestExecution(
        base=run_tests_at_revision(repo, base, timeout_seconds),
        head=run_tests_at_revision(repo, head, timeout_seconds),
    )
