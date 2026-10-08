#!/usr/bin/env python3
"""Inspect Steamworks ELF exports without loading libraries or launching STS2."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys


TARGET = "SteamAPI_ISteamClient_GetISteamGameSearch"
WATCHED = {
    TARGET,
    "SteamAPI_Init",
    "SteamAPI_InitFlat",
    "SteamAPI_InitEx",
    "SteamAPI_Shutdown",
    "SteamAPI_RunCallbacks",
    "SteamAPI_IsSteamRunning",
    "SteamAPI_GetHSteamUser",
    "SteamAPI_GetHSteamPipe",
    "SteamAPI_ISteamApps_BIsSubscribedApp",
    "SteamAPI_ISteamUser_GetAuthSessionTicket",
    "SteamAPI_ISteamClient_GetISteamMusicRemote",
    "SteamAPI_ISteamFriends_GetUserRestrictions",
    "SteamAPI_ISteamFriends_SetPersonaName",
    "SteamAPI_ISteamUserStats_RequestCurrentStats",
    "SteamInternal_SteamAPI_Init",
    "SteamInternal_CreateInterface",
    "SteamInternal_FindOrCreateUserInterface",
    "SteamInternal_FindOrCreateGameServerInterface",
    "SteamInternal_ContextInit",
    "SteamClient",
}


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_exports(output):
    """Only externally visible, defined dynamic symbols are exports."""
    exports = set()
    for line in output.splitlines():
        columns = line.split()
        if len(columns) < 8 or not columns[0].rstrip(":").isdigit():
            continue
        if columns[4] not in {"GLOBAL", "WEAK", "UNIQUE"}:
            continue
        if columns[5] not in {"DEFAULT", "PROTECTED"} or columns[6] == "UND":
            continue
        exports.add(columns[7].split("@", 1)[0])
    return exports


def inspect_library(path, readelf):
    result = {"path": str(path)}
    try:
        resolved = path.resolve(strict=True)
        result["resolved_path"] = str(resolved)
        with resolved.open("rb") as stream:
            if stream.read(4) != b"\x7fELF":
                raise ValueError("Not an ELF file")
        result["sha256"] = sha256_file(resolved)
        command = subprocess.run(
            [readelf, "--wide", "--file-header", "--dyn-syms", "--dynamic", str(resolved)],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=30,
            env={**os.environ, "LC_ALL": "C"},
        )
        if command.returncode:
            raise ValueError(command.stderr.strip() or "readelf failed")
        exports = parse_exports(command.stdout)
        result["elf_metadata"] = [
            line.strip()
            for line in command.stdout.splitlines()
            if line.strip().startswith(("Class:", "Data:", "Machine:", "Type:"))
            or any(tag in line for tag in ("(NEEDED)", "(SONAME)", "(RPATH)", "(RUNPATH)"))
        ]
        result["dynamic_export_count"] = len(exports)
        result["watched_exports"] = {name: name in exports for name in sorted(WATCHED)}
        result["game_search_exports"] = sorted(name for name in exports if "GameSearch" in name)
        result["steam_client_accessors"] = sorted(
            name for name in exports
            if name.startswith(("SteamAPI_SteamClient", "SteamAPI_ISteamClient_GetISteam"))
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        result["error"] = str(error)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game_dir", type=Path)
    parser.add_argument(
        "--library", action="append", default=[], type=Path,
        help="Inspect an additional library; repeat for multiple files.",
    )
    parser.add_argument("--pid", type=int, help="Also read Steam library mappings for this existing process.")
    args = parser.parse_args()
    report = {
        "diagnostic_version": 1,
        "host_architecture": platform.machine(),
        "game_dir": str(args.game_dir),
        "target_symbol": TARGET,
        "scope": "Static export inspection; does not prove Steam initialization or device compatibility.",
        "errors": [],
        "available_inspection_tools": {
            name: shutil.which(name) for name in ("readelf", "dotnet", "ilspycmd", "monodis")
        },
    }
    candidates = set(args.library)
    candidates.add(Path("/opt/steamvr/bin/linuxarm64/libsteam_api.so"))
    report["steam_named_assemblies"] = []
    report["launch_script_paths"] = []
    if not args.game_dir.is_dir():
        report["errors"].append("Game directory is missing or inaccessible")
    else:
        def walk_error(error):
            report["errors"].append(str(error))

        for directory, _, files in os.walk(args.game_dir, onerror=walk_error, followlinks=False):
            for name in sorted(files):
                path = Path(directory) / name
                lower = name.lower()
                if lower.startswith(("libsteam_api", "libsteamclient", "steamclient")) and ".so" in lower:
                    candidates.add(path)
                if lower.endswith(".dll") and "steam" in lower:
                    assembly = {"path": str(path)}
                    try:
                        assembly["sha256"] = sha256_file(path)
                    except OSError as error:
                        assembly["error"] = str(error)
                        report["errors"].append(str(error))
                    report["steam_named_assemblies"].append(assembly)
                if lower.endswith(".sh"):
                    report["launch_script_paths"].append(str(path))
    if args.pid is not None:
        report["process_steam_mappings"] = []
        try:
            for line in Path("/proc/{}/maps".format(args.pid)).read_text().splitlines():
                columns = line.split(maxsplit=5)
                if len(columns) != 6:
                    continue
                mapped = columns[5]
                if ".so" not in mapped or "steam" not in Path(mapped).name.lower():
                    continue
                report["process_steam_mappings"].append(mapped)
                if mapped.startswith("/") and not mapped.endswith(" (deleted)"):
                    candidates.add(Path(mapped))
            report["process_steam_mappings"] = sorted(set(report["process_steam_mappings"]))
        except OSError as error:
            report["errors"].append(str(error))
    readelf = shutil.which("readelf")
    if readelf is None:
        report["errors"].append("readelf is unavailable; no export conclusions can be drawn")
        report["libraries"] = []
    else:
        report["libraries"] = [inspect_library(path, readelf) for path in sorted(candidates)]
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if report["errors"] or any("error" in item for item in report["libraries"]) else 0


if __name__ == "__main__":
    sys.exit(main())
