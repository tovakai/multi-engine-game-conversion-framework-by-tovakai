"""Best-effort official Steam artwork acquisition for user-owned game packages.

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
_STEAM_ASSET_HOSTS = (
    "shared.akamai.steamstatic.com",
    "shared.fastly.steamstatic.com",
)

# Steam's official store assets mapped onto the generic artwork slots consumed
# by the Frame installer. Missing individual assets are harmless.
_STEAM_ARTWORK = {
    "grid": ("library_600x900.jpg", ".jpg"),
    "wide": ("header.jpg", ".jpg"),
    "hero": ("library_hero.jpg", ".jpg"),
    "logo": ("logo.png", ".png"),
}


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


def _valid_image(data: bytes, suffix: str) -> bool:
    if suffix == ".jpg":
        return data.startswith(b"\xff\xd8\xff")
    if suffix == ".png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    return False


def _expected_mime(suffix: str) -> set[str]:
    if suffix == ".jpg":
        return {"image/jpeg", "image/jpg"}
    if suffix == ".png":
        return {"image/png"}
    return set()


def _download_asset(appid: str, remote_name: str, suffix: str) -> bytes:
    last_error: Exception | None = None
    for host in _STEAM_ASSET_HOSTS:
        url = (
            f"https://{host}/store_item_assets/"
            f"steam/apps/{appid}/{remote_name}"
        )
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "tovakai-frame-converter/1.0"},
            )
            with urllib.request.urlopen(request, timeout=12) as response:
                mime = response.headers.get("Content-Type", "").split(";")[0].lower()
                if mime not in _expected_mime(suffix):
                    raise ValueError(f"unexpected content type {mime or 'unknown'}")
                data = response.read(_MAX_IMAGE_BYTES + 1)
            if len(data) > _MAX_IMAGE_BYTES:
                raise ValueError("Steam artwork exceeded 8 MiB limit")
            if not _valid_image(data, suffix):
                raise ValueError(f"download was not a valid {suffix.lstrip('.').upper()} image")
            return data
        except (OSError, urllib.error.URLError, ValueError) as exc:
            last_error = exc
    if last_error is None:
        raise ValueError("no Steam artwork hosts configured")
    raise last_error


def fetch_official_steam_artwork(
    build: Path,
    *,
    progress=None,
) -> dict[str, Path]:
    """Cache the available official Steam library artwork for a detected AppID.

    The lookup is best-effort per slot. One missing CDN asset must not prevent
    conversion or prevent other artwork from being bundled. Existing slot files
    are preserved, so a manually selected portrait remains authoritative while
    automatic hero/banner/logo assets can still be added alongside it.
    """
    root = Path(build)
    appid = detected_steam_appid(root)
    if not appid:
        return {}

    artwork_dir = root / ".megcfbt" / "artwork"
    found: dict[str, Path] = {}
    failures: list[str] = []

    for slot, (remote_name, suffix) in _STEAM_ARTWORK.items():
        existing = next(
            (
                artwork_dir / f"{slot}{candidate}"
                for candidate in (".png", ".jpg", ".jpeg")
                if (artwork_dir / f"{slot}{candidate}").is_file()
            ),
            None,
        )
        if existing is not None:
            found[slot] = existing
            continue

        target = artwork_dir / f"{slot}{suffix}"
        try:
            data = _download_asset(appid, remote_name, suffix)
        except (OSError, urllib.error.URLError, ValueError) as exc:
            failures.append(f"{slot}: {exc}")
            continue

        artwork_dir.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        found[slot] = target
        if progress:
            progress(f"Matched Steam {slot} artwork using AppID {appid}")

    if progress and failures:
        progress(
            f"Some Steam artwork was unavailable for AppID {appid}: "
            + "; ".join(failures)
        )
    return found


def fetch_official_steam_portrait(
    build: Path,
    *,
    progress=None,
) -> Path | None:
    """Cache only the official portrait artwork for a detected Steam AppID.

    This preserves the historical helper's narrow side effects. New conversion
    code should use :func:`fetch_official_steam_artwork` to fetch the complete
    portrait/banner/hero/logo set.
    """
    root = Path(build)
    appid = detected_steam_appid(root)
    if not appid:
        return None

    artwork_dir = root / ".megcfbt" / "artwork"
    for candidate in (".png", ".jpg", ".jpeg"):
        existing = artwork_dir / f"grid{candidate}"
        if existing.is_file():
            return existing

    target = artwork_dir / "grid.jpg"
    try:
        data = _download_asset(appid, "library_600x900.jpg", ".jpg")
    except (OSError, urllib.error.URLError, ValueError) as exc:
        if progress:
            progress(f"Steam portrait unavailable for AppID {appid}: {exc}")
        return None

    artwork_dir.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    if progress:
        progress(f"Matched Steam library portrait using AppID {appid}")
    return target


def complete_frame_artwork(
    build: Path,
    *,
    game_name: str,
    progress=None,
    steamgriddb_game_id: int | None = None,
) -> dict[str, Path]:
    """Fill Frame artwork via manual > official Steam > optional SteamGridDB.

    Existing artwork is always kept. Record per-slot provider provenance in
    package metadata, but never persist SteamGridDB credentials or requests.
    """
    from megcfbt.steamgriddb import fetch_steamgriddb_artwork

    root = Path(build)
    art_dir = root / ".megcfbt" / "artwork"
    slots = ("grid", "wide", "hero", "logo")
    suffixes = (".png", ".jpg", ".jpeg")

    def present() -> dict[str, Path]:
        return {
            slot: next(
                path for suffix in suffixes
                if (path := art_dir / (slot + suffix)).is_file()
            )
            for slot in slots
            if any((art_dir / (slot + suffix)).is_file() for suffix in suffixes)
        }

    manual = present()
    meta = root / ".megcfbt" / "package.json"
    stored_sources = {}
    if meta.is_file():
        try:
            stored = json.loads(meta.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                artwork_info = stored.get("artwork")
                if isinstance(artwork_info, dict) and isinstance(artwork_info.get("slots"), dict):
                    stored_sources = artwork_info["slots"]
        except (OSError, ValueError):
            pass
    sources = {
        slot: (
            stored_sources.get(slot)
            if stored_sources.get(slot) in {"manual", "official_steam", "steamgriddb"}
            else "manual"
        )
        for slot in manual
    }
    appid = detected_steam_appid(root)
    if appid:
        fetch_official_steam_artwork(root, progress=progress)
        for slot in set(present()) - set(manual):
            sources[slot] = "official_steam"
    elif progress:
        progress("Official Steam artwork unavailable: no embedded Steam AppID")

    sgdb_assets, sgdb_match = fetch_steamgriddb_artwork(
        root,
        game_name=game_name,
        steam_appid=appid,
        progress=progress,
        selected_game_id=steamgriddb_game_id,
    )
    sources.update({slot: "steamgriddb" for slot in sgdb_assets})

    art = present()
    if art:
        meta = root / ".megcfbt" / "package.json"
        if meta.is_file():
            try:
                payload = json.loads(meta.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    provenance: dict[str, object] = {"slots": sources}
                    if sgdb_assets and sgdb_match is not None:
                        provenance["steamgriddb"] = sgdb_match
                    if appid:
                        provenance["steam_appid"] = appid
                    payload["artwork"] = provenance
                    meta.write_text(
                        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
            except (OSError, ValueError) as exc:
                if progress:
                    progress(f"Could not save artwork provenance: {exc}")
        if progress:
            progress("Bundled artwork slots: " + ", ".join(sorted(art)))
    elif progress:
        progress("No game artwork available; conversion will proceed without artwork")
    return art
