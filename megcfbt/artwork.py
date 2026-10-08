"""Best-effort Steam artwork discovery for converted Frame packages.

Artwork is optional enrichment. Conversion must never depend on the Steam CDN
being available. A detected Steam App ID is used as the stable lookup key.
"""

from __future__ import annotations

import json
import shutil
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

_MAX_IMAGE_BYTES = 20 * 1024 * 1024
_USER_AGENT = "tovakai-frame-converter/0.1"

# Official Steam CDN assets. Not every title provides every slot.
_STEAM_ART_CANDIDATES: dict[str, tuple[str, ...]] = {
    "grid": (
        "library_600x900_2x.jpg",
        "library_600x900.jpg",
    ),
    "wide": (
        "header.jpg",
    ),
    "hero": (
        "library_hero.jpg",
    ),
    "logo": (
        "logo.png",
    ),
}


def _numeric_app_id(value: object) -> str | None:
    text = str(value or "").strip()
    return text if text.isdigit() else None


def _read_app_id_file(path: Path) -> str | None:
    try:
        return _numeric_app_id(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None


def _read_steam_data(path: Path) -> str | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    return _numeric_app_id(value.get("app_id"))


def discover_steam_app_id(root: Path | str) -> str | None:
    """Find a Steam App ID from common game sidecars without deep scanning."""

    base = Path(root).expanduser().resolve()
    if not base.exists():
        return None

    direct = (
        base / "steam_appid.txt",
        base / "steam_data.json",
        base / "game" / "steam_appid.txt",
        base / "game" / "steam_data.json",
    )
    for path in direct:
        if path.name == "steam_data.json":
            app_id = _read_steam_data(path)
        else:
            app_id = _read_app_id_file(path)
        if app_id:
            return app_id

    # Archives often unpack through one or two wrapper directories. Keep this
    # intentionally shallow so artwork enrichment cannot turn into a filesystem
    # crawl on large games.
    frontier = [base]
    for _ in range(3):
        next_frontier: list[Path] = []
        for directory in frontier:
            try:
                children = [p for p in directory.iterdir() if p.is_dir()]
            except OSError:
                continue
            for child in children[:64]:
                for name, reader in (
                    ("steam_appid.txt", _read_app_id_file),
                    ("steam_data.json", _read_steam_data),
                ):
                    app_id = reader(child / name)
                    if app_id:
                        return app_id
                next_frontier.append(child)
        frontier = next_frontier
        if not frontier:
            break
    return None


def _image_suffix(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    return None


def _download_image(url: str) -> tuple[bytes, str] | None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": _USER_AGENT, "Accept": "image/*"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            length = response.headers.get("Content-Length")
            if length and length.isdigit() and int(length) > _MAX_IMAGE_BYTES:
                return None
            data = response.read(_MAX_IMAGE_BYTES + 1)
    except (OSError, urllib.error.URLError, urllib.error.HTTPError):
        return None
    if len(data) > _MAX_IMAGE_BYTES:
        return None
    suffix = _image_suffix(data)
    return (data, suffix) if suffix else None


def fetch_official_steam_artwork(
    app_id: str,
    build_directory: Path | str,
    *,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Path]:
    """Download available official Steam artwork into .megcfbt/artwork.

    Missing assets or network errors are silently tolerated after a concise log
    message; artwork must never block conversion.
    """

    app_id = _numeric_app_id(app_id) or ""
    if not app_id:
        return {}

    root = Path(build_directory).expanduser().resolve()
    art_dir = root / ".megcfbt" / "artwork"
    found: dict[str, Path] = {}

    if progress:
        progress(f"Steam AppID {app_id} detected; looking for official artwork…")

    base = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}"
    for slot, names in _STEAM_ART_CANDIDATES.items():
        for name in names:
            result = _download_image(f"{base}/{name}")
            if result is None:
                continue
            data, suffix = result
            art_dir.mkdir(parents=True, exist_ok=True)
            target = art_dir / f"{slot}{suffix}"
            target.write_bytes(data)
            found[slot] = target
            break

    # Give Frame installers a conventional root icon when a suitable image is
    # available. The portrait remains in metadata for Steam library artwork.
    icon_source = found.get("logo") or found.get("grid")
    if icon_source is not None:
        root_icon = root / f"icon{icon_source.suffix.lower()}"
        shutil.copy2(icon_source, root_icon)
        found["icon"] = root_icon

    if progress:
        if found:
            slots = ", ".join(sorted(found))
            progress(f"Bundled official Steam artwork: {slots}")
        else:
            progress("No official Steam artwork was available; continuing without it")
    return found
