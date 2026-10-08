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

The shortcut-ID and binary shortcuts.vdf approach is adapted from Deckport
(https://github.com/wesellis/deckport), Copyright (c) 2026 Wesley Ellis,
used under the MIT License. See THIRD_PARTY_NOTICES.md in the source repository.
"""

from __future__ import annotations

import glob
import json
import shutil
import struct
import sys
import zlib
from datetime import datetime
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


def _write_map(node: dict) -> bytes:
    output = bytearray()
    for key, value in node.items():
        encoded_key = str(key).encode("utf-8")
        if isinstance(value, dict):
            output += b"\x00" + encoded_key + b"\x00" + _write_map(value) + b"\x08"
        elif isinstance(value, bool):
            output += b"\x02" + encoded_key + b"\x00" + struct.pack("<i", int(value))
        elif isinstance(value, int):
            if -(1 << 31) <= value < (1 << 31):
                output += b"\x02" + encoded_key + b"\x00" + struct.pack("<i", value)
            elif 0 <= value < (1 << 64):
                output += b"\x07" + encoded_key + b"\x00" + struct.pack("<Q", value)
            else:
                raise ValueError(f"integer out of KeyValues range for {key!r}: {value}")
        else:
            output += (
                b"\x01"
                + encoded_key
                + b"\x00"
                + str(value).encode("utf-8")
                + b"\x00"
            )
    return bytes(output)


def save_shortcuts(path: Path, shortcuts: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00shortcuts\x00" + _write_map(shortcuts) + b"\x08\x08")


def shortcut_appid(exe: str, app_name: str) -> int:
    """Return Steam's deterministic unsigned non-Steam shortcut AppID."""
    return (zlib.crc32((exe + app_name).encode("utf-8")) & 0xFFFFFFFF) | 0x80000000


def to_signed32(value: int) -> int:
    return struct.unpack("<i", struct.pack("<I", value & 0xFFFFFFFF))[0]


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


def shortcuts_path() -> Path:
    roots = (
        Path.home() / ".steam/steam",
        Path.home() / ".local/share/Steam",
        Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
    )
    candidates: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        userdata = root / "userdata"
        if not userdata.is_dir():
            continue
        for user in userdata.iterdir():
            if not user.is_dir() or not user.name.isdigit() or user.name == "0":
                continue
            resolved = user.resolve()
            if resolved not in seen:
                seen.add(resolved)
                candidates.append(user)

    if not candidates:
        raise RuntimeError("could not locate a Steam userdata account")

    def activity(user: Path) -> float:
        vdf = user / "config" / "shortcuts.vdf"
        try:
            return vdf.stat().st_mtime
        except OSError:
            try:
                return user.stat().st_mtime
            except OSError:
                return 0.0

    user = max(candidates, key=activity)
    return user / "config" / "shortcuts.vdf"


def build_shortcut(name: str, launcher: Path) -> tuple[dict, int]:
    exe = f'"{launcher}"'
    start_dir = f'"{ROOT}/"'
    appid = shortcut_appid(exe, name)
    entry = {
        "appid": to_signed32(appid),
        "AppName": name,
        "Exe": exe,
        "StartDir": start_dir,
        "icon": "",
        "ShortcutPath": "",
        "LaunchOptions": "",
        "IsHidden": 0,
        "AllowDesktopConfig": 1,
        "AllowOverlay": 1,
        "openvr": 0,
        "Devkit": 0,
        "DevkitGameID": "",
        "DevkitOverrideAppID": 0,
        "LastPlayTime": 0,
        "FlatpakAppID": "",
        "tags": {"0": "Tovakai ARM64"},
    }
    return entry, appid


def existing_shortcut(shortcuts: dict, launcher: Path) -> tuple[str, dict] | None:
    target = str(launcher)
    for key, entry in shortcuts.items():
        if not isinstance(entry, dict):
            continue
        exe = str(entry.get("Exe") or entry.get("exe") or "").strip('"')
        if exe == target:
            return str(key), entry
    return None


def artwork_source(slot: str) -> Path | None:
    for suffix in IMAGE_SUFFIXES:
        candidate = ART / f"{slot}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def apply_artwork(vdf: Path, appid: int) -> int:
    grid = vdf.parent / "grid"
    grid.mkdir(parents=True, exist_ok=True)
    appid = to_unsigned32(appid)
    copied = 0
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
        vdf = shortcuts_path()
    except RuntimeError as exc:
        return fail(str(exc))

    try:
        launcher.chmod(launcher.stat().st_mode | 0o755)
    except OSError:
        pass

    if steam_running():
        return fail(
            "Steam is running. Fully exit Steam first, then run "
            "./install-to-steam.sh again. Steam keeps shortcuts.vdf in memory "
            "and can overwrite external changes."
        )

    try:
        shortcuts = load_shortcuts(vdf)
    except (OSError, ValueError, IndexError, struct.error) as exc:
        return fail(f"could not read {vdf}: {exc}")

    existing = existing_shortcut(shortcuts, launcher)
    wrote_shortcut = False
    if existing is None:
        entry, appid = build_shortcut(name, launcher)
        shortcuts[str(len(shortcuts))] = entry

        if vdf.exists():
            backup = vdf.with_name(
                vdf.name + ".bak." + datetime.now().strftime("%Y%m%d-%H%M%S")
            )
            try:
                shutil.copy2(vdf, backup)
            except OSError as exc:
                return fail(f"could not back up {vdf}: {exc}")
            print(f"Backup: {backup}")

        try:
            save_shortcuts(vdf, shortcuts)
        except (OSError, ValueError, struct.error) as exc:
            return fail(f"could not write {vdf}: {exc}")
        wrote_shortcut = True
    else:
        _key, entry = existing
        stored = entry.get("appid")
        if not isinstance(stored, int):
            return fail("existing Steam shortcut has no usable AppID")
        appid = to_unsigned32(stored)

    try:
        copied = apply_artwork(vdf, appid)
    except OSError as exc:
        return fail(f"shortcut was installed, but artwork could not be copied: {exc}")

    if wrote_shortcut:
        print(f'Added to Steam as a non-Steam game: "{name}".')
    else:
        print(f'Already in Steam as a non-Steam game: "{name}".')
    print(f"Non-Steam AppID: {appid}")
    print(f"Artwork files applied: {copied}.")
    print("Reopen Steam. The game should appear in your library.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

INSTALL_GUIDE = """Steam Frame package

1. Copy this extracted folder to your Steam Frame.
2. Fully exit Steam.
3. Open a terminal in this folder.
4. Run:

   ./install-to-steam.sh

The installer writes launch.sh as a normal non-Steam shortcut, computes the same
deterministic AppID Steam uses for that shortcut, and copies any bundled artwork
into the matching Steam grid filenames.

5. Reopen Steam.

The installer backs up shortcuts.vdf before changing it. Do not run it while
Steam is open because Steam keeps that file in memory and can overwrite changes.
"""


def installer_files() -> dict[str, tuple[bytes, int]]:
    """Files injected at the root of each portable Steam Frame package."""
    return {
        "install-to-steam.sh": (INSTALLER_SHELL.encode("utf-8"), 0o755),
        ".megcfbt/install-to-steam.py": (INSTALLER_PYTHON.encode("utf-8"), 0o755),
        "INSTALL-ON-FRAME.txt": (INSTALL_GUIDE.encode("utf-8"), 0o644),
    }
