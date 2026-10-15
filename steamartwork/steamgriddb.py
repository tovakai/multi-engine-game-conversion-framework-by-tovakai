"""Explicit-ID SteamGridDB lookup; credentials stay in memory, never in files."""
from __future__ import annotations

import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

from steamartwork.backend import ArtworkError, MAX_FILE, read_image

API = "https://www.steamgriddb.com/api/v2"
QUERIES = {
    "portrait": ("grids", "600x900"),
    "wide": ("grids", "920x430"),
    "hero": ("heroes", None),
    "logo": ("logos", None),
}


def trusted_url(url):
    try:
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower()
        return (parts.scheme == "https" and parts.port in (None, 443)
                and not parts.username and not parts.password
                and (host == "steamgriddb.com" or host.endswith(".steamgriddb.com")))
    except (ValueError, TypeError):
        return False


class _Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not trusted_url(newurl):
            raise ArtworkError("SteamGridDB redirected outside its image service.")
        if req.has_header("Authorization") and urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(req.full_url).netloc:
            raise ArtworkError("SteamGridDB authentication redirect was refused.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def request_bytes(url: str, *, api_key: str | None = None, limit=MAX_FILE):
    if not trusted_url(url):
        raise ArtworkError("SteamGridDB returned an untrusted image address.")
    headers = {"User-Agent": "Steam-Artwork-Companion/1.0"}
    if api_key:
        if not url.startswith(API + "/"):
            raise ArtworkError("Authentication is only sent to the SteamGridDB API.")
        headers.update({"Authorization": "Bearer " + api_key, "Accept": "application/json"})
    try:
        opener = urllib.request.build_opener(_Redirect())
        with opener.open(urllib.request.Request(url, headers=headers), timeout=15) as response:
            data = response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        messages = {401: "API key was rejected.", 403: "Access was denied; check the API key.",
                    404: "Game or artwork was not found.", 429: "Rate limit reached; try again later."}
        raise ArtworkError("SteamGridDB: " + messages.get(exc.code, f"HTTP error {exc.code}.")) from None
    except (OSError, urllib.error.URLError):
        raise ArtworkError("Could not connect to SteamGridDB. Check your connection and try again.") from None
    if len(data) > limit:
        raise ArtworkError("SteamGridDB response exceeded the download size limit.")
    return data


def api_json(path, api_key):
    try:
        payload = json.loads(request_bytes(API + "/" + path, api_key=api_key, limit=1024 * 1024))
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, ArtworkError):
            raise
        raise ArtworkError("SteamGridDB returned invalid data.") from None
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ArtworkError("SteamGridDB lookup was unsuccessful.")
    return payload.get("data")


def fetch_artwork(api_key: str, game_id: str, directory: Path, *, slots=None):
    """Stage best-scored static images for review, never write Steam artwork here."""
    key = api_key.strip()
    if not key or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise ArtworkError("Enter a valid SteamGridDB API key.")
    if not game_id.isascii() or not game_id.isdecimal() or not 0 < int(game_id) <= 0xFFFFFFFF:
        raise ArtworkError("Enter a positive SteamGridDB game ID, not a Steam AppID.")
    wanted = list(QUERIES) if slots is None else list(slots)
    if set(wanted) - QUERIES.keys():
        raise ArtworkError("Unknown artwork type.")
    game = api_json(f"games/id/{int(game_id)}", key)
    if not isinstance(game, dict) or game.get("id") != int(game_id) or not isinstance(game.get("name"), str):
        raise ArtworkError("SteamGridDB did not return the requested game.")
    directory.mkdir(parents=True, exist_ok=True)
    images, warnings = {}, []
    for slot in wanted:
        kind, dimensions = QUERIES[slot]
        params = {"types": "static", "mimes": "image/png,image/jpeg", "nsfw": "false",
                  "humor": "false", "epilepsy": "false", "limit": "50"}
        if dimensions:
            params["dimensions"] = dimensions
        try:
            items = api_json(f"{kind}/game/{int(game_id)}?" + urllib.parse.urlencode(params), key)
            candidates = [item for item in items if isinstance(item, dict)
                          and trusted_url(item.get("url"))] if isinstance(items, list) else []
            candidates = [item for item in candidates if not
                          set(item.get("tags") or []) & {"humor", "epilepsy", "nsfw"}]
            def score(item):
                value = item.get("score", 0)
                return value if isinstance(value, (int, float)) else 0
            candidates.sort(key=score, reverse=True)
            if not candidates:
                warnings.append(f"{slot}: no suitable static image")
                continue
            # Try alternatives when a highly scored asset is unsupported or unavailable.
            for item in candidates[:3]:
                target = directory / f"{slot}.download"
                try:
                    target.write_bytes(request_bytes(item["url"]))
                    _, extension = read_image(target)
                    image = target.with_suffix(extension)
                    target.replace(image)
                    images[slot] = image
                    break
                except (OSError, ArtworkError):
                    target.unlink(missing_ok=True)
            else:
                warnings.append(f"{slot}: images could not be downloaded or decoded")
        except ArtworkError as exc:
            warnings.append(f"{slot}: {exc}")
    return game["name"], images, warnings
