"""Portable Steam Frame non-Steam installer bundled into generated packages."""

from __future__ import annotations

INSTALLER_SHELL = r'''#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$ROOT/.megcfbt/install-to-steam.py"

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is required to add this game to Steam." >&2
    exit 1
fi
if [[ ! -f "$PY" ]]; then
    echo "ERROR: bundled Steam installer is missing: $PY" >&2
    exit 1
fi

exec python3 "$PY"
'''

INSTALLER_PYTHON = r'''#!/usr/bin/env python3
"""Add an extracted tovakai Steam Frame package as a normal non-Steam game.

The deterministic shortcut-ID and artwork naming approach is adapted from
Deckport (https://github.com/wesellis/deckport), Copyright (c) 2026 Wesley
Ellis, used under the MIT License. See THIRD_PARTY_NOTICES.md in the source
repository.

Unlike Deckport, this installer does not write shortcuts.vdf directly. Steam
Frame's desktop session is part of the SteamVR environment, so fully exiting
Steam tears down the session. Instead we use SteamOS's live
steam://addnonsteamgame/ path, then read back the shortcut Steam created.
"""

from __future__ import annotations

import glob
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import time
import urllib.parse
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
META = ROOT / ".megcfbt" / "package.json"
ART = ROOT / ".megcfbt" / "artwork"
ARTWORK = {
    "grid": "p",
    "wide": "",
    "hero": "_hero",
    "logo": "_logo",
    "icon": "_icon",
}
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")


def fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def load_metadata() -> tuple[str, Path]:
    try:
        data = json.loads(META.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"could not read {META}: {exc}") from exc
    name = str(data.get("name") or ROOT.name).replace("\n", " ").replace("\r", " ").strip()
    launcher_raw = str(data.get("launcher") or "launch.sh").replace("\\", "/")
    launcher = (ROOT / launcher_raw).resolve()
    try:
        launcher.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise RuntimeError(f"unsafe launcher path in metadata: {launcher_raw}") from exc
    if not launcher.is_file():
        raise RuntimeError(f"launcher does not exist: {launcher}")
    return name or ROOT.name, launcher


def _read_cstr(data: bytes, at: int) -> tuple[str, int]:
    end = data.index(b"\0", at)
    return data[at:end].decode("utf-8", "replace"), end + 1


def _read_map(data: bytes, at: int) -> tuple[dict, int]:
    node: dict = {}
    while True:
        kind = data[at]
        at += 1
        if kind == 0x08:
            return node, at
        key, at = _read_cstr(data, at)
        if kind == 0x00:
            node[key], at = _read_map(data, at)
        elif kind == 0x01:
            node[key], at = _read_cstr(data, at)
        elif kind == 0x02:
            node[key] = struct.unpack_from("<i", data, at)[0]
            at += 4
        elif kind == 0x07:
            node[key] = struct.unpack_from("<Q", data, at)[0]
            at += 8
        else:
            raise ValueError(f"unsupported KeyValues type {kind:#x}")


def load_shortcuts(path: Path) -> dict:
    if not path.exists():
        return {}
    data = path.read_bytes()
    if not data:
        return {}
    if not data.startswith(b"\x00shortcuts\x00"):
        raise ValueError("shortcuts.vdf has an unexpected root")
    root, _ = _read_map(data, len(b"\x00shortcuts\x00"))
    return root


def shortcut_appid(exe: str, app_name: str) -> int:
    """Return Steam's deterministic unsigned non-Steam shortcut AppID."""
    return (zlib.crc32((exe + app_name).encode("utf-8")) & 0xFFFFFFFF) | 0x80000000


def to_unsigned32(value: int) -> int:
    return value & 0xFFFFFFFF


def steam_running() -> bool:
    for comm in glob.glob("/proc/[0-9]*/comm"):
        try:
            if Path(comm).read_text(encoding="utf-8", errors="replace").strip() == "steam":
                return True
        except OSError:
            continue
    return False


def steam_users() -> list[Path]:
    roots = (
        Path.home() / ".steam/steam",
        Path.home() / ".local/share/Steam",
        Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
    )
    found: dict[Path, Path] = {}
    for root in roots:
        userdata = root / "userdata"
        if not userdata.is_dir():
            continue
        for user in userdata.iterdir():
            if user.name.isdigit() and user.name != "0" and user.is_dir():
                found.setdefault(user.resolve(), user)
    return list(found.values())


def desktop_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def desktop_entry(name: str, launcher: Path) -> Path:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-").lower() or "game"
    digest = hashlib.sha256(str(launcher).encode("utf-8")).hexdigest()[:10]
    path = Path.home() / ".local/share/applications" / f"tovakai-{slug[:40]}-{digest}.desktop"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Name={desktop_escape(name)}",
        f'Exec="{desktop_escape(str(launcher))}"',
        f'Path={desktop_escape(str(ROOT))}',
        "Terminal=false",
        "Categories=Game;",
    ]
    icon = next(
        (ART / f"icon{suffix}" for suffix in IMAGE_SUFFIXES if (ART / f"icon{suffix}").is_file()),
        None,
    )
    if icon:
        lines.insert(5, f"Icon={desktop_escape(str(icon))}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o755)
    return path


def request_add(entry: Path) -> None:
    Path("/tmp/addnonsteamgamefile").touch()
    url = "steam://addnonsteamgame/" + urllib.parse.quote(str(entry), safe="")
    command = shutil.which("steam")
    if command:
        try:
            subprocess.run(
                [command, url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
                check=False,
            )
        except subprocess.TimeoutExpired:
            pass
        return

    opener = shutil.which("xdg-open")
    if opener:
        subprocess.Popen(
            [opener, url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    raise RuntimeError("could not find the Steam command or xdg-open")


def _entry_appid(entry: dict) -> int | None:
    value = entry.get("appid")
    return to_unsigned32(value) if isinstance(value, int) else None


def find_shortcuts(
    launcher: Path,
    *,
    name: str | None = None,
    desktop: Path | None = None,
) -> dict[Path, int]:
    target = str(launcher)
    desktop_target = str(desktop) if desktop is not None else None
    found: dict[Path, int] = {}

    for user in steam_users():
        vdf = user / "config" / "shortcuts.vdf"
        try:
            shortcuts = load_shortcuts(vdf)
        except (OSError, ValueError, IndexError, struct.error):
            continue

        for entry in shortcuts.values():
            if not isinstance(entry, dict):
                continue
            exe = str(entry.get("Exe") or entry.get("exe") or "").strip('"')
            app_name = str(entry.get("AppName") or entry.get("appname") or "")
            start_dir = str(entry.get("StartDir") or entry.get("startdir") or "").strip('"').rstrip("/")
            appid = _entry_appid(entry)
            if appid is None:
                continue
            if (
                exe == target
                or (desktop_target is not None and exe == desktop_target)
                or (name is not None and app_name == name and start_dir == str(ROOT).rstrip("/"))
            ):
                found[user] = appid
                break

    return found


def artwork_source(slot: str) -> Path | None:
    for suffix in IMAGE_SUFFIXES:
        candidate = ART / f"{slot}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def apply_artwork(found: dict[Path, int]) -> int:
    copied = 0
    for user, appid in found.items():
        grid = user / "config" / "grid"
        grid.mkdir(parents=True, exist_ok=True)
        for slot, suffix_tag in ARTWORK.items():
            source = artwork_source(slot)
            if source is None:
                continue

            destination_stem = f"{appid}{suffix_tag}"
            for stale in grid.glob(destination_stem + ".*"):
                try:
                    stale.unlink()
                except OSError:
                    pass

            suffix = ".jpg" if source.suffix.lower() == ".jpeg" else source.suffix.lower()
            shutil.copy2(source, grid / f"{destination_stem}{suffix}")
            copied += 1
    return copied


def main() -> int:
    if sys.platform != "linux":
        return fail("this installer is intended for the Steam Frame / Linux")

    try:
        name, launcher = load_metadata()
    except RuntimeError as exc:
        return fail(str(exc))

    try:
        launcher.chmod(launcher.stat().st_mode | 0o755)
    except OSError:
        pass

    found = find_shortcuts(launcher, name=name)
    if found:
        try:
            copied = apply_artwork(found)
        except OSError as exc:
            return fail(f"shortcut exists, but artwork could not be copied: {exc}")
        appids = sorted(set(found.values()))
        print(f'Already in Steam as a non-Steam game: "{name}".')
        print("Non-Steam AppID: " + ", ".join(str(value) for value in appids))
        print(f"Artwork files refreshed: {copied}.")
        if copied:
            print("Restart the Steam / SteamVR environment if artwork does not appear immediately.")
        return 0

    if not steam_running():
        return fail(
            "Steam is not running. On Steam Frame, leave Steam/SteamVR running "
            "and run ./install-to-steam.sh from the desktop session."
        )

    entry = desktop_entry(name, launcher)
    expected = shortcut_appid(f'"{launcher}"', name)
    print(f'Adding "{name}" to the running Steam client as a normal non-Steam game...')
    print(f"Expected deterministic AppID: {expected}")

    try:
        request_add(entry)
    except RuntimeError as exc:
        return fail(str(exc))

    deadline = time.monotonic() + 30
    found = {}
    while time.monotonic() < deadline:
        time.sleep(0.5)
        found = find_shortcuts(launcher, name=name, desktop=entry)
        if found:
            break

    if not found:
        return fail(
            "Steam did not confirm the new shortcut within 30 seconds. "
            "If Steam opened an Add Non-Steam Game prompt, complete it and run "
            "./install-to-steam.sh again."
        )

    try:
        copied = apply_artwork(found)
    except OSError as exc:
        return fail(f"shortcut was installed, but artwork could not be copied: {exc}")

    actual = sorted(set(found.values()))
    print(f'Added to Steam: "{name}".')
    print("Actual non-Steam AppID: " + ", ".join(str(value) for value in actual))
    if expected not in actual:
        print(
            "NOTE: Steam's imported shortcut AppID differs from the direct "
            "launcher hash; using Steam's actual AppID for artwork."
        )
    print(f"Artwork files applied: {copied}.")
    if copied:
        print("Restart the Steam / SteamVR environment if artwork does not appear immediately.")
    print("The game should now be available in the Steam library.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

INSTALL_GUIDE = """Steam Frame package

1. Copy this extracted folder to your Steam Frame.
2. Leave Steam / SteamVR running.
3. Open a terminal in this folder.
4. Run:

   ./install-to-steam.sh

The installer asks the running Steam client to import launch.sh as a normal
non-Steam game. It then reads back the shortcut Steam created and installs any
bundled portrait, banner, hero, logo, and icon artwork using that shortcut's
non-Steam AppID. Steam may require a Steam / SteamVR environment restart before
new custom artwork becomes visible.

The deterministic AppID calculation and artwork naming convention are adapted
from Deckport. The installer does not use Steam Devkit Game registration and
does not require shutting down the Steam Frame desktop session.
"""


def installer_files() -> dict[str, tuple[bytes, int]]:
    """Files injected at the root of each portable Steam Frame package."""
    return {
        "install-to-steam.sh": (INSTALLER_SHELL.encode("utf-8"), 0o755),
        ".megcfbt/install-to-steam.py": (INSTALLER_PYTHON.encode("utf-8"), 0o755),
        "INSTALL-ON-FRAME.txt": (INSTALL_GUIDE.encode("utf-8"), 0o644),
    }
