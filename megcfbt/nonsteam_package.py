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
"""Add an extracted tovakai Steam Frame package as a normal non-Steam game."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
META = ROOT / ".megcfbt" / "package.json"
ART = ROOT / ".megcfbt" / "artwork"
ARTWORK = {
    "grid": "{}p{}",
    "wide": "{}{}",
    "hero": "{}_hero{}",
    "logo": "{}_logo{}",
    "icon": "{}_icon{}",
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


def parse_vdf(data: bytes, at: int = 0) -> tuple[dict, int]:
    """Parse the binary KeyValues subset used by Steam shortcuts.vdf."""
    node: dict = {}
    while True:
        kind = data[at]
        at += 1
        if kind == 0x08:
            return node, at
        end = data.index(b"\0", at)
        key = data[at:end].decode("utf-8", "replace")
        at = end + 1
        if kind == 0x00:
            node[key], at = parse_vdf(data, at)
        elif kind == 0x01:
            end = data.index(b"\0", at)
            node[key] = data[at:end].decode("utf-8", "replace")
            at = end + 1
        elif kind == 0x02:
            node[key] = struct.unpack_from("<I", data, at)[0]
            at += 4
        elif kind == 0x07:
            node[key] = struct.unpack_from("<Q", data, at)[0]
            at += 8
        else:
            raise ValueError(f"unsupported KeyValues type {kind:#x}")


def field(entry: dict, name: str):
    lowered = name.casefold()
    return next((value for key, value in entry.items() if key.casefold() == lowered), None)


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
            if user.name.isdigit() and user.is_dir():
                found.setdefault(user.resolve(), user)
    return list(found.values())


def shortcut_ids(vdf: Path, launcher: Path) -> list[int]:
    try:
        root, _ = parse_vdf(vdf.read_bytes())
        shortcuts = field(root, "shortcuts") or {}
    except (OSError, ValueError, IndexError, struct.error):
        return []
    target = str(launcher)
    output: list[int] = []
    for entry in shortcuts.values():
        if not isinstance(entry, dict):
            continue
        exe = str(field(entry, "exe") or "").strip('"')
        appid = field(entry, "appid")
        if exe == target and isinstance(appid, int):
            output.append(appid)
    return output


def find_shortcuts(launcher: Path) -> dict[Path, list[int]]:
    found: dict[Path, list[int]] = {}
    for user in steam_users():
        ids = shortcut_ids(user / "config/shortcuts.vdf", launcher)
        if ids:
            found[user] = ids
    return found


def steam_running() -> bool:
    try:
        return subprocess.run(
            ["pgrep", "-x", "steam"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode == 0
    except FileNotFoundError:
        return True


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
    icon = next((ART / f"icon{suffix}" for suffix in IMAGE_SUFFIXES if (ART / f"icon{suffix}").is_file()), None)
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


def artwork_source(slot: str) -> Path | None:
    for suffix in IMAGE_SUFFIXES:
        candidate = ART / f"{slot}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def apply_artwork(found: dict[Path, list[int]]) -> int:
    copied = 0
    for user, ids in found.items():
        grid = user / "config" / "grid"
        grid.mkdir(parents=True, exist_ok=True)
        for appid in ids:
            for slot, pattern in ARTWORK.items():
                source = artwork_source(slot)
                if source is None:
                    continue
                suffix = ".jpg" if source.suffix.lower() == ".jpeg" else source.suffix.lower()
                shutil.copyfile(source, grid / pattern.format(appid, suffix))
                copied += 1
    return copied


def main() -> int:
    if sys.platform != "linux":
        return fail("this installer is intended for the Steam Frame / Linux.")
    try:
        name, launcher = load_metadata()
    except RuntimeError as exc:
        return fail(str(exc))

    try:
        launcher.chmod(launcher.stat().st_mode | 0o755)
    except OSError:
        pass

    found = find_shortcuts(launcher)
    if found:
        copied = apply_artwork(found)
        print(f'Already in Steam as a non-Steam game: "{name}".')
        print(f"Artwork files refreshed: {copied}.")
        return 0

    if not steam_running():
        return fail("Steam is not running. Start Steam, then run ./install-to-steam.sh again.")

    entry = desktop_entry(name, launcher)
    print(f'Adding "{name}" to Steam as a normal non-Steam game...')
    try:
        request_add(entry)
    except RuntimeError as exc:
        return fail(str(exc))

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        time.sleep(0.5)
        found = find_shortcuts(launcher)
        if found:
            copied = apply_artwork(found)
            print(f'Added to Steam: "{name}".')
            print(f"Artwork files applied: {copied}.")
            print("You can now launch it from the Steam library.")
            return 0

    print("Steam did not confirm the shortcut within 30 seconds.", file=sys.stderr)
    print("Fallback: in Steam choose 'Add a Non-Steam Game', add launch.sh from this folder,", file=sys.stderr)
    print("then run ./install-to-steam.sh again to apply bundled artwork.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
'''

INSTALL_GUIDE = """Steam Frame package

1. Copy this extracted folder to your Steam Frame.
2. Make sure Steam is running.
3. Open a terminal in this folder.
4. Run:

   ./install-to-steam.sh

The installer adds launch.sh as a normal non-Steam game and copies any bundled
Steam artwork into the active Steam user's grid folder.

If Steam does not import the shortcut automatically, add launch.sh manually via
Steam's "Add a Non-Steam Game" flow, then run install-to-steam.sh again to apply
the artwork.
"""


def installer_files() -> dict[str, tuple[bytes, int]]:
    """Files injected at the root of each portable Steam Frame package."""
    return {
        "install-to-steam.sh": (INSTALLER_SHELL.encode("utf-8"), 0o755),
        ".megcfbt/install-to-steam.py": (INSTALLER_PYTHON.encode("utf-8"), 0o755),
        "INSTALL-ON-FRAME.txt": (INSTALL_GUIDE.encode("utf-8"), 0o644),
    }
