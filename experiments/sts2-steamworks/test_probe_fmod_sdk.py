import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import probe_fmod_sdk as probe


class FmodSdkTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name) / "build"
        self.prototype = Path(self.directory.name) / "prototype"
        self.base.mkdir()
        self.prototype.mkdir()

    def test_header_tokens_hashes_and_no_contents_disclosed(self):
        header = self.base / "fmod_common.h"
        header.write_bytes(b"// synthetic\n#define FMOD_VERSION 0x00020315\n")
        result = probe.inspect(header, self.base, "header")
        self.assertEqual(result["fmod_version_definitions"], ["0x00020315"])
        self.assertEqual(result["sha256"], hashlib.sha256(header.read_bytes()).hexdigest())
        self.assertNotIn("synthetic", json.dumps(result))
        self.assertEqual(result["resolved_relative"], "fmod_common.h")

    def test_internal_aliases_allowed_external_and_broken_aliases_refused(self):
        target = self.base / "library.so.14.15"
        target.write_bytes(b"synthetic library")
        link = self.base / "library.so"
        link.symlink_to(target.name)
        result = probe.inspect(link, self.base, "core")
        self.assertEqual(result["resolved_relative"], target.name)
        self.assertFalse(result["matches_prototype_inventory"])
        external = self.prototype / "private"
        external.write_bytes(b"must not read")
        link.unlink()
        link.symlink_to(external)
        with self.assertRaisesRegex(ValueError, "outside"):
            probe.inspect(link, self.base, "core")
        external.unlink()
        with self.assertRaises(FileNotFoundError):
            probe.inspect(link, self.base, "core")

    def test_guard_size_concurrent_change_and_elf_byte_order(self):
        path = self.base / "library.so"
        raw = bytearray(64)
        raw[:6] = b"\x7fELF\x02\x02"
        raw[18:20] = (183).to_bytes(2, "big")
        path.write_bytes(raw)
        result = probe.inspect(path, self.base, "core")
        self.assertEqual(result["elf"], {"class_bits": 64, "machine": 183})
        with mock.patch.object(probe.os, "fstat", return_value=self.base.stat()):
            with self.assertRaisesRegex(ValueError, "changed"):
                probe.inspect(path, self.base, "core")
        with path.open("wb") as stream: stream.truncate(16 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, "oversized"):
            probe.inspect(path, self.base, "core")

    def test_collect_paths_missing_inputs_and_no_writes(self):
        layout = self.base / "sdk-layout/linux/core/inc"
        layout.mkdir(parents=True)
        (layout / "fmod_common.h").write_bytes(b"#define FMOD_VERSION 0x00020315\n")
        before = {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        result = probe.collect(self.base, self.prototype)
        self.assertEqual(result["errors"], [])
        self.assertEqual(len(result["files"]), 13)
        self.assertEqual(sum(row["present"] for row in result["files"]), 1)
        self.assertEqual(before, {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()})
        linked = self.base / "linked"
        linked.symlink_to(self.base, target_is_directory=True)
        self.assertTrue(probe.collect(linked, self.prototype)["errors"])

    def test_native_pins_match_archived_prototype(self):
        inventory = json.loads((Path(__file__).parent / "prototype_inventory_v1.json").read_text())
        by_path = {row["path"]: row for row in inventory["files"]}
        for name, kind in ((probe.EXTENSION, "extension"), ("libfmod.so.14", "core"), ("libfmodstudio.so.14", "studio")):
            row = by_path["addons/fmod/libs/linux/" + name]
            self.assertEqual((row["sha256"], row["size_bytes"]), probe.EXPECTED[kind])
            self.assertEqual(row["elf"], {"class_bits": 64, "machine": 183})

    def test_received_sdk_layout_closes_pending_fingerprint_check(self):
        observation = json.loads((Path(__file__).parent / "fmod_sdk_observation_v1.json").read_text())
        self.assertEqual(observation["errors"], [])
        self.assertEqual(len(observation["files"]), 13)
        self.assertTrue(all(row["present"] for row in observation["files"]))
        headers = [row for row in observation["files"] if row["kind"] == "header"]
        self.assertEqual(len(headers), 5)
        self.assertEqual([token for row in headers for token in row["fmod_version_definitions"]], ["0x00020315"])
        for row in observation["files"]:
            if row["kind"] != "header":
                self.assertTrue(row["matches_prototype_inventory"])
                self.assertEqual((row["sha256"], row["size_bytes"]), probe.EXPECTED[row["kind"]])
                self.assertEqual(row["elf"], {"class_bits": 64, "machine": 183})
        for row in headers:
            self.assertTrue(row["resolved_relative"].startswith("fmodstudioapi20315linux/api/"))


if __name__ == "__main__":
    unittest.main()
