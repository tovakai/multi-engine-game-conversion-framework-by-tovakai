#!/usr/bin/env python3
"""Preserve Steam's Frame launch chain and use Valve's native host runtime.

Receives the genuine expanded %command% from the existing game entry. Never sets
SteamAppId/SteamGameId, creates an appid file, or substitutes authentication.
"""

import json
import os
from pathlib import Path
import sys
import datetime

APPID = "2868840"
RUNTIME_KEYS = ("PRESSURE_VESSEL_RUNTIME", "PRESSURE_VESSEL_RUNTIME_ARCHIVE",
                "PRESSURE_VESSEL_RUNTIME_BASE", "PRESSURE_VESSEL_PREFIX")


def arm64_program(path):
    with path.open("rb") as stream:
        header = stream.read(20)
    if header[:6] != b"\x7fELF\x02\x01" or header[18:20] != b"\xb7\0" or not os.access(path, os.X_OK):
        raise ValueError("Expected installed native ARM64 Steam program: " + str(path))


def launch_plan(root, arguments, environment):
    args = list(arguments)
    if environment.get("STEAM_COMPAT_APP_ID") != APPID and environment.get("SteamAppId") != APPID:
        raise ValueError("Steam did not supply STS2 launch context. Run this through the game's Steam launch options with %command%.")
    if not args or not Path(args[0]).is_absolute():
        raise ValueError("Missing the expanded Steam %command%")
    wrapper = Path(args[0]).resolve(strict=True)
    steam = wrapper.parents[1]
    if wrapper != steam / "linuxarm64/steam-launch-wrapper":
        raise ValueError("Unsupported Steam wrapper; expected the Frame's linuxarm64 launch chain")
    separator = args.index("--")
    options = args[1:separator]
    if options and (len(options) != 2 or options[0] != "--oom-score-adjust" or not options[1].isdigit()):
        raise ValueError("Unsupported Steam wrapper options")
    tail = args[separator + 1:]
    if len(tail) < 5 or tail[1:4] != ["SteamLaunch", "AppId=" + APPID, "--"]:
        raise ValueError("Unsupported or conflicting Steam reaper command")
    reaper = Path(tail[0]).resolve(strict=True)
    if reaper != steam / "steamrtarm64/reaper":
        raise ValueError("Unsupported Steam reaper")
    runtime = steam / "steamapps/common/SteamLinuxRuntime_4/pressure-vessel-arm64/bin/pressure-vessel-unruntime"
    for program in (wrapper, reaper, runtime.with_name("pressure-vessel-wrap")):
        arm64_program(program)
    if not runtime.is_file() or not os.access(runtime, os.X_OK):
        raise ValueError("Installed Valve ARM64 host-runtime launcher is missing")
    collector = root / "collect-startup.sh"
    if not collector.is_file() or not os.access(collector, os.X_OK):
        raise ValueError("Conversion collector is missing or not executable")
    # Preserve the actual Steam wrapper/reaper arguments. Only replace the
    # foreign-architecture compatibility layer and original executable suffix.
    prefix = args[:separator + 5]
    command = [*prefix, str(runtime), "--no-copy-runtime", "--no-gc-runtimes",
               "--no-systemd-scope", "--batch", "--terminal=none", "--", str(collector)]
    child_environment = dict(environment)
    for key in RUNTIME_KEYS:
        child_environment.pop(key, None)
    return command, child_environment


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    dry_run = bool(args and args[0] == "--dry-run")
    if dry_run:
        args.pop(0)
    isolated = bool(args and args[0] == "--isolated-user-data")
    if isolated:
        args.pop(0)
    root = Path(__file__).resolve().parent
    if not dry_run:
        diagnostics = root / "diagnostics"
        diagnostics.mkdir(mode=0o700, exist_ok=True)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-dispatch-" + str(os.getpid())
        fd = os.open(diagnostics / (stamp + ".log"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.dup2(fd, 1)
        os.dup2(fd, 2)
        os.close(fd)
        context = {"stage": "steam-dispatch", "steam_environment": {key: os.environ.get(key) for key in
                   ("SteamAppId", "SteamGameId", "STEAM_COMPAT_APP_ID")},
                   "display_environment": {key: bool(os.environ.get(key)) for key in ("DISPLAY", "WAYLAND_DISPLAY")},
                   "isolated_user_data": isolated}
        (diagnostics / (stamp + ".json")).write_text(json.dumps(context, indent=2) + "\n")
    try:
        command, environment = launch_plan(root, args, os.environ)
        if isolated:
            for key, name in (("XDG_DATA_HOME", "data"), ("XDG_CONFIG_HOME", "config"), ("XDG_CACHE_HOME", "cache")):
                environment[key] = str(root / "diagnostics/test-userdata" / name)
            saves = Path.home() / ".local/share/SlayTheSpire2"
            if saves.is_dir():
                command[-2:-2] = ["--filesystem=" + str(saves) + ":ro"]
        if dry_run:
            print(json.dumps({"command": command, "sets_steam_identity": False}, indent=2))
            return 0
        print("Starting installed native Steam wrapper and Valve host runtime", flush=True)
        os.chdir(root)
        os.execvpe(command[0], command, environment)
    except (OSError, ValueError, IndexError) as error:
        print("STS2 Steam launch refused: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
