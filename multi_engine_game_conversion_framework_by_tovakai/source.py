"""Safe temporary source preparation for cross-engine inspection."""

from __future__ import annotations

import stat
import tarfile
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class SourceError(RuntimeError):
    pass


def source_base_name(path: Path | str) -> str:
    p = Path(path)
    lower = p.name.lower()
    for suffix in (".tar.gz", ".tar.bz2", ".tar.xz"):
        if lower.endswith(suffix):
            return p.name[: -len(suffix)]
    if p.suffix.lower() in {".zip", ".tgz", ".tbz2", ".txz"}:
        return p.stem
    return p.name


def _inside(root: Path, candidate: Path) -> bool:
    return candidate == root or root in candidate.parents


def _safe_extract_zip(archive: Path, destination: Path) -> None:
    root = destination.resolve()
    with zipfile.ZipFile(archive) as zipped:
        for info in zipped.infolist():
            target = (destination / info.filename).resolve()
            if not _inside(root, target):
                raise SourceError(f"Refusing unsafe path in ZIP: {info.filename}")
            mode = (info.external_attr >> 16) & 0o177777
            if stat.S_ISLNK(mode):
                raise SourceError(f"Refusing symlink in ZIP: {info.filename}")
        zipped.extractall(destination)


def _safe_extract_tar(archive: Path, destination: Path) -> None:
    root = destination.resolve()
    with tarfile.open(archive, "r:*") as tar:
        for member in tar.getmembers():
            target = (destination / member.name).resolve()
            if not _inside(root, target):
                raise SourceError(f"Refusing unsafe path in TAR: {member.name}")
            if member.issym():
                link = (target.parent / member.linkname).resolve()
                if not _inside(root, link):
                    raise SourceError(f"Refusing unsafe symlink in TAR: {member.name}")
            elif member.islnk():
                link = (destination / member.linkname).resolve()
                if not _inside(root, link):
                    raise SourceError(f"Refusing unsafe hardlink in TAR: {member.name}")
        tar.extractall(destination)


def _is_tar_name(path: Path) -> bool:
    lower = path.name.lower()
    return (
        lower.endswith((".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz"))
        or path.suffix.lower() == ".tar"
    )


@contextmanager
def prepare_for_inspection(path: Path | str) -> Iterator[Path]:
    source = Path(path).expanduser().resolve()
    if source.is_dir():
        yield source
        return
    if not source.exists() or not source.is_file():
        raise SourceError(f"Source path does not exist or is not a regular file: {source}")

    with tempfile.TemporaryDirectory(prefix="tovakai-engine-inspect-") as temporary:
        root = Path(temporary)
        try:
            if source.suffix.lower() == ".zip":
                _safe_extract_zip(source, root)
            elif _is_tar_name(source):
                _safe_extract_tar(source, root)
            else:
                raise SourceError(
                    f"Unsupported archive for inspection: {source.name}. "
                    "Use a folder, ZIP, or TAR-family archive."
                )
        except (OSError, zipfile.BadZipFile, tarfile.TarError) as exc:
            raise SourceError(f"Could not inspect archive {source}: {exc}") from exc
        yield root


def candidate_roots(root: Path, max_depth: int = 5) -> list[Path]:
    """Return root plus an unambiguous single-directory wrapper chain."""
    out = [root]
    current = root
    for _ in range(max_depth):
        try:
            dirs = [
                child
                for child in current.iterdir()
                if child.is_dir()
                and not child.name.startswith(".")
                and child.name != "__MACOSX"
            ]
        except OSError:
            break
        if len(dirs) != 1:
            break
        current = dirs[0]
        out.append(current)
    return out
