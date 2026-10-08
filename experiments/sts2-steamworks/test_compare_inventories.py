import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import compare_inventories as comparison


def report(files, version=2):
    return {"inventory_version": version, "inventory_complete": True, "errors": [],
            "excluded": [], "files_hashed": len(files), "files": files,
            "tree_sha256": comparison.canonical_hash(files)}


def file(name, raw=b"synthetic"):
    return {"kind": "file", "path": name, "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest()}


class InventoryComparisonTests(unittest.TestCase):
    def test_mapping_counts_and_no_mutation(self):
        source = report([file(comparison.SOURCE_DATA + "same.dll"), file("changed"), file("only-source")])
        prototype = report([file(comparison.TARGET_DATA + "same.dll"), file("changed", b"new"), file("only-target")], 1)
        before = copy.deepcopy((source, prototype))
        result = comparison.compare(source, prototype)
        self.assertEqual(result["counts"], dict(equal=1, different=1, source_only=1, prototype_only=1))
        self.assertEqual(result["equal"][0]["prototype_path"], comparison.TARGET_DATA + "same.dll")
        self.assertEqual((source, prototype), before)

    def test_modes_and_stat_api_fields_are_not_byte_changes(self):
        source, prototype = report([file("same")]), report([file("same")])
        source["files"][0].update(mode="0o666", stat_api_difference_fields=["st_ctime_ns"])
        source["tree_sha256"] = comparison.canonical_hash(source["files"])
        self.assertEqual(comparison.compare(source, prototype)["counts"]["equal"], 1)

    def test_incomplete_empty_and_unknown_reports_refused(self):
        for fields in ({"inventory_complete": False}, {"errors": [{"error": "changed"}]},
                       {"inventory_version": 99}, {"files": []}, {"files_hashed": 0}):
            candidate = report([file("one")])
            candidate.update(fields)
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                comparison.compare(candidate, report([file("one")]))

    def test_modified_record_checksum_refused(self):
        candidate = report([file("one")])
        candidate["files"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "checksum"):
            comparison.verified_records(candidate)

    def test_unsafe_duplicate_and_nonregular_records_refused(self):
        for candidate in ([file("../outside")], [file("/absolute")], [file("a\\b")],
                          [file("C:drive")], [file("a//b")], [file("same"), file("same")],
                          [{"kind": "symlink", "path": "link"}],
                          [{**file("bad"), "sha256": "z" * 64}],
                          [{**file("bad"), "size_bytes": True}]):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                comparison.verified_records(report(candidate))

    def test_mapping_collision_refused(self):
        source = report([file(comparison.SOURCE_DATA + "same"), file(comparison.TARGET_DATA + "same")])
        with self.assertRaisesRegex(ValueError, "collision"):
            comparison.compare(source, report([file("other")]))

    def test_cli_accepts_utf16_and_does_not_change_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, prototype = root / "source.json", root / "prototype.json"
            source.write_bytes(json.dumps(report([file("same")])).encode("utf-16"))
            prototype.write_text(json.dumps(report([file("same")], 1)))
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            command = [sys.executable, str(Path(comparison.__file__)), str(source), str(prototype)]
            result = subprocess.run(command, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["counts"]["equal"], 1)
            self.assertEqual({p.name: p.read_bytes() for p in root.iterdir()}, before)

    def test_archived_observations_and_wrapper_relationship(self):
        root = Path(__file__).parent
        source = json.loads((root / "clean_inventory_v2.json").read_bytes())
        prototype = json.loads((root / "prototype_inventory_v1.json").read_bytes())
        result = comparison.compare(source, prototype)
        self.assertEqual(result["counts"], dict(equal=14, different=176, source_only=28, prototype_only=60))
        self.assertEqual(result, json.loads((root / "clean_prototype_comparison_v1.json").read_bytes()))
        records = comparison.verified_records(source)
        wrapper = records[comparison.SOURCE_DATA + "Steamworks.NET.dll"]
        self.assertEqual(wrapper["sha256"], "e1cd0bf2436cefbb8bfcfcc1cea0587e5b9c740769e8340f7b9e9de72785fcf0")
        self.assertNotEqual(records[comparison.SOURCE_DATA + "sts2.dll"]["size_bytes"],
                            comparison.verified_records(prototype)[comparison.TARGET_DATA + "sts2.dll"]["size_bytes"])


@unittest.skipUnless(os.environ.get("STS2_WRAPPER_DLL"), "Set STS2_WRAPPER_DLL for the inspected wrapper")
class WrapperRelationshipTests(unittest.TestCase):
    def test_restoring_only_the_pe_machine_matches_clean_hash(self):
        raw = bytearray(Path(os.environ["STS2_WRAPPER_DLL"]).read_bytes())
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "474a2af1328c2a2b32bedf8376ed46a50958423313856659ac05bee677d8fdd3")
        header = int.from_bytes(raw[60:64], "little")
        self.assertEqual(raw[header:header + 4], b"PE\0\0")
        self.assertEqual(raw[header + 4:header + 6], b"\x64\xaa")
        raw[header + 4:header + 6] = b"\x64\x86"
        source = json.loads((Path(__file__).parent / "clean_inventory_v2.json").read_bytes())
        expected = comparison.verified_records(source)[comparison.SOURCE_DATA + "Steamworks.NET.dll"]["sha256"]
        self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)


if __name__ == "__main__":
    unittest.main()
