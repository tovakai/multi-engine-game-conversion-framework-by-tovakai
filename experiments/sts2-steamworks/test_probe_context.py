"""Call-recorder checks only; these tests never load the native Steam library."""

import io
import json
import unittest
from unittest.mock import patch

import probe_context as probe


class Function:
    def __init__(self, library, name):
        self.library = library
        self.name = name

    def __call__(self, *args):
        self.library.calls.append((self.name, args))
        if self.name == "SteamInternal_SteamAPI_Init":
            return self.library.init_result
        if self.name == "SteamAPI_Shutdown":
            return None
        if self.name == "SteamInternal_CreateInterface":
            return self.library.client_pointer
        if self.name in {"SteamAPI_GetHSteamUser", "SteamAPI_GetHSteamPipe"}:
            return 1
        if args[-1] == self.library.failed_version:
            return 0
        return 0x1000


class Library:
    def __init__(self, init_result=0, client_pointer=0x2000, failed_version=None):
        self.calls = []
        self.init_result = init_result
        self.client_pointer = client_pointer
        self.failed_version = failed_version

    def __getattr__(self, name):
        function = Function(self, name)
        setattr(self, name, function)
        return function


def report():
    return {"interfaces": [], "context_probe_passed": False, "shutdown_called": False}


class ContextProbeTests(unittest.TestCase):
    def test_client_layout_selection_and_dedicated_routes(self):
        for version in probe.CLIENT_VERSIONS:
            with self.subTest(version=version):
                library, result = Library(), report()
                probe.query(library, result, client_version=version)
                self.assertTrue(result["context_probe_passed"])
                self.assertTrue(result["shutdown_called"])
                self.assertEqual(result["steam_client_version"], version)
                self.assertEqual(result["client_version_override"], version != "SteamClient021")
                self.assertIn(("SteamInternal_CreateInterface", (version.encode("ascii"),)), library.calls)
                self.assertEqual([item["name"] for item in result["interfaces"]], [item[0] for item in probe.REQUESTS])
                for name in ("HTTP", "UGC"):
                    item = next(item for item in result["interfaces"] if item["name"] == name)
                    self.assertEqual(item["export"], "SteamAPI_ISteamClient_GetISteam" + name)
                generic = [args for name, args in library.calls if name == "SteamAPI_ISteamClient_GetISteamGenericInterface"]
                self.assertEqual(generic, [(0x2000, 1, 1, b"SteamMatchGameSearch001"), (0x2000, 1, 1, b"STEAMMUSICREMOTE_INTERFACE_VERSION001")])
                self.assertIn(("SteamAPI_ISteamClient_GetISteamUtils", (0x2000, 1, b"SteamUtils010")), library.calls)
                networking_utils = [args for name, args in library.calls if name == "SteamInternal_FindOrCreateUserInterface" and args[-1] == b"SteamNetworkingUtils004"]
                self.assertEqual(len(networking_utils), 2)
                self.assertEqual(library.calls[-1], ("SteamAPI_Shutdown", ()))

    def test_every_interface_null_guard_stops_and_shuts_down(self):
        for index, (name, version, _) in enumerate(probe.REQUESTS):
            with self.subTest(interface=name):
                library, result = Library(failed_version=version.encode("ascii")), report()
                probe.query(library, result, client_version="SteamClient023")
                self.assertFalse(result["context_probe_passed"])
                self.assertEqual(result["first_failed_interface"], name)
                self.assertEqual(len(result["interfaces"]), index + 1)
                self.assertTrue(result["shutdown_called"])
                self.assertEqual(library.calls[-1], ("SteamAPI_Shutdown", ()))

    def test_unavailable_client_stops_without_interface_calls(self):
        library, result = Library(client_pointer=0), report()
        probe.query(library, result, client_version="SteamClient023")
        self.assertEqual(result["failure_stage"], "SteamClient023")
        self.assertEqual(result["interfaces"], [])
        self.assertTrue(result["shutdown_called"])

    def test_native_init_failure_does_not_acquire_or_shutdown(self):
        library, result = Library(init_result=2), report()
        probe.query(library, result, client_version="SteamClient023")
        self.assertEqual(result["failure_stage"], "native_initialization")
        self.assertEqual(len(library.calls), 1)
        self.assertFalse(result["shutdown_called"])

    def test_unsupported_client_refused_before_initialization(self):
        library = Library()
        with self.assertRaises(ValueError):
            probe.query(library, report(), client_version="SteamClient999")
        self.assertEqual(library.calls, [])

    def test_main_uses_verified_installed_client_version_by_default(self):
        for assembly_hash, expected_version in (
            (probe.ASSEMBLY_HASH, "SteamClient021"),
            (probe.CLIENT_ASSEMBLY_HASH, "SteamClient023"),
            (probe.STATS_ASSEMBLY_HASH, "SteamClient023"),
        ):
            with self.subTest(version=expected_version):
                output = io.StringIO()
                library = Library()
                with patch.object(probe.platform, "machine", return_value="aarch64"), \
                     patch.object(probe, "file_hash", side_effect=[probe.LIBRARY_HASH, assembly_hash]), \
                     patch.object(probe.os, "chdir"), \
                     patch.object(probe.os, "dup", return_value=100), \
                     patch.object(probe.os, "dup2"), \
                     patch.object(probe.os, "close"), \
                     patch.dict(probe.os.environ), \
                     patch.object(probe.ctypes, "CDLL", return_value=library), \
                     patch.object(probe.sys, "stdout", output):
                    self.assertEqual(probe.main([]), 0)
                result = json.loads(output.getvalue())
                self.assertEqual(result["steam_client_version"], expected_version)
                self.assertEqual(result["installed_steam_client_version"], expected_version)
                self.assertFalse(result["client_version_override"])
                stats_version = b"STEAMUSERSTATS_INTERFACE_VERSION013" if assembly_hash == probe.STATS_ASSEMBLY_HASH else b"STEAMUSERSTATS_INTERFACE_VERSION012"
                self.assertIn(("SteamAPI_ISteamClient_GetISteamUserStats", (0x2000, 1, 1, stats_version)), library.calls)
                self.assertIn(("SteamInternal_CreateInterface", (expected_version.encode("ascii"),)), library.calls)


if __name__ == "__main__":
    unittest.main()
