"""Steam Frame packaging helpers shared by every conversion backend."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import stat
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath


class FramePackageError(RuntimeError):
    """Raised when a converted build cannot be packaged for Steam Frame."""


_METADATA_DIR = ".megcfbt"
_METADATA_FILE = "package.json"
_ARTWORK_DIR = "artwork"
_ARTWORK_SLOTS = frozenset({"grid", "wide", "hero", "logo", "icon"})
_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg"})

# FrameDrop 1.0.37's frozen framedrop.detect._safe_unzip rejects a ZIP when
# the sum of its unpacked members is over 4 GiB. Folder drops bypass that
# extraction path entirely.
FRAMEDROP_ZIP_UNPACK_LIMIT = 4 * 1024**3

_PORTABLE_EXECUTABLES = frozenset(
    {
        "launch.sh",
        "launch-steam.sh",
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


def default_zip_path(build_directory: Path) -> Path:
    name = build_directory.name
    base = name[:-6] if name.endswith("-frame") else name
    return build_directory.parent / f"{base}-linux-aarch64.zip"


def _relative_to_build(path: Path, build_directory: Path) -> str:
    try:
        return path.expanduser().resolve().relative_to(build_directory.resolve()).as_posix()
    except ValueError as exc:
        raise FramePackageError(f"{path} is not inside build directory {build_directory}") from exc


def _portable_executable(relative: Path, launcher_relative: str | None) -> bool:
    rel = relative.as_posix()
    name = relative.name
    parent = relative.parent.name
    return (
        rel == launcher_relative
        or name in _PORTABLE_EXECUTABLES
        or name.endswith(".sh")
        or parent in {"py2-linux-aarch64", "py3-linux-aarch64"}
    )


def _zip_timestamp(path: Path) -> tuple[int, int, int, int, int, int]:
    try:
        stamp = max(path.lstat().st_mtime, 315532800)
    except OSError:
        stamp = time.time()
    return time.localtime(stamp)[:6]


def _zip_info(
    path: Path,
    arcname: str,
    *,
    permissions: int,
    file_type: int,
    directory: bool = False,
) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(arcname + ("/" if directory and not arcname.endswith("/") else ""))
    info.date_time = _zip_timestamp(path)
    info.create_system = 3
    info.external_attr = ((file_type | permissions) & 0xFFFF) << 16
    if directory:
        info.external_attr |= 0x10
        info.compress_type = zipfile.ZIP_STORED
    else:
        info.compress_type = zipfile.ZIP_DEFLATED
    return info


def write_frame_metadata(
    build_directory: Path,
    *,
    name: str,
    launcher_path: Path,
    engine: str,
    engine_version: str | None = None,
) -> Path:
    """Write conversion metadata consumed by the on-device Steam installer."""

    root = build_directory.expanduser().resolve()
    if not root.is_dir():
        raise FramePackageError(f"Build directory does not exist: {root}")
    launcher = launcher_path.expanduser().resolve()
    if not launcher.is_file():
        raise FramePackageError(f"Launcher does not exist: {launcher}")

    relative_launcher = _relative_to_build(launcher, root)
    metadata_directory = root / _METADATA_DIR
    metadata_directory.mkdir(parents=True, exist_ok=True)
    metadata_path = metadata_directory / _METADATA_FILE
    metadata_path.write_text(
        json.dumps(
            {
                "schema": "megcfbt.frame-build/v1",
                "name": name,
                "launcher": relative_launcher,
                "architecture": "aarch64",
                "runtime": "SteamLinuxRuntime_4-arm64",
                "engine": engine,
                "engine_version": engine_version,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return metadata_path


def embed_steam_cover(build_directory: Path, cover: Path | str | None) -> Path | None:
    """Embed a user-selected portrait/grid image in the portable build metadata."""

    if cover is None:
        return None
    source = Path(cover).expanduser().resolve()
    if not source.is_file():
        raise FramePackageError(f"Steam cover does not exist: {source}")
    suffix = source.suffix.lower()
    if suffix not in _IMAGE_SUFFIXES:
        raise FramePackageError("Steam cover must be PNG or JPEG")

    destination = (
        build_directory.expanduser().resolve()
        / _METADATA_DIR
        / _ARTWORK_DIR
        / f"grid{suffix}"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def discover_artwork(build_directory: Path) -> dict[str, Path]:
    """Return artwork bundled with a converted build, keyed by Steam slot."""

    root = build_directory.expanduser().resolve()
    art = root / _METADATA_DIR / _ARTWORK_DIR
    found: dict[str, Path] = {}
    if art.is_dir():
        for slot in sorted(_ARTWORK_SLOTS):
            for suffix in (".png", ".jpg", ".jpeg"):
                candidate = art / f"{slot}{suffix}"
                if candidate.is_file():
                    found[slot] = candidate
                    break

    if "icon" not in found:
        for name in ("icon.png", "logo.png"):
            candidate = root / name
            if candidate.is_file():
                found["icon"] = candidate
                break
    return found


def load_frame_metadata(build_directory: Path) -> dict:
    root = build_directory.expanduser().resolve()
    path = root / _METADATA_DIR / _METADATA_FILE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise FramePackageError(f"Missing Frame build metadata: {path}") from exc
    except ValueError as exc:
        raise FramePackageError(f"Invalid Frame build metadata: {path}") from exc

    if payload.get("schema") != "megcfbt.frame-build/v1":
        raise FramePackageError(f"Unsupported Frame build metadata schema in {path}")
    launcher = payload.get("launcher")
    if not isinstance(launcher, str) or not launcher:
        raise FramePackageError(f"Frame build metadata has no launcher: {path}")
    normalized = launcher.replace("\\", "/")
    relative = PurePosixPath(normalized)
    if (
        relative.is_absolute()
        or any(part in {"", ".."} or ":" in part for part in relative.parts)
        or normalized.startswith("./../")
    ):
        raise FramePackageError(f"Frame build metadata has an unsafe launcher path: {launcher!r}")
    payload["launcher"] = relative.as_posix()
    return payload


def create_frame_zip(
    build_directory: Path,
    *,
    launcher_path: Path | None = None,
    output: Path | None = None,
    force: bool = False,
) -> Path:
    """Create a drop-in ZIP with an unambiguous top-level launch.sh.

    The real converted build lives under payload/. Keeping native runtime binaries
    one level below the trampoline makes generic installers prefer launch.sh while
    preserving each backend's internal layout unchanged.
    """

    source = build_directory.expanduser().resolve()
    if not source.is_dir():
        raise FramePackageError(f"Build directory does not exist: {source}")

    if launcher_path is not None:
        launcher_relative = _relative_to_build(launcher_path, source)
    else:
        launcher_relative = str(load_frame_metadata(source)["launcher"])
    source_launcher = source / Path(launcher_relative)
    if not source_launcher.is_file():
        raise FramePackageError(f"Converted launcher does not exist: {source_launcher}")

    archive = (
        output.expanduser().resolve()
        if output is not None
        else default_zip_path(source)
    )
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists() and not force:
        raise FramePackageError(
            f"Frame package already exists: {archive}. Pass --force to replace it."
        )

    temporary = archive.parent / f".{archive.name}.tmp-{uuid.uuid4().hex[:8]}"
    root_name = source.name
    target_literal = shlex.quote(launcher_relative)
    trampoline = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n\n"
        'ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'PAYLOAD="$ROOT/payload"\n'
        f"TARGET={target_literal}\n"
        'exec "$PAYLOAD/$TARGET" "$@"\n'
    ).encode("utf-8")

    def write_bytes(
        zf: zipfile.ZipFile,
        *,
        sample: Path,
        arcname: str,
        data: bytes,
        permissions: int = 0o644,
    ) -> None:
        info = _zip_info(
            sample,
            arcname,
            permissions=permissions,
            file_type=stat.S_IFREG,
        )
        zf.writestr(info, data)

    try:
        with zipfile.ZipFile(
            temporary,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
            allowZip64=True,
        ) as zf:
            zf.writestr(
                _zip_info(
                    source,
                    root_name,
                    permissions=0o755,
                    file_type=stat.S_IFDIR,
                    directory=True,
                ),
                b"",
            )
            write_bytes(
                zf,
                sample=source_launcher,
                arcname=f"{root_name}/launch.sh",
                data=trampoline,
                permissions=0o755,
            )

            payload_root = f"{root_name}/payload"
            zf.writestr(
                _zip_info(
                    source,
                    payload_root,
                    permissions=0o755,
                    file_type=stat.S_IFDIR,
                    directory=True,
                ),
                b"",
            )

            for path in sorted(source.rglob("*"), key=lambda p: p.as_posix()):
                relative = path.relative_to(source)
                arcname = f"{payload_root}/{relative.as_posix()}"

                if path.is_symlink():
                    info = _zip_info(
                        path,
                        arcname,
                        permissions=0o777,
                        file_type=stat.S_IFLNK,
                    )
                    zf.writestr(info, os.readlink(path).encode("utf-8"))
                    continue

                if path.is_dir():
                    zf.writestr(
                        _zip_info(
                            path,
                            arcname,
                            permissions=0o755,
                            file_type=stat.S_IFDIR,
                            directory=True,
                        ),
                        b"",
                    )
                    continue

                if not path.is_file():
                    continue

                executable = _portable_executable(relative, launcher_relative)
                info = _zip_info(
                    path,
                    arcname,
                    permissions=0o755 if executable else 0o644,
                    file_type=stat.S_IFREG,
                )
                with path.open("rb") as src, zf.open(info, "w") as dst:
                    shutil.copyfileobj(src, dst, 1 << 20)

            # Duplicate tiny integration metadata at the wrapper root so an extracted
            # package can itself be fed to our native steam-install command.
            metadata_path = source / _METADATA_DIR / _METADATA_FILE
            if metadata_path.is_file():
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                metadata["launcher"] = "launch.sh"
                metadata["payload"] = "payload"
                metadata["payload_launcher"] = launcher_relative
                write_bytes(
                    zf,
                    sample=metadata_path,
                    arcname=f"{root_name}/{_METADATA_DIR}/{_METADATA_FILE}",
                    data=(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
                )

            artwork_root = source / _METADATA_DIR / _ARTWORK_DIR
            if artwork_root.is_dir():
                for artwork in sorted(artwork_root.iterdir()):
                    if artwork.is_file() and artwork.suffix.lower() in _IMAGE_SUFFIXES:
                        write_bytes(
                            zf,
                            sample=artwork,
                            arcname=f"{root_name}/{_METADATA_DIR}/{_ARTWORK_DIR}/{artwork.name}",
                            data=artwork.read_bytes(),
                        )

            # Frame Control already treats these root names as shortcut-icon sources.
            for icon_name in ("icon.png", "logo.png"):
                icon = source / icon_name
                if icon.is_file():
                    write_bytes(
                        zf,
                        sample=icon,
                        arcname=f"{root_name}/{icon_name}",
                        data=icon.read_bytes(),
                    )

        if archive.exists():
            archive.unlink()
        temporary.replace(archive)
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        if isinstance(exc, FramePackageError):
            raise
        raise FramePackageError(f"Could not create Frame package {archive}: {exc}") from exc

    return archive

def zip_unpacked_size(path: Path | str) -> int:
    """Return the sum of uncompressed file sizes stored in a ZIP archive."""
    archive = Path(path).expanduser().resolve()
    if not archive.is_file() or archive.suffix.lower() != ".zip":
        raise FramePackageError(f"Expected a ZIP package: {archive}")
    try:
        with zipfile.ZipFile(archive) as zf:
            return sum(info.file_size for info in zf.infolist() if not info.is_dir())
    except (OSError, zipfile.BadZipFile) as exc:
        raise FramePackageError(f"Could not inspect ZIP package {archive}: {exc}") from exc


def framedrop_zip_compatible(path: Path | str) -> bool:
    """Whether FrameDrop's current 4 GiB ZIP extraction guard will accept it."""
    return zip_unpacked_size(path) <= FRAMEDROP_ZIP_UNPACK_LIMIT


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_install_manifest(
    package_path: Path,
    *,
    url: str,
    name: str,
    launcher_in_archive: str | None = None,
    output: Path | None = None,
) -> Path:
    """Create the shared FrameDrop/Frame Control web-install manifest."""

    package = package_path.expanduser().resolve()
    if not package.is_file() or package.suffix.lower() != ".zip":
        raise FramePackageError(f"Frame install manifest needs a ZIP package: {package}")
    if not url.lower().startswith("https://"):
        raise FramePackageError("Frame install manifests require an https:// package URL")

    destination = (
        output.expanduser().resolve()
        if output is not None
        else package.with_suffix(".framedrop.json")
    )
    entry: dict[str, object] = {
        "url": url,
        "sha256": sha256_file(package),
        "size": package.stat().st_size,
    }
    if launcher_in_archive:
        entry["exe"] = launcher_in_archive

    destination.write_text(
        json.dumps(
            {
                "schema": "framedrop.install/v1",
                "name": name,
                "files": [entry],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return destination
