"""Read Steam shortcuts and transactionally replace artwork, never shortcut data."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
import uuid

SLOTS = {
    "portrait": ("Portrait grid", "p", "600 × 900"),
    "wide": ("Landscape grid", "", "920 × 430"),
    "hero": ("Hero banner", "_hero", "1920 × 620"),
    "logo": ("Logo", "_logo", "transparent PNG"),
}
EXTENSIONS = (".png", ".jpg", ".jpeg")
MAX_FILE = 32 * 1024 * 1024


class ArtworkError(ValueError):
    pass


@dataclass(frozen=True)
class Shortcut:
    appid: int
    name: str
    executable: str


def parse_shortcuts(data: bytes) -> list[Shortcut]:
    """Bounded binary KeyValues reader. Unknown types fail without any writes."""
    if len(data) > MAX_FILE:
        raise ArtworkError("Steam shortcut file is too large.")
    position = 0

    def take(size):
        nonlocal position
        if position + size > len(data):
            raise ArtworkError("Truncated Steam shortcut file.")
        value = data[position:position + size]
        position += size
        return value

    def string():
        nonlocal position
        end = data.find(b"\0", position)
        if end < 0:
            raise ArtworkError("Unterminated Steam shortcut field.")
        value = data[position:end].decode("utf-8", errors="replace")
        position = end + 1
        return value

    def object_(depth=0):
        if depth > 16:
            raise ArtworkError("Steam shortcut nesting exceeds limit.")
        values = {}
        while True:
            kind = take(1)[0]
            if kind == 8:
                return values
            key = string().casefold()
            if key in values:
                raise ArtworkError("Duplicate Steam shortcut field.")
            if kind == 0:
                value = object_(depth + 1)
            elif kind == 1:
                value = string()
            elif kind == 2:
                value = struct.unpack("<I", take(4))[0]
            elif kind == 3:
                value = struct.unpack("<f", take(4))[0]
            elif kind == 7:
                value = struct.unpack("<Q", take(8))[0]
            else:
                raise ArtworkError(f"Unsupported Steam shortcut field type: {kind}.")
            values[key] = value

    root = object_()
    if position != len(data) or not isinstance(root.get("shortcuts"), dict):
        raise ArtworkError("Invalid Steam shortcut file.")
    result = []
    seen = set()
    for item in root["shortcuts"].values():
        if not isinstance(item, dict):
            raise ArtworkError("Invalid Steam shortcut entry.")
        appid, name = item.get("appid"), item.get("appname")
        if type(appid) is not int or not appid or not isinstance(name, str):
            raise ArtworkError("Shortcut is missing its stored AppID or name.")
        if appid in seen:
            raise ArtworkError("Duplicate shortcut AppID; resolve this in Steam first.")
        seen.add(appid)
        result.append(Shortcut(appid, name, str(item.get("exe", ""))))
    return sorted(result, key=lambda entry: (entry.name.casefold(), entry.appid))


def shortcuts(profile: Path) -> list[Shortcut]:
    path = profile / "config" / "shortcuts.vdf"
    if path.stat().st_size > MAX_FILE:
        raise ArtworkError("Steam shortcut file is too large.")
    return parse_shortcuts(path.read_bytes())


def discover_profiles(home: Path | None = None) -> list[Path]:
    home = home or Path.home()
    roots = [home / ".steam/steam", home / ".steam/root",
             home / ".local/share/Steam", home / ".var/app/com.valvesoftware.Steam/.local/share/Steam"]
    found = set()
    for root in roots:
        for file in (root / "userdata").glob("*/config/shortcuts.vdf"):
            if file.parent.parent.name.isdigit():
                found.add(file.parent.parent.resolve())
    return sorted(found)


def artwork_paths(profile: Path, entry: Shortcut, slot: str) -> list[Path]:
    suffix = SLOTS[slot][1]
    grid = profile / "config/grid"
    return [grid / f"{entry.appid}{suffix}{ext}" for ext in EXTENSIONS]


def read_image(path: Path) -> tuple[bytes, str]:
    """Validate actual decoded format, not a user-controlled filename extension."""
    from PIL import Image, UnidentifiedImageError
    if path.stat().st_size > MAX_FILE:
        raise ArtworkError("Choose an image smaller than 32 MiB.")
    data = path.read_bytes()
    from io import BytesIO
    try:
        with Image.open(BytesIO(data)) as image:
            extension = {"PNG": ".png", "JPEG": ".jpg"}.get(image.format)
            if not extension:
                raise ArtworkError("Choose a PNG or JPEG image.")
            if image.width * image.height > 40_000_000:
                raise ArtworkError("Choose an image below 40 megapixels.")
            image.verify()
        with Image.open(BytesIO(data)) as image:
            image.load()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError) as exc:
        raise ArtworkError("This image could not be read as a valid PNG or JPEG.") from exc
    return data, extension


def _atomic_write(path: Path, data: bytes):
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".artwork-", delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def apply_artwork(profile: Path, entry: Shortcut, selections: dict[str, Path]) -> Path:
    if not selections or set(selections) - SLOTS.keys():
        raise ArtworkError("Choose at least one artwork image.")
    if entry not in shortcuts(profile):
        raise ArtworkError("This Steam entry changed. Refresh the entry list first.")
    images = {slot: read_image(path) for slot, path in selections.items()}
    grid = profile / "config/grid"
    grid.mkdir(exist_ok=True)
    targets = [path for slot in selections for path in artwork_paths(profile, entry, slot)]
    # Refuse links so rollback cannot change files outside this profile.
    if grid.is_symlink() or any(p.is_symlink() or (p.exists() and not p.is_file()) for p in targets):
        raise ArtworkError("Artwork paths contain links or non-files; no artwork changed.")
    backup_root = profile / "config/artwork-companion-backups"
    if backup_root.is_symlink():
        raise ArtworkError("The artwork backup directory must not be a symbolic link.")
    backup = backup_root / uuid.uuid4().hex
    backup.mkdir(parents=True)
    before = {}
    for path in targets:
        before[path.name] = path.exists()
        if path.exists():
            shutil.copy2(path, backup / path.name)
    # Publish the recovery record before modifying artwork.
    manifest = {"appid": entry.appid, "name": entry.name, "before": before, "after": {}}
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    try:
        for slot, (data, extension) in images.items():
            paths = artwork_paths(profile, entry, slot)
            destination = grid / f"{entry.appid}{SLOTS[slot][1]}{extension}"
            _atomic_write(destination, data)
            for path in paths:
                if path != destination:
                    path.unlink(missing_ok=True)
        manifest["after"] = {p.name: _digest(p) for p in targets}
        _atomic_write(backup / "manifest.json", json.dumps(manifest, indent=2).encode())
    except BaseException:
        for path in targets:
            if before[path.name]:
                _atomic_write(path, (backup / path.name).read_bytes())
            else:
                path.unlink(missing_ok=True)
        raise
    return backup


def undo_artwork(profile: Path, backup: Path):
    expected_parent = (profile / "config/artwork-companion-backups").resolve()
    if backup.resolve().parent != expected_parent or backup.is_symlink():
        raise ArtworkError("Backup does not belong to this Steam profile.")
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    appid = manifest["appid"]
    if type(appid) is not int or not 0 < appid <= 0xFFFFFFFF:
        raise ArtworkError("Invalid artwork backup AppID.")
    allowed = {f"{appid}{suffix}{ext}" for _, suffix, _ in SLOTS.values() for ext in EXTENSIONS}
    before, after = manifest["before"], manifest["after"]
    if not before or set(before) != set(after) or set(before) - allowed:
        raise ArtworkError("Incomplete artwork backup; manual recovery may be needed.")
    grid = profile / "config/grid"
    if grid.is_symlink():
        raise ArtworkError("The artwork directory changed; no artwork restored.")
    contents, current = {}, {}
    for name, existed in before.items():
        path = grid / name
        if path.is_symlink() or _digest(path) != after[name]:
            raise ArtworkError("Artwork changed since Apply. Undo would overwrite newer artwork.")
        current[name] = path.read_bytes() if path.exists() else None
        source = backup / name
        if existed:
            if source.is_symlink():
                raise ArtworkError("Invalid backup image link.")
            contents[name] = source.read_bytes()
    try:
        for name in before:
            if name in contents:
                _atomic_write(grid / name, contents[name])
            else:
                (grid / name).unlink(missing_ok=True)
    except BaseException:
        for name, data in current.items():
            if data is not None:
                _atomic_write(grid / name, data)
            else:
                (grid / name).unlink(missing_ok=True)
        raise
