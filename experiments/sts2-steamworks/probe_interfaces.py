#!/usr/bin/env python3
"""Initialize genuine Steam in this process and query versioned interface pointers."""

import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import sys


LIBRARY = Path("/run/media/steamos/SD512/sts2-arm64-proto/data_sts2_linuxbsd_arm64/libsteam_api64.so")
EXPECTED_SHA256 = "9d354c631f01f7318bc00e8fa29842b83678f4293b52d0d5c11806edd76a7f4b"
APP_ID = "2868840"
VERSIONS = {
    "AppsControl": "STEAMAPPS_INTERFACE_VERSION008",
    "GameSearch": "SteamMatchGameSearch001",
    "MusicRemote": "STEAMMUSICREMOTE_INTERFACE_VERSION001",
}


def query_interfaces(lib, report):
    init = lib.SteamInternal_SteamAPI_Init
    init.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_char)]
    init.restype = ctypes.c_int32
    shutdown = lib.SteamAPI_Shutdown
    shutdown.argtypes = []
    shutdown.restype = None
    get_user = lib.SteamAPI_GetHSteamUser
    get_user.argtypes = []
    get_user.restype = ctypes.c_int32
    get_pipe = lib.SteamAPI_GetHSteamPipe
    get_pipe.argtypes = []
    get_pipe.restype = ctypes.c_int32
    create_client = lib.SteamInternal_CreateInterface
    create_client.argtypes = [ctypes.c_char_p]
    create_client.restype = ctypes.c_void_p
    generic = lib.SteamAPI_ISteamClient_GetISteamGenericInterface
    generic.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.c_int32, ctypes.c_char_p]
    generic.restype = ctypes.c_void_p

    error_buffer = ctypes.create_string_buffer(1024)
    result = init(None, error_buffer)
    report["native_init_result"] = result
    report["native_init_error"] = error_buffer.value.decode("utf-8", errors="replace")
    if result != 0:
        return
    try:
        user = get_user()
        pipe = get_pipe()
        client = create_client(b"SteamClient021")
        report["hsteam_user"] = user
        report["hsteam_pipe"] = pipe
        report["steam_client_version"] = "SteamClient021"
        report["steam_client_pointer"] = hex(client or 0)
        if not user or not pipe or not client:
            report["errors"].append("Native init succeeded but a required user, pipe, or client handle is zero")
            return
        for label, version in VERSIONS.items():
            pointer = generic(client, user, pipe, version.encode("ascii"))
            report["interfaces"][label] = {
                "version": version,
                "nonzero": bool(pointer),
                "pointer": hex(pointer or 0),
            }
    finally:
        shutdown()
        report["shutdown_called"] = True


def main():
    report = {
        "probe_version": 1,
        "host_architecture": platform.machine(),
        "library": str(LIBRARY),
        "app_id": APP_ID,
        "interfaces": {},
        "errors": [],
        "shutdown_called": False,
        "scope": "Queries genuine interface pointers; does not test authentication, ownership, or game compatibility.",
    }
    saved_stdout = None
    try:
        if platform.machine().lower() not in {"aarch64", "arm64"}:
            raise ValueError("This probe requires the ARM64 Frame")
        digest = hashlib.sha256()
        with LIBRARY.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        report["library_sha256"] = digest.hexdigest()
        if digest.hexdigest() != EXPECTED_SHA256:
            raise ValueError("Library hash differs from the inspected Frame library; refusing to load it")
        os.environ["SteamAppId"] = APP_ID
        os.environ["SteamGameId"] = APP_ID
        os.chdir(LIBRARY.parent.parent)
        # Keep native Steam messages on stderr so stdout remains JSON.
        sys.stdout.flush()
        saved_stdout = os.dup(1)
        os.dup2(2, 1)
        lib = ctypes.CDLL(str(LIBRARY))
        query_interfaces(lib, report)
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
    report["all_requested_interfaces_available"] = (
        len(report["interfaces"]) == len(VERSIONS)
        and all(item["nonzero"] for item in report["interfaces"].values())
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["errors"] or report.get("native_init_result") != 0:
        return 2
    return 0 if report["all_requested_interfaces_available"] else 3


if __name__ == "__main__":
    sys.exit(main())
