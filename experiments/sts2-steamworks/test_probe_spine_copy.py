import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import probe_spine_copy as probe


class SpineCopyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "source"
        self.prototype = Path(self.directory.name) / "prototype"
        for relative in ("spine-cpp/spine-cpp", "spine-godot/spine_godot/spine-cpp"):
            folder = self.root / relative / "src/spine"
            folder.mkdir(parents=True)
            (folder / "fixture.cpp").write_bytes(b"synthetic source\n")
            (folder / "fixture.o").write_bytes(b"excluded object")

    def test_equal_sources_hashes_optional_absence_and_no_writes(self):
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result = probe.collect(self.root, self.prototype)
        self.assertEqual(result["errors"], [])
        self.assertTrue(result["source_copy_matches"])
        self.assertEqual(result["sources"]["original"]["file_count"], 1)
        self.assertEqual(result["sources"]["original"], result["sources"]["copied"])
        self.assertTrue(all(not row["present"] for row in result["files"]))
        self.assertNotIn("synthetic source", json.dumps(result))
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_changed_missing_and_extra_sources_reported(self):
        folder = self.root / "spine-godot/spine_godot/spine-cpp/src/spine"
        (folder / "fixture.cpp").write_bytes(b"changed")
        (folder / "extra.h").write_bytes(b"extra")
        result = probe.collect(self.root, self.prototype)
        self.assertFalse(result["source_copy_matches"])
        self.assertEqual(result["difference_count"], 2)
        (folder / "fixture.cpp").unlink()
        result = probe.collect(self.root, self.prototype)
        self.assertEqual(result["difference_count"], 2)

    def test_failures_do_not_claim_equal_or_disclose_exception_details(self):
        with mock.patch.object(probe, "source_tree", side_effect=OSError("private")):
            result = probe.collect(self.root, self.prototype)
        self.assertNotIn("source_copy_matches", result)
        self.assertNotIn("private", json.dumps(result))
        with mock.patch.object(probe.os, "walk", return_value=[(str(self.root), [], ["x"] * 4096)]):
            with self.assertRaisesRegex(ValueError, "limit"):
                probe.source_tree(self.root)

    def test_symlinks_size_and_change_guards(self):
        path = self.root / "link.cpp"
        target = self.root / "spine-cpp/spine-cpp/src/spine/fixture.cpp"
        path.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "Symbolic"):
            probe.fingerprint(path)
        with target.open("wb") as stream:
            stream.truncate(16 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, "oversized"):
            probe.fingerprint(target)
        target.write_bytes(b"fixture")
        with mock.patch.object(probe.os, "fstat", return_value=self.root.stat()):
            with self.assertRaisesRegex(ValueError, "changed"):
                probe.fingerprint(target)
        (self.root / "spine-cpp/spine-cpp/linked-directory").symlink_to(self.prototype, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Symbolic"):
            probe.source_tree(self.root / "spine-cpp/spine-cpp")

    def test_library_inventory_comparison_is_full_hash_and_size(self):
        library = self.prototype / probe.LIB
        library.parent.mkdir(parents=True)
        library.write_bytes(b"synthetic binary")
        result = probe.collect(self.root, self.prototype)
        row = next(row for row in result["files"] if row["label"] == "deployed")
        self.assertFalse(row["matches_prototype_inventory"])
        self.assertEqual(row["sha256"], hashlib.sha256(b"synthetic binary").hexdigest())
        inventory = json.loads((Path(__file__).parent / "prototype_inventory_v1.json").read_text())
        observed = next(row for row in inventory["files"] if row["path"] == probe.LIB)
        self.assertEqual(observed["sha256"], probe.EXPECTED)
        self.assertEqual(observed["size_bytes"], 4328984)

    def test_archived_checkout_pins_remain_explicit_observations(self):
        observation = json.loads((Path(__file__).parent / "spine_build_inputs_observation_v1.json").read_text())
        self.assertEqual(observation["errors"], [])
        self.assertEqual([row["commit"] for row in observation["repositories"]], [
            "e7dc1435fa4a0083ab431f1b28e083c14a1f5c68", "27d9dd23c83871e0619fca5dc2cddfbfd69e926a"])
        for row in observation["repositories"]:
            self.assertEqual(row["errors"], [])
            self.assertEqual(row["tracked_changes"], [])
            self.assertEqual(row["untracked_count"], 0)

    def test_received_copy_observation_matches_inventory_and_upstream_api_pin(self):
        directory = Path(__file__).parent
        observation = json.loads((directory / "spine_copy_observation_v1.json").read_text())
        self.assertEqual(observation["errors"], [])
        self.assertTrue(observation["source_copy_matches"])
        self.assertEqual(observation["sources"]["original"], observation["sources"]["copied"])
        self.assertEqual(observation["sources"]["original"]["file_count"], 158)
        self.assertEqual(observation["difference_count"], 0)
        rows = {row["label"]: row for row in observation["files"]}
        for name in ("build", "example", "deployed"):
            self.assertTrue(rows[name]["matches_prototype_inventory"])
            self.assertEqual(rows[name]["sha256"], probe.EXPECTED)
            self.assertEqual(rows[name]["size_bytes"], 4328984)
        self.assertFalse(rows["custom.py"]["present"])
        self.assertFalse(rows["godot-cpp/dev"]["present"])
        pin = json.loads((directory / "spine_upstream_api_provenance_v1.json").read_text())
        api = rows["godot-cpp/gdextension/extension_api.json"]
        self.assertEqual(api["sha256"], pin["sha256"])
        self.assertEqual(api["size_bytes"], pin["size_bytes"])
        self.assertIn(pin["source_commit"], pin["url"])

    @unittest.skipUnless(os.environ.get("STS2_SPINE_API_JSON"), "Pinned upstream API source not supplied")
    def test_downloaded_upstream_api_full_bytes(self):
        pin = json.loads((Path(__file__).parent / "spine_upstream_api_provenance_v1.json").read_text())
        actual = probe.fingerprint(Path(os.environ["STS2_SPINE_API_JSON"]))
        self.assertEqual(actual, {key: pin[key] for key in ("sha256", "size_bytes")})


if __name__ == "__main__":
    unittest.main()
