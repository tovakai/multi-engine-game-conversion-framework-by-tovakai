import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import inspect_dependency_graph as inspection


def source():
    return {"runtimeTarget": {"name": "net9.0/win-x64"}, "compilationOptions": {},
            "targets": {"net9.0": {}, "net9.0/win-x64": {
                "game/1": {"dependencies": {"runtimepack/9": "9"}, "runtime": {"game.dll": {}}},
                "runtimepack/9": {"runtime": {"System.dll": {}}, "native": {"coreclr.dll": {}}}}},
            "libraries": {"game/1": {"type": "project"}, "runtimepack/9": {"type": "runtimepack"}}}


def inspect(value):
    raw = json.dumps(value).encode()
    return inspection.inspect(raw, hashlib.sha256(raw).hexdigest())


class DependencyInspectionTests(unittest.TestCase):
    def test_target_counts_and_record_hashes_without_mutation(self):
        value = source()
        original = json.dumps(value)
        result = inspect(value)
        self.assertEqual(result["runtime_target_name"], "net9.0/win-x64")
        self.assertEqual([t["library_count"] for t in result["targets"]], [0, 2])
        runtime = result["targets"][1]["libraries"][1]
        self.assertEqual(runtime["native_asset_names"], ["coreclr.dll"])
        self.assertEqual(runtime["managed_asset_count"], 1)
        self.assertEqual(runtime["record_sha256"], inspection.canonical_hash(value["targets"]["net9.0/win-x64"]["runtimepack/9"]))
        self.assertEqual(json.dumps(value), original)

    def test_hash_limit_and_nonstandard_json_refused(self):
        for raw, expected in ((b"unknown", "0" * 64), (b"x" * (inspection.MAX_BYTES + 1), "0" * 64),
                              (b'{"a":1,"a":2}', None), (b'{"a":NaN}', None), (b"[]", None)):
            expected = expected or hashlib.sha256(raw).hexdigest()
            with self.subTest(raw=raw[:20]), self.assertRaises(ValueError):
                inspection.inspect(raw, expected)

    def test_inconsistent_graph_or_nonobject_assets_refused(self):
        for change in ("target", "libraries", "runtime", "dependencies"):
            value = source()
            if change == "target":
                value["runtimeTarget"]["name"] = "missing"
            elif change == "libraries":
                value["libraries"] = {}
            else:
                value["targets"]["net9.0/win-x64"]["game/1"][change] = []
            with self.subTest(change=change), self.assertRaises(ValueError):
                inspect(value)

    def test_unknown_contents_are_hashed_not_dumped(self):
        value = source()
        value["extra"] = {"private": "do not dump"}
        result = inspect(value)
        self.assertNotIn("do not dump", json.dumps(result))
        self.assertEqual(result["root_record_hashes"]["extra"], inspection.canonical_hash(value["extra"]))

    def test_cli_reads_utf16_without_writes_and_refuses_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "game.deps.json"
            raw = json.dumps(source()).encode("utf-16")
            path.write_bytes(raw)
            command = [sys.executable, inspection.__file__, str(path), "--expected-sha256", hashlib.sha256(raw).hexdigest()]
            result = subprocess.run(command, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["errors"], [])
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(list(Path(directory).iterdir()), [path])
            link = Path(directory) / "link"
            link.symlink_to(path)
            command[2] = str(link)
            self.assertEqual(subprocess.run(command, capture_output=True, check=False).returncode, 2)

    def test_archived_source_summary_is_tied_to_matching_inventory(self):
        root = Path(__file__).parent
        result = json.loads((root / "source_dependency_observation_v1.json").read_bytes())
        inventory = json.loads((root / "matching_build_inventory_v2.json").read_bytes())
        row = next(r for r in inventory["files"] if r["path"].endswith("/sts2.deps.json"))
        self.assertEqual(result["sha256"], row["sha256"])
        self.assertEqual(result["size_bytes"], row["size_bytes"])
        self.assertEqual(result["runtime_target_name"], ".NETCoreApp,Version=v9.0/win-x64")
        active = next(t for t in result["targets"] if t["name"] == result["runtime_target_name"])
        self.assertEqual(active["library_count"], 19)
        pack = next(r for r in active["libraries"] if r["name"].startswith("runtimepack."))
        self.assertEqual(pack["managed_asset_count"], 169)
        self.assertEqual(len(pack["native_asset_names"]), 15)

    @unittest.skipUnless(os.environ.get("STS2_SOURCE_DEPS"), "Set STS2_SOURCE_DEPS for the local original capture")
    def test_uploaded_source_reproduces_the_archived_summary(self):
        raw = Path(os.environ["STS2_SOURCE_DEPS"]).read_bytes()
        result = inspection.inspect(raw, inspection.SOURCE_SHA256)
        archive = json.loads((Path(__file__).parent / "source_dependency_observation_v1.json").read_bytes())
        self.assertEqual(result, archive)


if __name__ == "__main__":
    unittest.main()
