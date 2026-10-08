#!/usr/bin/env python3
"""Replay the patched wrapper's ordered native interface acquisitions."""

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import sys


DATA = Path("/run/media/steamos/SD512/sts2-arm64-proto/data_sts2_linuxbsd_arm64")
LIBRARY_HASH = "9d354c631f01f7318bc00e8fa29842b83678f4293b52d0d5c11806edd76a7f4b"
ASSEMBLY_HASH = "808393ad362ef694e506d6b722bf4357014b1f2cdb19256d0f467c89b9ac02de"
HTTP_ASSEMBLY_HASH = "c85f06c0aa27c8e498e4d4bd8c73ed818f810d2ba7e1565bb3c415230eb269af"
CLIENT_ASSEMBLY_HASH = "7dd9a985d68666096bdf8941497cc38e911561179998119a151373d9ea928db5"
STATS_ASSEMBLY_HASH = "e214b36dda06df40901cd5b0fb043045b7aa626475c0154f7ca421bb725fde14"
CLIENT_VERSIONS = ("SteamClient021", "SteamClient023")
# Order, version strings, and retrieval routes come from the supplied context IL.
REQUESTS = (
    ("User", "SteamUser023", "client"),
    ("Friends", "SteamFriends017", "client"),
    ("Utils", "SteamUtils010", "pipe"),
    ("Matchmaking", "SteamMatchMaking009", "client"),
    ("MatchmakingServers", "SteamMatchMakingServers002", "client"),
    ("UserStats", "STEAMUSERSTATS_INTERFACE_VERSION012", "client"),
    ("Apps", "STEAMAPPS_INTERFACE_VERSION008", "client"),
    ("Networking", "SteamNetworking006", "client"),
    ("RemoteStorage", "STEAMREMOTESTORAGE_INTERFACE_VERSION016", "client"),
    ("Screenshots", "STEAMSCREENSHOTS_INTERFACE_VERSION003", "client"),
    ("GameSearch", "SteamMatchGameSearch001", "generic"),
    ("HTTP", "STEAMHTTP_INTERFACE_VERSION003", "client"),
    ("UGC", "STEAMUGC_INTERFACE_VERSION020", "client"),
    ("Music", "STEAMMUSIC_INTERFACE_VERSION001", "client"),
    ("MusicRemote", "STEAMMUSICREMOTE_INTERFACE_VERSION001", "generic"),
    ("HTMLSurface", "STEAMHTMLSURFACE_INTERFACE_VERSION_005", "client"),
    ("Inventory", "STEAMINVENTORY_INTERFACE_V003", "client"),
    ("Video", "STEAMVIDEO_INTERFACE_V007", "client"),
    ("ParentalSettings", "STEAMPARENTALSETTINGS_INTERFACE_VERSION001", "client"),
    ("Input", "SteamInput006", "client"),
    ("Parties", "SteamParties002", "client"),
    ("RemotePlay", "STEAMREMOTEPLAY_INTERFACE_VERSION002", "client"),
    ("NetworkingUtils", "SteamNetworkingUtils004", "fallback"),
    ("NetworkingSockets", "SteamNetworkingSockets012", "user"),
    ("NetworkingMessages", "SteamNetworkingMessages002", "user"),
    ("Timeline", "STEAMTIMELINE_INTERFACE_V001", "user"),
)


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def query(lib, report, http_generic=False, client_version="SteamClient021"):
    if client_version not in CLIENT_VERSIONS:
        raise ValueError("Unsupported probe client version")
    report["steam_client_version"] = client_version
    report["client_version_override"] = client_version != report.get("installed_steam_client_version", "SteamClient021")
    pointer_type = ctypes.c_void_p
    integer_type = ctypes.c_int32
    text_type = ctypes.c_char_p

    def bind(name, result, *arguments):
        function = getattr(lib, name)
        function.restype = result
        function.argtypes = list(arguments)
        return function

    shutdown = bind("SteamAPI_Shutdown", None)
    init = bind("SteamInternal_SteamAPI_Init", integer_type, text_type, ctypes.POINTER(ctypes.c_char))
    error = ctypes.create_string_buffer(1024)
    result = init(None, error)
    report["native_init_result"] = result
    report["native_init_error"] = error.value.decode("utf-8", errors="replace")
    if result != 0:
        report["failure_stage"] = "native_initialization"
        return
    try:
        user = bind("SteamAPI_GetHSteamUser", integer_type)()
        pipe = bind("SteamAPI_GetHSteamPipe", integer_type)()
        report.update(hsteam_user=user, hsteam_pipe=pipe)
        if pipe == 0:
            report["failure_stage"] = "zero_steam_pipe"
            return
        client = bind("SteamInternal_CreateInterface", pointer_type, text_type)(client_version.encode("ascii"))
        report["steam_client_pointer"] = hex(client or 0)
        if not client:
            report["failure_stage"] = client_version
            return
        for label, version, route in REQUESTS:
            report["current_interface"] = label
            if label == "UserStats":
                version = report.get("user_stats_version", version)
            if label == "HTTP" and http_generic:
                route = "generic"
            encoded = version.encode("ascii")
            if route in {"client", "pipe", "generic"}:
                export = "SteamAPI_ISteamClient_GetISteam" + ("GenericInterface" if route == "generic" else label)
                if route == "pipe":
                    value = bind(export, pointer_type, pointer_type, integer_type, text_type)(client, pipe, encoded)
                else:
                    value = bind(export, pointer_type, pointer_type, integer_type, integer_type, text_type)(client, user, pipe, encoded)
            else:
                export = "SteamInternal_FindOrCreateUserInterface"
                getter = bind(export, pointer_type, integer_type, text_type)
                value = getter(user, encoded)
                if route == "fallback":
                    # Mirror the context's second user lookup or server fallback.
                    if value:
                        value = getter(user, encoded)
                    else:
                        export = "SteamInternal_FindOrCreateGameServerInterface"
                        value = bind(export, pointer_type, integer_type, text_type)(user, encoded)
            report["interfaces"].append({
                "name": label, "version": version, "export": export,
                "nonzero": bool(value), "pointer": hex(value or 0),
            })
            if not value:
                report["failure_stage"] = "context_interface"
                report["first_failed_interface"] = label
                return
        report["context_probe_passed"] = True
        report.pop("current_interface", None)
    finally:
        shutdown()
        report["shutdown_called"] = True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--http-generic", action="store_true", help="Probe the verified HTTP generic route without changing the DLL.")
    parser.add_argument("--client-version", choices=CLIENT_VERSIONS, help="Override the verified installed client version without changing the DLL.")
    args = parser.parse_args(argv)
    report = {
        "probe_version": 4, "host_architecture": platform.machine(),
        "steam_client_version": args.client_version or "SteamClient021",
        "client_version_override": False,
        "interfaces": [], "errors": [], "context_probe_passed": False,
        "shutdown_called": False, "failure_stage": None,
        "scope": "Separate-process native context replay; no DLL modifications or game authentication/ownership validation.",
    }
    saved_stdout = None
    try:
        if platform.machine().lower() not in {"aarch64", "arm64"}:
            raise ValueError("This probe requires the ARM64 Frame")
        report["library_sha256"] = file_hash(DATA / "libsteam_api64.so")
        report["assembly_sha256"] = file_hash(DATA / "Steamworks.NET.dll")
        if report["library_sha256"] != LIBRARY_HASH or report["assembly_sha256"] not in {ASSEMBLY_HASH, HTTP_ASSEMBLY_HASH, CLIENT_ASSEMBLY_HASH, STATS_ASSEMBLY_HASH}:
            raise ValueError("Library or wrapper hash differs from the inspected setup; stopping")
        installed_client = "SteamClient023" if report["assembly_sha256"] in {CLIENT_ASSEMBLY_HASH, STATS_ASSEMBLY_HASH} else "SteamClient021"
        report["installed_steam_client_version"] = installed_client
        report["user_stats_version"] = "STEAMUSERSTATS_INTERFACE_VERSION013" if report["assembly_sha256"] == STATS_ASSEMBLY_HASH else "STEAMUSERSTATS_INTERFACE_VERSION012"
        installed_http_redirect = report["assembly_sha256"] == HTTP_ASSEMBLY_HASH
        report["installed_http_generic_redirect"] = installed_http_redirect
        report["http_generic_override"] = args.http_generic and not installed_http_redirect
        os.environ["SteamAppId"] = "2868840"
        os.environ["SteamGameId"] = "2868840"
        os.chdir(DATA.parent)
        sys.stdout.flush()
        saved_stdout = os.dup(1)
        os.dup2(2, 1)
        query(ctypes.CDLL(str(DATA / "libsteam_api64.so")), report,
              http_generic=args.http_generic or installed_http_redirect,
              client_version=args.client_version or installed_client)
    except (OSError, ValueError, AttributeError) as error:
        report["errors"].append(str(error))
        report["failure_stage"] = "probe_error"
    finally:
        if saved_stdout is not None:
            fflush = ctypes.CDLL(None).fflush
            fflush.argtypes = [ctypes.c_void_p]
            fflush.restype = ctypes.c_int
            fflush(None)
            os.dup2(saved_stdout, 1)
            os.close(saved_stdout)
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["errors"] or report.get("native_init_result") != 0:
        return 2
    return 0 if report["context_probe_passed"] else 3


if __name__ == "__main__":
    sys.exit(main())
