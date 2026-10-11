"""Optional SteamGridDB artwork fallback for portable Steam Frame packages.

Only a unique exact-title match, a verified Steam AppID, or an explicitly
selected SteamGridDB game ID is used. This is not a fuzzy title scraper.
The API key is read from the process environment and never persisted.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_API = "https://www.steamgriddb.com/api/v2"
_MAX_JSON_BYTES = 1024 * 1024
_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_ASSET_SUFFIXES = {".png", ".jpg", ".jpeg"}
_ASSET_QUERIES = {
    "grid": ("grids", "dimensions=600x900"),
    "wide": ("grids", "dimensions=920x430"),
    "hero": ("heroes", ""),
    "logo": ("logos", ""),
}


def _notify(progress, message: str) -> None:
    if progress:
        progress(message)


def _api_json(path: str, api_key: str) -> dict:
    request = urllib.request.Request(
        _API + "/" + path,
        headers={
            "Authorization": "Bearer " + api_key,
            "Accept": "application/json",
            "User-Agent": "tovakai-frame-converter/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        if response.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            raise ValueError("SteamGridDB returned non-JSON content")
        data = response.read(_MAX_JSON_BYTES + 1)
    if len(data) > _MAX_JSON_BYTES:
        raise ValueError("SteamGridDB response exceeds size limit")
    decoded = json.loads(data)
    if not isinstance(decoded, dict) or decoded.get("success") is not True:
        raise ValueError("SteamGridDB returned an unsuccessful response")
    return decoded


def _normalized_title(name: str) -> str:
    value = unicodedata.normalize("NFKC", name).casefold().strip()
    return re.sub(r"[\W_]+", " ", value, flags=re.UNICODE).strip()


def _resolve_game(
    game_name: str,
    api_key: str,
    *,
    steam_appid: str | None = None,
    selected_game_id: int | None = None,
) -> dict | None:
    if selected_game_id is not None:
        if isinstance(selected_game_id, bool) or not isinstance(selected_game_id, int) or selected_game_id <= 0:
            raise ValueError("SteamGridDB game ID must be a positive integer")
        data = _api_json(f"games/id/{selected_game_id}", api_key).get("data")
        return data if isinstance(data, dict) and data.get("id") == selected_game_id else None

    if steam_appid and re.fullmatch(r"[1-9]\d{0,9}", steam_appid):
        data = _api_json(f"games/steam/{steam_appid}", api_key).get("data")
        return data if isinstance(data, dict) else None

    if not game_name or not _normalized_title(game_name):
        return None

    term = urllib.parse.quote(game_name.strip(), safe="")
    matches = _api_json(f"search/autocomplete/{term}", api_key).get("data")
    if not isinstance(matches, list):
        return None

    exact: dict[int, dict] = {}
    wanted = _normalized_title(game_name)
    for entry in matches:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        game_id = entry.get("id")
        if (
            isinstance(name, str)
            and isinstance(game_id, int)
            and not isinstance(game_id, bool)
            and game_id > 0
            and _normalized_title(name) == wanted
        ):
            exact[game_id] = entry
    if len(exact) > 1:
        raise ValueError("SteamGridDB match ambiguous: multiple exact-title games")
    return next(iter(exact.values()), None)


def _asset_is_safe(url: str) -> bool:
    try:
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower()
        return (
            parts.scheme == "https"
            and parts.username is None
            and parts.password is None
            and parts.port in (None, 443)
            and (host == "steamgriddb.com" or host.endswith(".steamgriddb.com"))
        )
    except ValueError:
        return False


def _select_asset(items: object) -> dict | None:
    if not isinstance(items, list):
        return None
    allowed = [
        entry for entry in items
        if isinstance(entry, dict)
        and isinstance(entry.get("url"), str)
        and _asset_is_safe(entry["url"])
        and not bool(set(entry.get("tags") or []) & {"humor", "epilepsy"})
    ]
    if not allowed:
        return None

    def quality(item: dict) -> tuple:
        tags = item.get("tags") or []
        score = item.get("score", 0)
        score = score if isinstance(score, (int, float)) and not isinstance(score, bool) else 0
        uid = item.get("id", 0)
        uid = uid if isinstance(uid, int) else 0
        return (0 if "nsfw" not in tags else 1, -score, uid)

    return min(allowed, key=quality)


def _asset_bytes(url: str, *, logo: bool) -> tuple[bytes, str]:
    if not _asset_is_safe(url):
        raise ValueError("SteamGridDB asset URL is not trusted")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "tovakai-frame-converter/1.0"},
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        mime = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
        data = response.read(_MAX_IMAGE_BYTES + 1)
    if len(data) > _MAX_IMAGE_BYTES:
        raise ValueError("SteamGridDB asset exceeds size limit")
    if mime == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n"):
        return data, ".png"
    if not logo and mime in {"image/jpeg", "image/jpg"} and data.startswith(b"\xff\xd8\xff"):
        return data, ".jpg"
    raise ValueError("SteamGridDB asset is not a supported static PNG/JPEG")


def fetch_steamgriddb_artwork(
    build: Path,
    *,
    game_name: str,
    progress=None,
    steam_appid: str | None = None,
    selected_game_id: int | None = None,
) -> tuple[dict[str, Path], dict | None]:
    """Fill only vacant artwork slots; return newly downloaded assets and provenance.

    Returns no assets without a configured environment key; all network errors
    are non-fatal. Incomplete artwork does not block game conversion.
    """
    root = Path(build)
    art = root / ".megcfbt" / "artwork"
    key = os.environ.get("STEAMGRIDDB_API_KEY", "").strip()
    if not key:
        _notify(progress, "SteamGridDB artwork disabled (STEAMGRIDDB_API_KEY not set)")
        return {}, None

    missing = [
        slot for slot in _ASSET_QUERIES
        if not any((art / (slot + suffix)).is_file() for suffix in _ASSET_SUFFIXES)
    ]
    if not missing:
        return {}, None

    _notify(progress, "SteamGridDB artwork enabled")
    try:
        matched = _resolve_game(
            game_name, key, steam_appid=steam_appid, selected_game_id=selected_game_id
        )
    except (OSError, ValueError, urllib.error.URLError) as exc:
        _notify(progress, f"SteamGridDB lookup skipped: {exc}")
        return {}, None
    if not matched or not isinstance(matched.get("id"), int) or not isinstance(matched.get("name"), str):
        _notify(progress, f"SteamGridDB found no reliable match for {game_name!r}")
        return {}, None

    game_id = matched["id"]
    if game_id <= 0:
        return {}, None
    matched_name = matched["name"]
    _notify(progress, f"SteamGridDB matched: {matched_name} (id {game_id})")
    nsfw_filter = os.environ.get("STEAMGRIDDB_NSFW", "false").casefold()
    if nsfw_filter not in {"false", "any"}:
        nsfw_filter = "false"
    new: dict[str, Path] = {}
    for slot in missing:
        kind, extra = _ASSET_QUERIES[slot]
        query = "types=static&mimes=image/png,image/jpeg&humor=false&epilepsy=false"
        query += "&nsfw=" + nsfw_filter + "&limit=50"
        if kind == "logos":
            query = query.replace("image/png,image/jpeg", "image/png")
        if extra:
            query += "&" + extra
        try:
            payload = _api_json(f"{kind}/game/{game_id}?{query}", key)
            selected = _select_asset(payload.get("data"))
            if selected is None:
                _notify(progress, f"SteamGridDB {slot}: no suitable artwork")
                continue
            image, extension = _asset_bytes(selected["url"], logo=(slot == "logo"))
            art.mkdir(parents=True, exist_ok=True)
            target = art / (slot + extension)
            # A manual file might have arrived since initial discovery.
            if any((art / (slot + suffix)).is_file() for suffix in _ASSET_SUFFIXES):
                continue
            target.write_bytes(image)
            new[slot] = target
            _notify(progress, f"Bundled SteamGridDB {slot} artwork for {matched_name}")
        except (OSError, ValueError, urllib.error.URLError) as exc:
            _notify(progress, f"SteamGridDB {slot} unavailable: {exc}")
    provenance = {"provider": "steamgriddb", "game_id": game_id, "matched_name": matched_name}
    return new, provenance
