"""Package completed RPGMFrame builds for transfer."""

from __future__ import annotations

import tarfile
import uuid
from pathlib import Path


class PackagingError(RuntimeError):
    """Raised when a completed build cannot be packaged."""


# Windows filesystems do not preserve POSIX execute bits. These files are
# created/copied by RPGMFrame specifically to be executed after extraction on
# Linux, so normalize their archive metadata independently of the host OS.
_PORTABLE_EXECUTABLES = frozenset(
    {
        "launch.sh",
        "nw",
        "chrome_crashpad_handler",
        "chrome-sandbox",
        "mkxp-z.aarch64",
        "godot.arm64",
    }
)


def _portable_tar_filter(info: tarfile.TarInfo) -> tarfile.TarInfo:
    relative = Path(info.name)
    if info.isfile():
        name = relative.name
        # launch.sh and the Linux NW.js helpers live at the converted package
        # root. Shell helpers are executable wherever RPGMFrame adds them.
        if name in _PORTABLE_EXECUTABLES or name.endswith(".sh"):
            info.mode |= 0o111
    return info


def default_archive_path(build_directory: Path) -> Path:
    name = build_directory.name
    base = name[:-6] if name.endswith("-frame") else name
    return build_directory.parent / f"{base}-linux-aarch64.tar.gz"


def create_tar_gz(
    build_directory: Path,
    *,
    output: Path | None = None,
    force: bool = False,
) -> Path:
    """Create a portable tar.gz containing the complete build directory."""
    source = build_directory.expanduser().resolve()
    if not source.is_dir():
        raise PackagingError(f"Build directory does not exist: {source}")

    archive = (
        output.expanduser().resolve()
        if output is not None
        else default_archive_path(source)
    )
    archive.parent.mkdir(parents=True, exist_ok=True)

    if archive.exists() and not force:
        raise PackagingError(
            f"Archive already exists: {archive}. Pass --force to replace it."
        )

    temporary = archive.parent / f".{archive.name}.tmp-{uuid.uuid4().hex[:8]}"
    try:
        with tarfile.open(temporary, "w:gz", format=tarfile.PAX_FORMAT) as tar:
            tar.add(
                source,
                arcname=source.name,
                recursive=True,
                filter=_portable_tar_filter,
            )

        if archive.exists():
            archive.unlink()
        temporary.replace(archive)
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        if isinstance(exc, PackagingError):
            raise
        raise PackagingError(f"Could not create archive {archive}: {exc}") from exc

    return archive
