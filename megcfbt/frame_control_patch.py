"""Optional, reversible tweaks for a local Frame Control installation.

Frame Control currently caps raw uploads at 8 GiB in ui/server.py.  The packaged
Electron app ships that Python source as a normal resource, so we can safely
offer an opt-in 20 GiB patch without touching the executable itself.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

STOCK_LIMIT_GIB = 8
PATCHED_LIMIT_GIB = 20
BACKUP_SUFFIX = ".megcfbt-backup"

_STOCK_LINE = b"MAX_UPLOAD = 8 * 1024**3"
_PATCHED_LINE = b"MAX_UPLOAD = 20 * 1024**3"


def _exact_line_count(data: bytes, line: bytes) -> int:
    return sum(part == line for part in data.splitlines())


def _replace_exact_line(data: bytes, before: bytes, after: bytes) -> bytes:
    output: list[bytes] = []
    changed = 0
    for raw in data.splitlines(keepends=True):
        body = raw.rstrip(b"\r\n")
        ending = raw[len(body) :]
        if body == before:
            output.append(after + ending)
            changed += 1
        else:
            output.append(raw)
    if changed != 1:
        raise FrameControlPatchError(
            "Frame Control changed while it was being inspected; refusing to patch."
        )
    return b"".join(output)


class FrameControlPatchError(RuntimeError):
    """Raised when Frame Control cannot be identified or safely patched."""


@dataclass(frozen=True)
class FrameControlPatchStatus:
    server_path: Path
    limit_gib: int
    backup_path: Path

    @property
    def is_stock(self) -> bool:
        return self.limit_gib == STOCK_LIMIT_GIB

    @property
    def is_patched(self) -> bool:
        return self.limit_gib == PATCHED_LIMIT_GIB

    @property
    def has_backup(self) -> bool:
        return self.backup_path.is_file()


def backup_path_for(server_path: Path | str) -> Path:
    path = Path(server_path)
    return path.with_name(path.name + BACKUP_SUFFIX)


def _server_from_selection(path: Path) -> Path | None:
    """Turn a selected server.py, Frame Control.exe, or install directory into server.py."""
    path = path.expanduser()
    candidates: list[Path]
    if path.is_file():
        if path.name.lower() == "server.py":
            candidates = [path]
        else:
            candidates = [
                path.parent / "resources" / "ui" / "server.py",
                path.parent / "ui" / "server.py",
            ]
    else:
        candidates = [
            path / "server.py",
            path / "ui" / "server.py",
            path / "resources" / "ui" / "server.py",
        ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def candidate_server_paths() -> tuple[Path, ...]:
    """Return conservative, non-recursive Frame Control locations for this computer."""
    raw: list[Path] = []

    explicit = os.environ.get("FRAME_CONTROL_SERVER")
    if explicit:
        raw.append(Path(explicit))

    local = os.environ.get("LOCALAPPDATA")
    if local:
        root = Path(local) / "Programs"
        raw.extend(
            [
                root / "Frame Control",
                root / "frame-control",
                root / "FrameControl",
            ]
        )

    program_files = [os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)")]
    for value in program_files:
        if value:
            root = Path(value)
            raw.extend([root / "Frame Control", root / "frame-control"])

    # Handy for source checkouts and portable builds launched from their own folder.
    raw.extend([Path.cwd(), Path.cwd() / "Frame Control", Path.cwd() / "frame-control"])

    found: list[Path] = []
    seen: set[str] = set()
    for item in raw:
        server = _server_from_selection(item)
        if server is None:
            continue
        key = os.path.normcase(str(server))
        if key not in seen:
            seen.add(key)
            found.append(server)
    return tuple(found)


def locate_frame_control_server(selection: Path | str | None = None) -> Path | None:
    """Locate ui/server.py from an explicit selection or known install locations."""
    if selection is not None:
        return _server_from_selection(Path(selection))
    candidates = candidate_server_paths()
    return candidates[0] if candidates else None


def require_frame_control_server(selection: Path | str | None = None) -> Path:
    path = locate_frame_control_server(selection)
    if path is None:
        raise FrameControlPatchError(
            "Could not find Frame Control's ui/server.py. Select server.py or "
            "Frame Control.exe manually."
        )
    return path


def _limit_from_bytes(data: bytes) -> int:
    stock = _exact_line_count(data, _STOCK_LINE)
    patched = _exact_line_count(data, _PATCHED_LINE)
    if stock + patched != 1:
        if stock + patched > 1:
            raise FrameControlPatchError(
                "Frame Control has more than one recognized MAX_UPLOAD line; refusing to patch."
            )
        # A numeric custom/updated line is more useful to report than a generic mismatch.
        marker = b"MAX_UPLOAD = "
        lines = [line.strip() for line in data.splitlines() if line.strip().startswith(marker)]
        if len(lines) == 1:
            line = lines[0]
            prefix = marker
            suffix = b" * 1024**3"
            if line.startswith(prefix) and line.endswith(suffix):
                raw = line[len(prefix) : -len(suffix)]
                try:
                    return int(raw)
                except ValueError:
                    pass
        raise FrameControlPatchError(
            "This Frame Control version does not contain the expected MAX_UPLOAD line. "
            "It may have changed upstream, so the patch was not applied."
        )
    return STOCK_LIMIT_GIB if stock else PATCHED_LIMIT_GIB


def inspect_frame_control(selection: Path | str | None = None) -> FrameControlPatchStatus:
    server = require_frame_control_server(selection)
    try:
        data = server.read_bytes()
    except OSError as exc:
        raise FrameControlPatchError(f"Could not read {server}: {exc}") from exc
    return FrameControlPatchStatus(
        server_path=server,
        limit_gib=_limit_from_bytes(data),
        backup_path=backup_path_for(server),
    )


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".megcfbt-tmp")
    try:
        tmp.write_bytes(data)
        try:
            shutil.copystat(path, tmp)
        except OSError:
            pass
        os.replace(tmp, path)
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise FrameControlPatchError(f"Could not update {path}: {exc}") from exc


def patch_upload_limit(
    selection: Path | str | None = None,
    *,
    target_gib: int = PATCHED_LIMIT_GIB,
) -> FrameControlPatchStatus:
    """Patch a verified stock Frame Control 8 GiB limit to the supported 20 GiB tweak."""
    if target_gib != PATCHED_LIMIT_GIB:
        raise FrameControlPatchError(
            f"This patcher intentionally supports only {PATCHED_LIMIT_GIB} GiB."
        )

    status = inspect_frame_control(selection)
    if status.is_patched:
        return status
    if not status.is_stock:
        raise FrameControlPatchError(
            f"Frame Control already has a custom {status.limit_gib} GiB upload limit; "
            "refusing to overwrite it."
        )

    data = status.server_path.read_bytes()
    if _exact_line_count(data, _STOCK_LINE) != 1:
        raise FrameControlPatchError("Frame Control changed while it was being inspected.")

    backup = status.backup_path
    if backup.exists():
        try:
            backup_data = backup.read_bytes()
            if _limit_from_bytes(backup_data) != STOCK_LIMIT_GIB:
                raise FrameControlPatchError(
                    f"Existing backup is not a stock {STOCK_LIMIT_GIB} GiB Frame Control file: {backup}"
                )
        except OSError as exc:
            raise FrameControlPatchError(f"Could not verify backup {backup}: {exc}") from exc
    else:
        try:
            shutil.copy2(status.server_path, backup)
        except OSError as exc:
            raise FrameControlPatchError(f"Could not create backup {backup}: {exc}") from exc

    patched = _replace_exact_line(data, _STOCK_LINE, _PATCHED_LINE)
    _atomic_write(status.server_path, patched)
    result = inspect_frame_control(status.server_path)
    if not result.is_patched:
        raise FrameControlPatchError("Frame Control did not verify as patched after writing.")
    return result


def restore_upload_limit(selection: Path | str | None = None) -> FrameControlPatchStatus:
    """Restore the exact server.py saved before patching."""
    status = inspect_frame_control(selection)
    backup = status.backup_path
    if not backup.is_file():
        if status.is_stock:
            return status
        raise FrameControlPatchError(
            f"No backup exists at {backup}; refusing to synthesize an original file."
        )

    try:
        original = backup.read_bytes()
    except OSError as exc:
        raise FrameControlPatchError(f"Could not read backup {backup}: {exc}") from exc
    if _limit_from_bytes(original) != STOCK_LIMIT_GIB:
        raise FrameControlPatchError(
            f"Backup does not contain the verified stock {STOCK_LIMIT_GIB} GiB limit."
        )

    _atomic_write(status.server_path, original)
    restored = inspect_frame_control(status.server_path)
    if not restored.is_stock:
        raise FrameControlPatchError("Frame Control did not verify as restored after writing.")
    try:
        backup.unlink()
    except OSError:
        # Restoration succeeded; a leftover backup is harmless and useful.
        pass
    return inspect_frame_control(status.server_path)
