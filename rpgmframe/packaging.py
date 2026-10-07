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
        "python",
        "python3",
        "pythonw",
        "pythonw3",
        "renpy",
    }
)


def _portable_tar_filter(info: tarfile.TarInfo) -> tarfile.TarInfo:
    relative = Path(info.name)
    if info.isfile():
        name = relative.name
        parent = relative.parent.name
        renpy_arm_entry = parent in {
            "py2-linux-aarch64",
            "py3-linux-aarch64",
        }
        # Windows filesystems discard POSIX execute bits. Normalize launchers,
        # native runtime entrypoints, and direct Ren'Py ARM platform files.
        # Ren'Py distributions name the executable after the game's .sh file,
        # so that final case cannot be represented by a fixed filename list.
        if (
            name in _PORTABLE_EXECUTABLES
            or name.endswith(".sh")
            or renpy_arm_entry
        ):
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
        # Game payloads such as PCK/archives are commonly already compressed.
        # Level 1 keeps transfer archives portable while avoiding a long,
        # single-threaded recompression pass for negligible size savings.
        with tarfile.open(
            temporary,
            "w:gz",
            format=tarfile.PAX_FORMAT,
            compresslevel=1,
        ) as tar:
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
