import hashlib
from pathlib import Path
import tempfile
import unittest

import locate_stats_artifacts as locator


class StatsLocatorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.data = self.root / locator.DATA_NAME
        self.data.mkdir()
        (self.data / "Steamworks.NET.dll").write_bytes(b"RequestCurrentStats UserStatsReceived_t")
        (self.data / "libsteam_api64.so").write_bytes(b"native fixture")

    def test_streaming_markers_across_boundaries_and_exact_hash(self):
        path = self.data / "game.dll"
        content = b"MZ" + b"SteamStatsManager UserStatsReceived_t UserStatsStored_t"
        path.write_bytes(content)
        for size in (1, 7, 16, 1024):
            with self.subTest(chunk_size=size):
                item = locator.scan(path, size)
                self.assertEqual(item["sha256"], hashlib.sha256(content).hexdigest())
                self.assertEqual(item["identifier_hits"], ["SteamStatsManager", "UserStatsReceived_t", "UserStatsStored_t"])

    def test_transfer_selection_excludes_wrapper_and_backups(self):
        game = self.data / "game with spaces.dll"
        game.write_bytes(b"SteamStatsManager")
        (self.data / "unrelated.dll").write_bytes(b"unrelated")
        (self.data / "game.dll.before-patch").write_bytes(b"SteamStatsManager")
        before = {p: p.read_bytes() for p in self.data.iterdir()}
        result = locator.collect(self.root)
        self.assertEqual(result["errors"], [])
        self.assertTrue(result["game_assembly_candidates_found"])
        self.assertEqual(result["assemblies_scanned"], 3)
        requests = result["transfer_requests"]
        self.assertEqual([Path(item["path"]).name for item in requests], [game.name, "libsteam_api64.so"])
        self.assertIn("'steamos@FRAME_HOST:", requests[0]["scp_from_your_computer"])
        self.assertFalse(result["working_wrapper"]["matches_expected_hash"])
        self.assertEqual(before, {p: p.read_bytes() for p in self.data.iterdir()})

    def test_symbolic_link_file_is_not_followed(self):
        link = self.data / "link.dll"
        link.symlink_to(self.data / "Steamworks.NET.dll")
        with self.assertRaises(ValueError):
            locator.scan(link)
        result = locator.collect(self.root)
        self.assertEqual(len(result["errors"]), 1)

    def test_missing_root_and_absent_game_candidates_are_explicit(self):
        missing = locator.collect(self.root / "missing")
        self.assertTrue(missing["errors"])
        result = locator.collect(self.root)
        self.assertFalse(result["game_assembly_candidates_found"])
        self.assertEqual(len(result["transfer_requests"]), 1)


if __name__ == "__main__":
    unittest.main()
