import os
from pathlib import Path
import tempfile
import unittest

import steam_launch
from test_convert_sts2 import elf


class SteamLaunchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.steam = self.root / "Steam with spaces"
        self.output = self.root / "game output"
        self.output.mkdir()
        (self.output / "collect-startup.sh").write_text("#!/bin/sh\nexit 0\n")
        (self.output / "collect-startup.sh").chmod(0o755)
        self.runtime = self.steam / "steamapps/common/SteamLinuxRuntime_4/pressure-vessel-arm64/bin/pressure-vessel-unruntime"
        for relative in ("linuxarm64/steam-launch-wrapper", "steamrtarm64/reaper",
                         "steamapps/common/SteamLinuxRuntime_4/pressure-vessel-arm64/bin/pressure-vessel-wrap"):
            path = self.steam / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(elf(relative))
            path.chmod(0o755)
        self.runtime.write_text("#!/bin/sh\nexit 0\n")
        self.runtime.chmod(0o755)
        self.arguments = [str(self.steam / "linuxarm64/steam-launch-wrapper"),
                          "--oom-score-adjust", "900", "--", str(self.steam / "steamrtarm64/reaper"),
                          "SteamLaunch", "AppId=2868840", "--", "original-FEX", "original-game"]

    def test_preserves_real_wrapper_chain_and_does_not_assign_identity(self):
        environment = {"STEAM_COMPAT_APP_ID": "2868840", "DISPLAY": ":synthetic",
                       "PRESSURE_VESSEL_RUNTIME": "foreign-sysroot"}
        before = dict(environment)
        command, child = steam_launch.launch_plan(self.output, self.arguments, environment)
        self.assertEqual(command[:8], self.arguments[:8])
        self.assertEqual(command[8], str(self.runtime))
        self.assertEqual(command[-1], str(self.output / "collect-startup.sh"))
        self.assertNotIn("original-FEX", command)
        self.assertNotIn("original-game", command)
        self.assertEqual(child["STEAM_COMPAT_APP_ID"], environment["STEAM_COMPAT_APP_ID"])
        self.assertNotIn("SteamAppId", child)
        self.assertNotIn("SteamGameId", child)
        self.assertNotIn("PRESSURE_VESSEL_RUNTIME", child)
        self.assertEqual(environment, before)

    def test_ssh_without_steam_context_is_refused(self):
        with self.assertRaisesRegex(ValueError, "Steam did not supply"):
            steam_launch.launch_plan(self.output, self.arguments, {})

    def test_conflicting_game_and_foreign_architecture_wrapper_refused(self):
        arguments = list(self.arguments)
        arguments[6] = "AppId=another-game"
        with self.assertRaisesRegex(ValueError, "conflicting"):
            steam_launch.launch_plan(self.output, arguments, {"STEAM_COMPAT_APP_ID": "2868840"})
        (self.steam / "linuxarm64/steam-launch-wrapper").write_bytes(b"foreign executable")
        with self.assertRaisesRegex(ValueError, "native ARM64"):
            steam_launch.launch_plan(self.output, self.arguments, {"STEAM_COMPAT_APP_ID": "2868840"})

    def test_missing_collector_fails_before_exec(self):
        (self.output / "collect-startup.sh").unlink()
        with self.assertRaisesRegex(ValueError, "collector is missing"):
            steam_launch.launch_plan(self.output, self.arguments, {"STEAM_COMPAT_APP_ID": "2868840"})


if __name__ == "__main__":
    unittest.main()
