import json
import os
from pathlib import Path
import struct
import unittest
from unittest import mock

import compare_inventories
import patch_accessors
import patch_stats
import prepare_managed


class ManagedGuardTests(unittest.TestCase):
    def test_matching_build_metadata_is_bound_to_its_inventory(self):
        root = Path(__file__).parent
        observation = json.loads((root / "matching_build_release_observation_v1.json").read_bytes())
        source = json.loads((root / "matching_build_inventory_v2.json").read_bytes())
        prototype = json.loads((root / "prototype_inventory_v1.json").read_bytes())
        self.assertEqual(observation["errors"], [])
        self.assertEqual(observation["sha256"], compare_inventories.verified_records(source)["release_info.json"]["sha256"])
        self.assertEqual(observation["sha256"], compare_inventories.verified_records(prototype)["release_info.json"]["sha256"])
        self.assertEqual(observation["release_info"], {
            "version": "v0.98.2", "branch": "v0.98.2", "commit": "f4eeecc6",
            "date": "2026-03-06T15:52:37-08:00"})

    def test_newer_release_metadata_does_not_identify_matching_source(self):
        root = Path(__file__).parent
        observation = json.loads((root / "clean_release_v107_observation_v1.json").read_bytes())
        newer = json.loads((root / "clean_inventory_v2.json").read_bytes())
        matching = json.loads((root / "matching_build_inventory_v2.json").read_bytes())
        self.assertEqual(observation["sha256"], compare_inventories.verified_records(newer)["release_info.json"]["sha256"])
        self.assertNotEqual(observation["sha256"], compare_inventories.verified_records(matching)["release_info.json"]["sha256"])
        self.assertEqual(observation["release_info"]["version"], "v0.107.1")

    def test_unknown_pair_refused_before_transformations(self):
        with mock.patch.object(prepare_managed, "arm64_metadata") as adaptation:
            with self.assertRaisesRegex(ValueError, "pair"):
                prepare_managed.prepare_pair(b"unknown", b"unknown")
            adaptation.assert_not_called()

    def test_both_archived_builds_remain_separate(self):
        root = Path(__file__).parent
        matching = json.loads((root / "matching_build_inventory_v2.json").read_bytes())
        current = json.loads((root / "clean_inventory_v2.json").read_bytes())
        prototype = json.loads((root / "prototype_inventory_v1.json").read_bytes())
        records = compare_inventories.verified_records(matching)
        prefix = compare_inventories.SOURCE_DATA
        self.assertEqual(records[prefix + "sts2.dll"]["sha256"], prepare_managed.WINDOWS_GAME)
        self.assertEqual(records[prefix + "Steamworks.NET.dll"]["sha256"], prepare_managed.WINDOWS_WRAPPER)
        self.assertNotEqual(compare_inventories.verified_records(current)[prefix + "sts2.dll"]["sha256"],
                            prepare_managed.WINDOWS_GAME)
        result = compare_inventories.compare(matching, prototype)
        self.assertEqual(result["counts"], dict(equal=29, different=173, source_only=27, prototype_only=48))
        self.assertEqual(result, json.loads((root / "matching_build_prototype_comparison_v1.json").read_bytes()))
        self.assertEqual(records["SlayTheSpire2.pck"]["sha256"],
                         compare_inventories.verified_records(prototype)["SlayTheSpire2.pck.before-sentry-patch"]["sha256"])
        self.assertNotEqual(records[prefix + "steam_api64.dll"]["sha256"],
                            records[prefix + "steam_api64.dll.bak"]["sha256"])


@unittest.skipUnless(os.environ.get("STS2_GAME_DLL") and os.environ.get("STS2_WRAPPER_DLL"),
                     "Set STS2_GAME_DLL and STS2_WRAPPER_DLL for inspected counterparts")
class MatchingBuildManagedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tagged_game = Path(os.environ["STS2_GAME_DLL"]).read_bytes()
        cls.tagged_wrapper = Path(os.environ["STS2_WRAPPER_DLL"]).read_bytes()
        def windows_image(raw):
            header = struct.unpack_from("<I", raw, 60)[0]
            return raw[:header + 4] + b"\x64\x86" + raw[header + 6:]
        cls.game, cls.wrapper = windows_image(cls.tagged_game), windows_image(cls.tagged_wrapper)

    def test_original_game_and_wrapper_relationships(self):
        self.assertEqual(patch_stats.sha256(self.game), prepare_managed.WINDOWS_GAME)
        self.assertEqual(patch_stats.sha256(self.wrapper), prepare_managed.WINDOWS_WRAPPER)
        self.assertEqual(prepare_managed.arm64_metadata(self.game, prepare_managed.WINDOWS_GAME,
                         patch_stats.GAME_SOURCE), self.tagged_game)
        self.assertEqual(prepare_managed.arm64_metadata(self.wrapper, prepare_managed.WINDOWS_WRAPPER,
                         patch_accessors.ORIGINAL_SHA256), self.tagged_wrapper)

    def test_complete_chain_matches_final_pair_without_mutation(self):
        game, wrapper = bytearray(self.game), bytearray(self.wrapper)
        result = prepare_managed.prepare_pair(game, wrapper)
        self.assertEqual(patch_stats.sha256(result["sts2.dll"]), patch_stats.GAME_TARGET)
        self.assertEqual(patch_stats.sha256(result["Steamworks.NET.dll"]), patch_stats.WRAPPER_TARGET)
        self.assertEqual(game, self.game)
        self.assertEqual(wrapper, self.wrapper)
        self.assertEqual(prepare_managed.prepare_pair(result["sts2.dll"], result["Steamworks.NET.dll"]), result)
        self.assertEqual(set(result), {"sts2.dll", "Steamworks.NET.dll"})

    def test_unknown_mixed_or_intermediate_pairs_refused(self):
        result = prepare_managed.prepare_pair(self.game, self.wrapper)
        for game, wrapper in ((result["sts2.dll"], self.wrapper), (self.game, result["Steamworks.NET.dll"]),
                              (self.tagged_game, self.tagged_wrapper), (self.game + b"changed", self.wrapper)):
            with self.subTest(), self.assertRaisesRegex(ValueError, "pair"):
                prepare_managed.prepare_pair(game, wrapper)

    def test_header_and_result_guards_cannot_be_bypassed_by_source_pin(self):
        for raw in (b"not PE", self.game[:63], self.tagged_game):
            with self.subTest(), self.assertRaises(ValueError):
                prepare_managed.arm64_metadata(raw, patch_stats.sha256(raw), patch_stats.GAME_SOURCE)
        with self.assertRaisesRegex(ValueError, "counterpart"):
            prepare_managed.arm64_metadata(self.game, prepare_managed.WINDOWS_GAME, "0" * 64)


if __name__ == "__main__":
    unittest.main()
