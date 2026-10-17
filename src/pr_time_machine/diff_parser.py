"""Parse unified diffs (the format produced by `git diff`), apply them, or create them."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class DiffParseError(ValueError):
    """Raised when diff text cannot be understood."""


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[tuple[str, str]] = field(default_factory=list)  # (" " | "-" | "+", text)


@dataclass
class FileDiff:
    old_path: str | None
    new_path: str | None
    hunks: list[Hunk] = field(default_factory=list)
    is_binary: bool = False

    @property
    def path(self) -> str:
        return self.new_path or self.old_path or ""

    @property
    def status(self) -> str:
        if self.old_path is None:
            return "added"
        if self.new_path is None:
            return "deleted"
        if self.old_path != self.new_path:
            return "renamed"
        return "modified"

    @property
    def is_python(self) -> bool:
        return self.path.endswith(".py") and not self.is_binary

    def deleted_old_lines(self) -> set[int]:
        """Line numbers (in the old file) that were removed or replaced."""
        result: set[int] = set()
        for hunk in self.hunks:
            line_no = hunk.old_start
            for tag, _ in hunk.lines:
                if tag == "-":
                    result.add(line_no)
                if tag in " -":
                    line_no += 1
        return result

    def added_new_lines(self) -> set[int]:
        """Line numbers (in the new file) that were added or replaced."""
        result: set[int] = set()
        for hunk in self.hunks:
            line_no = hunk.new_start
            for tag, _ in hunk.lines:
                if tag == "+":
                    result.add(line_no)
                if tag in " +":
                    line_no += 1
        return result


def _clean_path(raw: str) -> str | None:
    raw = raw.split("\t")[0].strip().strip('"')
    if raw == "/dev/null":
        return None
    if raw.startswith(("a/", "b/")):
        raw = raw[2:]
    return raw


def parse_unified_diff(text: str) -> list[FileDiff]:
    """Parse diff text into FileDiff objects. Raises DiffParseError on malformed hunks."""
    if not text or not text.strip():
        raise DiffParseError("The diff is empty.")
    lines = text.replace("\r\n", "\n").split("\n")
    files: list[FileDiff] = []
    current: FileDiff | None = None
    new_file = deleted_file = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("diff --git "):
            current = FileDiff(None, None)
            files.append(current)
            new_file = deleted_file = False
            match = re.match(r"diff --git a/(.+) b/(.+)$", line)
            if match:
                current.old_path, current.new_path = match.group(1), match.group(2)
        elif current is not None and line.startswith("new file mode"):
            new_file = True
            current.old_path = None
        elif current is not None and line.startswith("deleted file mode"):
            deleted_file = True
            current.new_path = None
        elif current is not None and line.startswith("rename from "):
            current.old_path = line[len("rename from "):]
        elif current is not None and line.startswith("rename to "):
            current.new_path = line[len("rename to "):]
        elif line.startswith(("Binary files ", "GIT binary patch")) and current is not None:
            current.is_binary = True
        elif line.startswith("--- ") and i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
            if current is None or current.hunks:
                current = FileDiff(None, None)
                files.append(current)
            current.old_path = None if new_file else _clean_path(line[4:])
            current.new_path = None if deleted_file else _clean_path(lines[i + 1][4:])
            i += 2
            continue
        else:
            match = HUNK_RE.match(line)
            if match:
                if current is None:
                    raise DiffParseError("Found a hunk (@@ line) before any file header.")
                hunk = Hunk(
                    int(match.group(1)), int(match.group(2) or 1),
                    int(match.group(3)), int(match.group(4) or 1),
                )
                i += 1
                old_seen = new_seen = 0
                while i < len(lines) and (old_seen < hunk.old_count or new_seen < hunk.new_count):
                    body_line = lines[i]
                    if body_line.startswith("\\"):  # "\ No newline at end of file"
                        i += 1
                        continue
                    tag, body = (" ", "") if body_line == "" else (body_line[0], body_line[1:])
                    if tag not in " +-":
                        raise DiffParseError(f"Unexpected line inside a hunk of {current.path}: {body_line[:60]!r}")
                    hunk.lines.append((tag, body))
                    old_seen += tag in " -"
                    new_seen += tag in " +"
                    i += 1
                current.hunks.append(hunk)
                continue
        i += 1
    files = [f for f in files if f.old_path or f.new_path]
    if not files:
        raise DiffParseError("No file changes were found. Paste a unified diff, e.g. the output of `git diff`.")
    return files


def apply_diff(old_files: dict[str, str], diffs: list[FileDiff]) -> tuple[dict[str, str], list[str]]:
    """Apply Python file diffs to a snapshot. Returns (new_files, problems)."""
    new_files = dict(old_files)
    problems: list[str] = []
    for fd in diffs:
        if not fd.is_python:
            continue
        if fd.status == "deleted":
            new_files.pop(fd.old_path, None)
            continue
        base = "" if fd.old_path is None else old_files.get(fd.old_path)
        if base is None:
            problems.append(f"{fd.old_path}: not found in the repository, so this file's changes were skipped.")
            continue
        src = base.split("\n")
        if src and src[-1] == "":
            src.pop()
        out: list[str] = []
        pos = 0
        failed = False
        for hunk in fd.hunks:
            start = hunk.old_start - 1 if hunk.old_count > 0 else hunk.old_start
            if start < pos or start > len(src):
                problems.append(f"{fd.path}: hunk at line {hunk.old_start} is out of order or past the end of the file.")
                failed = True
                break
            out.extend(src[pos:start])
            pos = start
            for tag, body in hunk.lines:
                if tag == "+":
                    out.append(body)
                    continue
                if pos >= len(src) or src[pos].rstrip("\r") != body.rstrip("\r"):
                    problems.append(f"{fd.path}: line {pos + 1} does not match the diff; the diff may be for a different version.")
                    failed = True
                    break
                if tag == " ":
                    out.append(src[pos])
                pos += 1
            if failed:
                break
        if failed:
            continue
        out.extend(src[pos:])
        if fd.status == "renamed":
            new_files.pop(fd.old_path, None)
        new_files[fd.new_path] = "\n".join(out) + "\n" if out else ""
    return new_files, problems


def make_unified_diff(old_files: dict[str, str], new_files: dict[str, str]) -> str:
    """Create a git-style unified diff between two snapshots (used by the benchmark)."""
    chunks: list[str] = []
    for path in sorted(set(old_files) | set(new_files)):
        old, new = old_files.get(path), new_files.get(path)
        if old == new:
            continue
        diff = difflib.unified_diff(
            (old or "").splitlines(), (new or "").splitlines(),
            fromfile=f"a/{path}" if old is not None else "/dev/null",
            tofile=f"b/{path}" if new is not None else "/dev/null",
            lineterm="",
        )
        chunks.append("\n".join(diff))
    return "\n".join(chunks) + "\n"
