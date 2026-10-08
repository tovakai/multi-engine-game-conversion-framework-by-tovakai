import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import probe_deployment_config as probe


class DeploymentConfigTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def add(self, name, raw):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return {name: hashlib.sha256(raw).hexdigest()}

    def test_verified_text_and_structured_config_without_writes(self):
        files = self.add("launch.sh", b"#!/bin/sh\nexec ./Godot \"$@\"\n")
        files.update(self.add("game.runtimeconfig.json", b'{"runtimeOptions":{"includedFrameworks":[{"name":"Microsoft.NETCore.App","version":"9.0.7"}]}}'))
        before = {path: path.read_bytes() for path in self.root.iterdir()}
        result = probe.collect(self.root, files)
        self.assertEqual(result["errors"], [])
        self.assertEqual(len(result["files"]), 2)
        self.assertIn("includedFrameworks", result["files"][1]["contents"]["runtimeOptions"])
        self.assertEqual(before, {path: path.read_bytes() for path in self.root.iterdir()})

    def test_deps_summary_retains_target_and_native_routes_not_all_managed_assets(self):
        value = {"runtimeTarget": {"name": "net9.0/linux-arm64"}, "targets": {
            "net9.0/linux-arm64": {
                "Microsoft.NETCore.App.Runtime.linux-arm64/9.0.7": {
                    "native": {"libcoreclr.so": {}}, "runtime": {"System.Private.CoreLib.dll": {}}},
                "Extension/1.0": {"runtimeTargets": {"native.so": {"assetType": "native", "rid": "linux-arm64"}}}}}}
        result = probe.collect(self.root, self.add("game.deps.json", json.dumps(value).encode()))
        self.assertEqual(result["errors"], [])
        contents = result["files"][0]["contents"]
        self.assertEqual(contents["runtimeTarget"], value["runtimeTarget"])
        self.assertEqual(contents["targets"][0]["library_count"], 2)
        self.assertIn("libcoreclr.so", json.dumps(contents))
        self.assertIn("native.so", json.dumps(contents))
        self.assertNotIn("System.Private.CoreLib.dll", json.dumps(contents))

    def test_unknown_hash_withholds_contents(self):
        files = self.add("launch.sh", b"private content")
        files["launch.sh"] = "0" * 64
        result = probe.collect(self.root, files)
        self.assertEqual(result["files"], [])
        self.assertEqual(len(result["errors"]), 1)
        self.assertNotIn("private content", json.dumps(result))

    def test_missing_file_and_symlinks_are_refused(self):
        (self.root / "link").symlink_to(self.root, target_is_directory=True)
        (self.root / "link.sh").symlink_to(self.root / "missing")
        result = probe.collect(self.root, {"missing": "0" * 64, "link/file": "0" * 64, "link.sh": "0" * 64})
        self.assertEqual(result["files"], [])
        self.assertEqual(len(result["errors"]), 3)

    def test_oversized_file_and_invalid_json_are_refused(self):
        files = self.add("large.sh", b"x" * 1048577)
        files.update(self.add("invalid.json", b"not JSON"))
        result = probe.collect(self.root, files)
        self.assertEqual(result["files"], [])
        self.assertEqual(len(result["errors"]), 2)

    def test_changed_file_is_refused(self):
        files = self.add("launch.sh", b"shell fixture")
        real_lstat = Path.lstat
        with mock.patch.object(Path, "lstat", side_effect=lambda path: real_lstat(path), autospec=True):
            with mock.patch.object(probe.os, "fstat", side_effect=[
                    (self.root / "launch.sh").stat(), self.root.stat()]):
                result = probe.collect(self.root, files)
        self.assertEqual(result["files"], [])
        self.assertIn("file changed", result["errors"][0]["error"])

    def test_device_inventory_checksum_and_probe_guards_match_archived_evidence(self):
        report = json.loads((Path(__file__).parent / "prototype_inventory_v1.json").read_text())
        digest = hashlib.sha256(json.dumps(report["files"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(digest, report["tree_sha256"])
        self.assertEqual(report["files_hashed"], len(report["files"]))
        self.assertEqual(report["errors"], [])
        records = {item["path"]: item for item in report["files"]}
        for path, expected in probe.FILES.items():
            self.assertEqual(records[path]["sha256"], expected)
            self.assertLess(records[path]["size_bytes"], 1048576)

    def test_received_deployment_is_hash_consistent_and_self_contained(self):
        path = Path(__file__).parent / "prototype_deployment_v1.json"
        if not path.is_file():
            self.skipTest("Local full-text deployment capture is not redistributed")
        report = json.loads(path.read_text())
        self.assertEqual(report["errors"], [])
        records = {item["path"]: item for item in report["files"]}
        self.assertEqual(set(records), set(probe.FILES))
        for name, item in records.items():
            self.assertEqual(item["sha256"], probe.FILES[name])
            if isinstance(item["contents"], str):
                self.assertEqual(hashlib.sha256(item["contents"].encode()).hexdigest(), item["sha256"])
        options = records["data_sts2_linuxbsd_arm64/sts2.runtimeconfig.json"]["contents"]["runtimeOptions"]
        self.assertEqual(options["includedFrameworks"], [{"name": "Microsoft.NETCore.App", "version": "9.0.7"}])
        dependencies = records["data_sts2_linuxbsd_arm64/sts2.deps.json"]["contents"]
        self.assertEqual(dependencies["runtimeTarget"]["name"], ".NETCoreApp,Version=v9.0/linux-arm64")


if __name__ == "__main__":
    unittest.main()
