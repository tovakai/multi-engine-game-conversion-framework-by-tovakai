#!/usr/bin/env python3
"""Dual-mode Steam launch wrapper (stdlib only).

Native: start the converted package while preserving Steam AppID/environment
and, when the Frame launch chain is recognized, steam-launch-wrapper + reaper.
Original: forward the expanded Steam %command% unchanged, including FEX/Proton.

This file is copied into FrameBench state so Steam can invoke it without the
converter checkout remaining on PYTHONPATH.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

KIND = "framebench-dual-mode-v1"


def mode_file(appid: str, environ=None) -> Path:
    env = os.environ if environ is None else environ
    if explicit := env.get("FRAMEBENCH_MODE_FILE"):
        return Path(explicit)
    if state := env.get("FRAMEBENCH_STATE"):
        return Path(state) / "mode" / f"{appid}.mode"
    xdg = env.get("XDG_STATE_HOME")
    root = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return root / "framebench" / "mode" / f"{appid}.mode"


def read_mode(appid: str, environ=None, default: str = "native") -> str:
    env = os.environ if environ is None else environ
    if env.get("FRAMEBENCH_MODE") in {"native", "original"}:
        return env["FRAMEBENCH_MODE"]
    path = mode_file(appid, env)
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return default
    return value if value in {"native", "original"} else default


def write_mode(appid: int | str, mode: str, environ=None) -> Path:
    if mode not in {"native", "original"}:
        raise ValueError(f"Unsupported FrameBench mode: {mode}")
    path = mode_file(str(int(appid)), environ)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(mode + "\n", encoding="utf-8")
    return path


def parse_steam_chain(arguments: list[str], appid: str) -> dict | None:
    if not arguments:
        return None
    wrapper = Path(arguments[0])
    # Steam on Frame always expands %command% to an absolute Unix path.
    # Accept '/' prefixes so Windows hosts can still unit-test the chain.
    if not (wrapper.is_absolute() or arguments[0].startswith("/")):
        return None
    if wrapper.name != "steam-launch-wrapper":
        return None
    try:
        separator = arguments.index("--")
    except ValueError:
        return None
    tail = arguments[separator + 1:]
    if len(tail) < 4 or tail[1] != "SteamLaunch" or tail[2] != "AppId=" + appid or tail[3] != "--":
        return None
    return {
        "prefix": arguments[: separator + 5],
        "wrapper": str(wrapper),
        "reaper": tail[0],
        "suffix": tail[4:],
    }


def native_command(package: Path, arguments: list[str], appid: str) -> list[str]:
    launcher = _native_launcher(package)
    chain = parse_steam_chain(arguments, appid)
    if chain:
        return [*chain["prefix"], str(launcher)]
    return [str(launcher)]


def original_command(arguments: list[str]) -> list[str]:
    if not arguments:
        raise ValueError("Steam did not expand %command%; refusing original-mode launch")
    return list(arguments)


def _native_launcher(package: Path) -> Path:
    for name in ("launch.sh", "launch-steam.sh"):
        candidate = package / name
        if candidate.is_file():
            return candidate
    metadata = package / ".megcfbt" / "package.json"
    if metadata.is_file():
        data = json.loads(metadata.read_text(encoding="utf-8"))
        launcher = package / str(data.get("launcher") or "")
        if launcher.is_file():
            return launcher
    raise ValueError(f"Converted package has no launch.sh: {package}")


def plan(argv: list[str], environ=None) -> dict:
    env = dict(os.environ if environ is None else environ)
    args = list(argv)
    package = None
    appid = env.get("SteamAppId") or env.get("STEAM_COMPAT_APP_ID") or env.get("SteamGameId")
    default_mode = "native"
    while args:
        if args[0] == "--":
            args = args[1:]
            break
        if args[0] == "--package" and len(args) > 1:
            package = Path(args[1])
            args = args[2:]
            continue
        if args[0] == "--appid" and len(args) > 1:
            appid = args[1]
            args = args[2:]
            continue
        if args[0] == "--default-mode" and len(args) > 1:
            default_mode = args[1]
            args = args[2:]
            continue
        break
    if not appid:
        raise ValueError("Steam AppID missing; launch through the real Steam entry")
    if package is None:
        raise ValueError("Converted package path is required")
    mode = read_mode(str(appid), env, default=default_mode)
    if mode == "original":
        command = original_command(args)
    else:
        command = native_command(package, args, str(appid))
    return {
        "kind": KIND,
        "mode": mode,
        "appid": str(appid),
        "package": str(package),
        "command": command,
        "sets_steam_identity": False,
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    dry = bool(args and args[0] == "--dry-run")
    if dry:
        args = args[1:]
    try:
        result = plan(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("FrameBench launch refused: " + str(error), file=sys.stderr)
        return 2
    if dry:
        print(json.dumps(result, indent=2))
        return 0
    os.execvpe(result["command"][0], result["command"], os.environ)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
