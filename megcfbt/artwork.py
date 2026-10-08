"""Best-effort Steam library portrait acquisition for user-owned game packages.

Only a Steam AppID from the game's own metadata is considered a strong match.
Never search by fuzzy title and silently assign unrelated artwork.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_APPID = re.compile(r"^[1-9][0-9]{0,9}$")


def detected_steam_appid(build: Path) -> str | None:
    root = Path(build)
    for path in (root / "steam_appid.txt", root / "game" / "steam_appid.txt"):
        try:
            appid = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if _APPID.fullmatch(appid):
            return appid
    for path in (root / "steam_data.json", root / "game" / "steam_data.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        appid = str(data.get("app_id", "")).strip() if isinstance(data, dict) else ""
        if _APPID.fullmatch(appid):
            return appid
    return None


def fetch_official_steam_portrait(
    build: Path,
    *,
    progress=None,
) -> Path | None:
    """Cache official Steam library art when the source supplies a valid AppID.

    Artwork lookup is best-effort: no network, 404 or bad image must never
    prevent game conversion. A manual cover always takes precedence.
    """
    root = Path(build)
    appid = detected_steam_appid(root)
    if not appid:
        return None
    target = root / ".megcfbt" / "artwork" / "grid.jpg"
    if target.is_file():
        return target
    url = (
        "https://shared.fastly.steamstatic.com/store_item_assets/"
        f"steam/apps/{appid}/library_600x900.jpg"
    )
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "tovakai-frame-converter/1.0"})
        with urllib.request.urlopen(request, timeout=12) as response:
            mime = response.headers.get("Content-Type", "").split(";")[0].lower()
            if mime not in {"image/jpeg", "image/jpg"}:
                return None
            data = response.read(_MAX_IMAGE_BYTES + 1)
        if not data.startswith(b"\\xff\\xd8\\xff") or len(data) > _MAX_IMAGE_BYTES:
            return None
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        if progress:
            progress(f"Matched Steam library portrait using AppID {appid}")
        return target
    except (OSError, urllib.error.URLError, ValueError) as exc:
        if progress:
            progress(f"Steam artwork unavailable for AppID {appid}: {exc}")
        return None
