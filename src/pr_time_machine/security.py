"""Safety checks for uploaded repositories.

Uploaded ZIP files are read directly in memory. Nothing is extracted to disk,
imported, or executed, which removes the classic "zip slip" risk entirely.
We still reject archives that contain unsafe paths so a malicious upload is
reported clearly instead of being silently half-read.
"""

from __future__ import annotations

import io
import stat
import zipfile
from pathlib import PurePosixPath
from typing import Callable

MAX_COMPRESSION_RATIO = 100  # protects against "zip bombs"


class UnsafeArchiveError(ValueError):
    """Raised when an uploaded archive is invalid or unsafe."""


def is_safe_member_name(name: str) -> bool:
    if not name or "\x00" in name:
        return False
    if name.startswith(("/", "\\")) or "\\" in name:
        return False
    parts = PurePosixPath(name).parts
    if not parts or ":" in parts[0]:  # Windows drive letters such as C:
        return False
    return ".." not in parts


def read_python_files_from_zip(
    data: bytes,
    *,
    max_files: int,
    max_file_bytes: int,
    max_total_bytes: int,
    is_ignored: Callable[[str], bool],
) -> tuple[dict[str, str], list[str]]:
    """Return {posix_path: source_text} for Python files plus a list of warnings."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UnsafeArchiveError("The upload is not a valid ZIP file.") from exc

    infos = archive.infolist()
    if len(infos) > max_files * 20:
        raise UnsafeArchiveError(f"The archive has {len(infos)} entries, which is above the safety limit.")

    for info in infos:
        if not is_safe_member_name(info.filename):
            raise UnsafeArchiveError(f"Rejected unsafe path in archive: {info.filename!r}")
        if stat.S_ISLNK(info.external_attr >> 16):
            raise UnsafeArchiveError(f"Rejected symbolic link in archive: {info.filename!r}")

    files: dict[str, str] = {}
    warnings: list[str] = []
    total = 0
    for info in infos:
        name = info.filename
        if info.is_dir() or not name.endswith(".py") or is_ignored(name):
            continue
        if info.file_size > max_file_bytes:
            warnings.append(f"Skipped {name}: larger than {max_file_bytes:,} bytes.")
            continue
        if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
            raise UnsafeArchiveError(f"Rejected {name}: suspicious compression ratio (possible zip bomb).")
        if len(files) >= max_files:
            raise UnsafeArchiveError(f"More than {max_files} Python files; raise the limit or upload a smaller repository.")
        total += info.file_size
        if total > max_total_bytes:
            raise UnsafeArchiveError(f"Python files exceed the {max_total_bytes:,}-byte limit.")
        with archive.open(info) as handle:
            raw = handle.read(max_file_bytes + 1)
        if len(raw) > max_file_bytes:
            warnings.append(f"Skipped {name}: larger than {max_file_bytes:,} bytes after decompression.")
            continue
        files[name] = raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
    return files, warnings
