#!/usr/bin/env python3
"""Compare genuine retrieval routes for exact HTTP or UGC interface versions."""

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys


DATA = Path("/run/media/steamos/SD512/sts2-arm64-proto/data_sts2_linuxbsd_arm64")
LIBRARY_HASH = "9d354c631f01f7318bc00e8fa29842b83678f4293b52d0d5c11806edd76a7f4b"
ASSEMBLY_HASH = "808393ad362ef694e506d6b722bf4357014b1f2cdb19256d0f467c89b9ac02de"
VERSION = "STEAMHTTP_INTERFACE_VERSION003"
VERSIONS = {"HTTP": VERSION, "UGC": "STEAMUGC_INTERFACE_VERSION020"}


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def collect_disassembly(library, report):
    report["native_steamclient_version_strings"] = sorted({
        value.decode("ascii")
        for value in re.findall(rb"SteamClient[0-9]{3}(?=\x00)", library.read_bytes())
    })
    objdump = shutil.which("objdump")
    report["objdump"] = objdump
    report["accessor_disassembly"] = {}
    if objdump is None:
        report["disassembly_error"] = "objdump is unavailable"
        return
    for export in (
        "SteamAPI_ISteamClient_GetISteamGenericInterface",
        "SteamAPI_ISteamClient_GetISteamHTTP",
        "SteamAPI_ISteamClient_GetISteamUGC",
    ):
        try:
            result = subprocess.run(
                [objdump, "-d", "--disassemble=" + export, str(library)],
                capture_output=True, text=True, errors="replace", timeout=15,
                env={**os.environ, "LC_ALL": "C"},
            )
            lines = result.stdout.splitlines()
            report["accessor_disassembly"][export] = {
                "exit_code": result.returncode, "stderr": result.stderr,
                "lines": lines[:100], "truncated": len(lines) > 100,
                "symbol_label_found": any("<" + export in line for line in lines),
            }
        except (OSError, subprocess.TimeoutExpired) as error:
            report["accessor_disassembly"][export] = {"error": str(error)}


def query(lib, report, interface="HTTP"):
    version = VERSIONS[interface].encode("ascii")
    pointer, integer, text = ctypes.c_void_p, ctypes.c_int32, ctypes.c_char_p

    def bind(name, result, *arguments):
        function = getattr(lib, name)
        function.restype = result
        function.argtypes = list(arguments)
        return function

    shutdown = bind("SteamAPI_Shutdown", None)
    init = bind("SteamInternal_SteamAPI_Init", integer, text, ctypes.POINTER(ctypes.c_char))
    error = ctypes.create_string_buffer(1024)
    result = init(None, error)
    report["native_init_result"] = result
    report["native_init_error"] = error.value.decode("utf-8", errors="replace")
    if result != 0:
        return
    try:
        user = bind("SteamAPI_GetHSteamUser", integer)()
        pipe = bind("SteamAPI_GetHSteamPipe", integer)()
        client = bind("SteamInternal_CreateInterface", pointer, text)(b"SteamClient021")
        report.update(hsteam_user=user, hsteam_pipe=pipe, steam_client_pointer=hex(client or 0))
        if not user or not pipe or not client:
            raise ValueError("Required Steam user, pipe, or client handle is zero")
        for export in (
            "SteamAPI_ISteamClient_GetISteam" + interface,
            "SteamAPI_ISteamClient_GetISteamGenericInterface",
            "SteamInternal_FindOrCreateUserInterface",
        ):
            report["current_export"] = export
            if export == "SteamInternal_FindOrCreateUserInterface":
                value = bind(export, pointer, integer, text)(user, version)
            else:
                value = bind(export, pointer, pointer, integer, integer, text)(client, user, pipe, version)
            report["routes"].append({"export": export, "nonzero": bool(value), "pointer": hex(value or 0)})
        report.pop("current_export", None)
    finally:
        shutdown()
        report["shutdown_called"] = True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interface", choices=VERSIONS, default="HTTP")
    parser.add_argument("--disassemble", action="store_true")
    args = parser.parse_args(argv)
    report = {
        "probe_version": 2, "host_architecture": platform.machine(),
        "interface": args.interface, "interface_version": VERSIONS[args.interface],
        "routes": [], "errors": [],
        "shutdown_called": False,
        "scope": "Genuine interface acquisition and optional static disassembly; no interface operations, DLL changes, or authentication/ownership validation.",
    }
    saved_stdout = None
    try:
        if platform.machine().lower() not in {"aarch64", "arm64"}:
            raise ValueError("This probe requires the ARM64 Frame")
        report["library_sha256"] = file_hash(DATA / "libsteam_api64.so")
        report["assembly_sha256"] = file_hash(DATA / "Steamworks.NET.dll")
        if report["library_sha256"] != LIBRARY_HASH or report["assembly_sha256"] != ASSEMBLY_HASH:
            raise ValueError("Library or wrapper hash differs from the inspected setup; stopping")
        if args.disassemble:
            collect_disassembly(DATA / "libsteam_api64.so", report)
        os.environ["SteamAppId"] = "2868840"
        os.environ["SteamGameId"] = "2868840"
        os.chdir(DATA.parent)
        sys.stdout.flush()
        saved_stdout = os.dup(1)
        os.dup2(2, 1)
        query(ctypes.CDLL(str(DATA / "libsteam_api64.so")), report, args.interface)
    except (OSError, ValueError, AttributeError) as error:
        report["errors"].append(str(error))
    finally:
        if saved_stdout is not None:
            fflush = ctypes.CDLL(None).fflush
            fflush.argtypes = [ctypes.c_void_p]
            fflush.restype = ctypes.c_int
            fflush(None)
            os.dup2(saved_stdout, 1)
            os.close(saved_stdout)
    report["interface_available_via_any_route"] = any(route["nonzero"] for route in report["routes"])
    if args.interface == "HTTP":
        report["http_version"] = VERSION
        report["http_available_via_any_route"] = report["interface_available_via_any_route"]
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["errors"] or report.get("native_init_result") != 0:
        return 2
    return 0 if report["interface_available_via_any_route"] else 3


if __name__ == "__main__":
    sys.exit(main())
