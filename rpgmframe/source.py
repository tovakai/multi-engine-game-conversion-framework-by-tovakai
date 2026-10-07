"""Prepare directory and ZIP inputs for RPGMFrame builds."""

from __future__ import annotations

import stat
import tempfile
import zipfile
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


def _safe_extract_zip(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()

    try:
        zipped = zipfile.ZipFile(archive)
    except (OSError, zipfile.BadZipFile) as exc:
        raise SourceError(f"Could not open ZIP archive {archive}: {exc}") from exc

    with zipped:
        for info in zipped.infolist():
            target = (destination / info.filename).resolve()
            if not _inside(root, target):
                raise SourceError(
                    f"Refusing unsafe path in ZIP archive: {info.filename}"
                )

            unix_mode = (info.external_attr >> 16) & 0o177777
            if stat.S_ISLNK(unix_mode):
                raise SourceError(
                    f"Refusing symlink in ZIP archive: {info.filename}"
                )

        try:
            zipped.extractall(destination)
        except OSError as exc:
            raise SourceError(f"Could not extract ZIP archive {archive}: {exc}") from exc


@contextmanager
def prepare_source(path: Path) -> Iterator[PreparedSource]:
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
        _safe_extract_zip(source, root)
        yield PreparedSource(
            original_path=source,
            root=root,
            archive_type="zip",
        )
