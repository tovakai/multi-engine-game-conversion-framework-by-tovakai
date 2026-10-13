"""Discover installed Steam games and converted Frame packages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re

from framebench import STARDEW_APPID

APPID_RE = re.compile(r'"appid"\s+"(\d+)"', re.I)
INSTALLDIR_RE = re.compile(r'"installdir"\s+"([^"]+)"', re.I)
NAME_RE = re.compile(r'"name"\s+"([^"]+)"', re.I)


@dataclass(frozen=True)
class CatalogEntry:
    appid: int
    name: str
    steam_install: Path | None
    package: Path | None
    launcher: str | None

    def as_dict(self) -> dict:
        return {
            "appid": self.appid,
            "name": self.name,
            "steam_install": None if self.steam_install is None else str(self.steam_install),
            "package": None if self.package is None else str(self.package),
            "launcher": self.launcher,
        }


def steam_root(home: Path | None = None) -> Path:
    base = Path.home() if home is None else Path(home)
    for candidate in (base / ".steam" / "steam", base / ".local" / "share" / "Steam"):
        if candidate.is_dir():
            return candidate
    return base / ".steam" / "steam"


def library_folders(root: Path) -> list[Path]:
    folders = [root]
    text = _read(root / "steamapps" / "libraryfolders.vdf")
    if not text:
        return folders
    for match in re.finditer(r'"path"\s+"([^"]+)"', text):
        path = Path(match.group(1).replace("\\\\", "\\"))
        if path not in folders:
            folders.append(path)
    return folders


def installed_apps(root: Path) -> list[CatalogEntry]:
    entries: list[CatalogEntry] = []
    for library in library_folders(root):
        apps = library / "steamapps"
        if not apps.is_dir():
            continue
        for manifest in apps.glob("appmanifest_*.acf"):
            text = _read(manifest)
            if not text:
                continue
            appid = APPID_RE.search(text)
            installdir = INSTALLDIR_RE.search(text)
            name = NAME_RE.search(text)
            if not appid:
                continue
            steam_install = None
            if installdir:
                candidate = apps / "common" / installdir.group(1)
                if candidate.is_dir():
                    steam_install = candidate
            entries.append(
                CatalogEntry(
                    appid=int(appid.group(1)),
                    name=name.group(1) if name else f"App {appid.group(1)}",
                    steam_install=steam_install,
                    package=None,
                    launcher=None,
                )
            )
    return entries


def find_package(appid: int, *, search_roots: list[Path] | None = None, home: Path | None = None) -> Path | None:
    roots = list(search_roots or [])
    base = Path.home() if home is None else Path(home)
    roots.extend(
        [
            base / "devkit-game",
            base / "Applications",
            base / "Desktop",
        ]
    )
    for root in roots:
        if not root.is_dir():
            continue
        for candidate in [root, *root.iterdir()] if root.is_dir() else []:
            if not candidate.is_dir():
                continue
            if _package_appid(candidate) == appid:
                return candidate
            nested = candidate / "game"
            if nested.is_dir() and _package_appid(candidate) == appid:
                return candidate
    return None


def _package_appid(root: Path) -> int | None:
    for path in (
        root / "steam_appid.txt",
        root / "game" / "steam_appid.txt",
        root / ".megcfbt" / "package.json",
    ):
        if not path.is_file():
            continue
        if path.suffix == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for key in ("steam_app_id", "app_id", "appid"):
                value = data.get(key)
                if value:
                    try:
                        return int(value)
                    except (TypeError, ValueError):
                        continue
            conversion = data.get("conversion") if isinstance(data.get("conversion"), dict) else {}
            value = conversion.get("steam_app_id")
            if value:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    continue
        else:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            if text.isdigit():
                return int(text)
    if (root / "MONOFRAME-PROFILE.json").is_file() or (root / "game" / "MONOFRAME-PROFILE.json").is_file():
        return STARDEW_APPID
    return None


def discover(*, home: Path | None = None, extra_packages: list[Path] | None = None) -> list[CatalogEntry]:
    root = steam_root(home)
    games = {entry.appid: entry for entry in installed_apps(root)}
    for package in extra_packages or []:
        appid = _package_appid(Path(package))
        if appid is None:
            continue
        current = games.get(appid)
        launcher = _launcher(Path(package))
        games[appid] = CatalogEntry(
            appid=appid,
            name=current.name if current else Path(package).name,
            steam_install=current.steam_install if current else None,
            package=Path(package),
            launcher=launcher,
        )
    for appid, entry in list(games.items()):
        if entry.package is None:
            package = find_package(appid, home=home)
            if package is not None:
                games[appid] = CatalogEntry(
                    appid=entry.appid,
                    name=entry.name,
                    steam_install=entry.steam_install,
                    package=package,
                    launcher=_launcher(package),
                )
    return sorted(games.values(), key=lambda item: (item.name.casefold(), item.appid))


def benchmarkable(entries: list[CatalogEntry]) -> list[CatalogEntry]:
    return [entry for entry in entries if entry.package is not None]


def _launcher(package: Path) -> str | None:
    for name in ("launch.sh", "launch-steam.sh"):
        if (package / name).is_file():
            return name
    metadata = package / ".megcfbt" / "package.json"
    if metadata.is_file():
        try:
            data = json.loads(metadata.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        value = data.get("launcher")
        return str(value) if value else None
    return None


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
