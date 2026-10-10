"""Prepare directory and ZIP inputs for RPGMFrame builds."""

from __future__ import annotations

import stat
import tempfile
import zipfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


class SourceError(RuntimeError):
    """Raised when a source cannot be prepared safely."""


@dataclass(frozen=True)
class PreparedSource:
    original_path: Path
    root: Path
    archive_type: str | None = None


def _inside(root: Path, candidate: Path) -> bool:
    return candidate == root or root in candidate.parents


def _safe_extract_zip(archive: Path, destination: Path, *, progress=None) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()

    try:
        zipped = zipfile.ZipFile(archive)
    except (OSError, zipfile.BadZipFile) as exc:
        raise SourceError(f"Could not open ZIP archive {archive}: {exc}") from exc

    with zipped:
        entries = []
        seen = {}
        reserved = {'con','prn','aux','nul'} | {f'{prefix}{n}' for prefix in ('com','lpt') for n in range(1,10)}
        for info in zipped.infolist():
            name = info.filename.replace("\\", "/")
            while name.startswith('./'):
                name = name[2:]
            if not name and info.is_dir():
                continue
            parts = name.rstrip("/").split("/")
            if any(part in {"", ".", ".."} or part.endswith((' ','.'))
                   or part.split('.')[0].casefold() in reserved
                   or any(ord(char) < 32 or char in '<>:"|?*' for char in part)
                   for part in parts) or name.startswith("/"):
                raise SourceError(f"Refusing unsafe path in ZIP archive: {info.filename}")
            target = (destination / name).resolve()
            if not _inside(root, target):
                raise SourceError(
                    f"Refusing unsafe path in ZIP archive: {info.filename}"
                )

            unix_mode = (info.external_attr >> 16) & 0o177777
            if stat.S_ISLNK(unix_mode):
                raise SourceError(
                    f"Refusing symlink in ZIP archive: {info.filename}"
                )
            key = "/".join(parts).casefold()
            if key in seen:
                raise SourceError(f"Refusing duplicate path in ZIP archive: {info.filename}")
            seen[key] = info.is_dir() or name.endswith("/")
            entries.append((info, target, key))

        for info, target, key in entries:
            ancestors = key.split("/")[:-1]
            for length in range(1, len(ancestors) + 1):
                if seen.get("/".join(ancestors[:length])) is False:
                    raise SourceError(f"Refusing file/directory collision in ZIP archive: {info.filename}")

        try:
            total = sum(info.file_size for info, _, _ in entries)
            copied, last_report = 0, time.monotonic()
            if progress:
                progress(f'Extracting {archive.name}: {total / 1024**2:.1f} MiB')
            for info, target, key in entries:
                if seen[key]:
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zipped.open(info) as source, target.open("wb") as output:
                        while chunk := source.read(1024 * 1024):
                            output.write(chunk)
                            copied += len(chunk)
                            if progress and time.monotonic() - last_report >= 2:
                                progress(f'Extracting {archive.name}: {copied / 1024**2:.1f} / {total / 1024**2:.1f} MiB')
                                last_report = time.monotonic()
                    mode = (info.external_attr >> 16) & 0o777
                    if mode:
                        target.chmod(mode)
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            raise SourceError(f"Could not extract ZIP archive {archive}: {exc}") from exc


@contextmanager
def prepare_source(path: Path, *, progress=None) -> Iterator[PreparedSource]:
    """
    Yield a directory suitable for engine inspection/building.

    Directories are used in place. ZIP archives are safely unpacked into a
    temporary workspace that is deleted when the build finishes.
    """
    source = path.expanduser().resolve()

    if source.is_dir():
        yield PreparedSource(original_path=source, root=source)
        return

    if not source.exists():
        raise SourceError(f"Source path does not exist: {source}")

    if not source.is_file():
        raise SourceError(f"Source path is not a directory or regular file: {source}")

    if source.suffix.lower() != ".zip":
        raise SourceError(
            f"Unsupported source archive: {source.name}. "
            "RPGMFrame currently accepts directories and .zip files."
        )

    with tempfile.TemporaryDirectory(prefix="rpgmframe-source-") as temporary:
        root = Path(temporary)
        _safe_extract_zip(source, root, progress=progress)
        yield PreparedSource(
            original_path=source,
            root=root,
            archive_type="zip",
        )
