import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import patch_pack as patcher
import probe_packed_extensions as reader
from test_probe_packed_extensions import make_pack


FMOD = "addons/fmod/fmod.gdextension"
SENTRY = "addons/sentry/sentry.gdextension"
SPINE = "bin/spine_godot_extension.gdextension"
LIST = ".godot/extension_list.cfg"


def adapt(resources):
    result = dict(resources)
    result[FMOD] = b"after_fmod"
    result[SENTRY] = b"after_sentry"
    return result, {"synthetic": True}


class PackPatchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source, self.output = self.root / "source.pck", self.root / "output.pck"
        self.resources = {FMOD: b"before_fmod", SENTRY: b"before_sentry", SPINE: b"unchanged_spine", LIST: b"",
                          "assets/data.txt": b"untouched_asset\n"}
        self.write_source()

    def write_source(self, *, base=128, directory=8192, **kwargs):
        self.raw = make_pack(list(self.resources.items()), base=base, directory=directory, **kwargs)
        self.source.write_bytes(self.raw)

    def run_patch(self, **kwargs):
        return patcher.rewrite_pack(self.source, self.output, expected_sha256=hashlib.sha256(self.raw).hexdigest(),
                                    expected_size=len(self.raw), transform=kwargs.pop("transform", adapt), **kwargs)

    def test_append_preserves_every_original_byte_except_directory_pointer(self):
        report = self.run_patch()
        result = self.output.read_bytes()
        restored_prefix = result[:32] + self.raw[32:40] + result[40:len(self.raw)]
        self.assertEqual(restored_prefix, self.raw)
        self.assertEqual(self.source.read_bytes(), self.raw)
        self.assertEqual(report["output_sha256"], hashlib.sha256(result).hexdigest())
        self.assertEqual(report["output_size_bytes"], len(result))
        self.assertEqual(report["changed_paths"], [FMOD, SENTRY])
        new, new_entries = reader.inspect_pack(self.output)
        old, old_entries = reader.inspect_pack(self.source)
        self.assertEqual(new["file_base"], old["file_base"])
        self.assertEqual(new_entries["assets/data.txt"], old_entries["assets/data.txt"])
        self.assertEqual({row["path"]: row["text"] for row in new["extension_configs"]}[FMOD], "after_fmod")
        self.assertTrue(all(row["table_md5_matches"] for row in new["extension_configs"]))
        with self.source.open("rb") as stream: _, _, old_table, old_offsets = patcher._table(stream, len(self.raw))
        with self.output.open("rb") as stream: _, _, _, new_offsets = patcher._table(stream, len(result))
        for name in (SPINE, LIST, "assets/data.txt"):
            self.assertEqual(old_offsets[name]["offset"], new_offsets[name]["offset"])
        self.assertEqual(result[old["directory_offset"]:old["directory_offset"] + len(old_table)], old_table)

    def test_header_directory_layout_and_multiple_stream_blocks(self):
        self.resources["assets/data.txt"] = b"streamed asset" * 100000
        for base, directory in ((8192, 104), (128, 2000000)):
            self.write_source(base=base, directory=directory)
            report = self.run_patch()
            parsed, _ = reader.inspect_pack(self.output)
            self.assertEqual(parsed["file_base"], base)
            self.assertGreater(report["output_directory"], len(self.raw))
            self.output.unlink()

    def test_no_change_clone_is_byte_identical(self):
        report = self.run_patch(transform=lambda value: (value, {}))
        self.assertEqual(self.output.read_bytes(), self.raw)
        self.assertEqual(report["changed_paths"], [])
        self.assertEqual(report["original_prefix_changes"], [])

    def test_wrong_source_hash_size_or_manifest_md5_leaves_no_output(self):
        with self.assertRaisesRegex(ValueError, "hash or file identity"):
            patcher.rewrite_pack(self.source, self.output, expected_sha256="0" * 64, expected_size=len(self.raw), transform=adapt)
        with self.assertRaisesRegex(ValueError, "expected size"):
            patcher.rewrite_pack(self.source, self.output, expected_sha256="0" * 64, expected_size=len(self.raw) + 1, transform=adapt)
        modified = bytearray(self.raw)
        modified[128] ^= 1
        self.raw = bytes(modified)
        self.source.write_bytes(self.raw)
        with self.assertRaisesRegex(ValueError, "MD5"):
            self.run_patch()
        self.assertFalse(self.output.exists())
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["source.pck"])

    def test_existing_and_racing_destinations_are_never_overwritten(self):
        self.output.write_bytes(b"user file")
        with self.assertRaisesRegex(ValueError, "Destination exists"):
            self.run_patch()
        self.assertEqual(self.output.read_bytes(), b"user file")
        self.output.unlink()
        real_link = patcher.os.link
        def racing_link(temporary, destination):
            self.output.write_bytes(b"concurrent user file")
            return real_link(temporary, destination)
        with mock.patch.object(patcher.os, "link", side_effect=racing_link):
            with self.assertRaises(FileExistsError): self.run_patch()
        self.assertEqual(self.output.read_bytes(), b"concurrent user file")
        self.assertEqual(self.source.read_bytes(), self.raw)
        self.assertFalse(any(path.suffix == ".tmp" for path in self.root.iterdir()))

    def test_private_staging_rename_preserves_concurrent_destination(self):
        real_publish = patcher.publish_new
        def racing_publish(temporary, destination):
            self.output.write_bytes(b"concurrent user file")
            return real_publish(temporary, destination)
        with mock.patch.object(patcher, "publish_new", side_effect=racing_publish):
            with self.assertRaises(FileExistsError):
                self.run_patch(atomic_publication=False)
        self.assertEqual(self.output.read_bytes(), b"concurrent user file")
        self.assertEqual(self.source.read_bytes(), self.raw)
        self.assertFalse(any(path.suffix == ".tmp" for path in self.root.iterdir()))

    def test_flush_or_identity_failure_cleans_temporary_files(self):
        with mock.patch.object(patcher.os, "fsync", side_effect=OSError("synthetic disk error")):
            with self.assertRaises(OSError): self.run_patch()
        with mock.patch.object(patcher, "identity", side_effect=[1, 2]):
            with self.assertRaisesRegex(ValueError, "identity"): self.run_patch()
        self.assertFalse(self.output.exists())
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["source.pck"])

    def test_unknown_formats_flags_bad_paths_and_duplicate_aliases_refused(self):
        for changes in ({"version": 2}, {"pack_flags": 1}, {"entry_flags": 1}):
            self.write_source(**changes)
            with self.assertRaises(ValueError): self.run_patch()
        for name in ("../escape", "res://assets/data.txt", "assets//alias", "/absolute", "a\\b"):
            self.resources[name] = b"rejected"
            self.write_source()
            with self.assertRaisesRegex(ValueError, "resource path"): self.run_patch()
            del self.resources[name]
        self.assertFalse(self.output.exists())

    def test_malformed_bounds_truncation_missing_configs_and_changed_preserved_resources(self):
        for offset, layout, value in ((32, "<Q", len(self.raw) + 1), (8192, "<I", 200001), (8196, "<I", 0)):
            raw = bytearray(self.raw)
            struct.pack_into(layout, raw, offset, value)
            self.source.write_bytes(raw)
            with self.assertRaises(ValueError):
                patcher.rewrite_pack(self.source, self.output, expected_sha256=hashlib.sha256(raw).hexdigest(), expected_size=len(raw), transform=adapt)
        del self.resources[SPINE]
        self.write_source()
        with self.assertRaisesRegex(ValueError, "missing"): self.run_patch()
        self.resources[SPINE] = b"unchanged"
        self.write_source()
        def wrong_transform(value):
            value[SPINE] = b"changed"
            return value, {}
        with self.assertRaisesRegex(ValueError, "Preserved"): self.run_patch(transform=wrong_transform)

    def test_symlink_inputs_outputs_and_parents_refused(self):
        link = self.root / "link.pck"
        link.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, "Symbolic"):
            patcher.rewrite_pack(link, self.output, expected_sha256="0" * 64, expected_size=len(self.raw))
        self.output.symlink_to(self.root / "missing")
        with self.assertRaisesRegex(ValueError, "Symbolic"): self.run_patch()
        self.output.unlink()
        folder = self.root / "linked"
        folder.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Symbolic"):
            patcher.rewrite_pack(self.source, folder / "output", expected_sha256="0" * 64, expected_size=len(self.raw))

    def test_windows_descriptor_path_precision_difference_does_not_reject_unchanged_file(self):
        real_fstat = patcher.os.fstat
        def descriptor(fd):
            original = real_fstat(fd)
            fields = {name: getattr(original, name) for name in ("st_mode", "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")}
            fields["st_ctime_ns"] -= 1000
            return SimpleNamespace(**fields)
        with mock.patch.object(patcher, "COMPARE_HANDLE_PATH_STATS", False), mock.patch.object(patcher.os, "fstat", side_effect=descriptor):
            self.run_patch()
        self.assertTrue(self.output.exists())

    def test_sts2_source_guard_matches_matching_build_inventory_not_new_release(self):
        directory = Path(__file__).parent
        matching = json.loads((directory / "matching_build_inventory_v2.json").read_text())
        newer = json.loads((directory / "clean_inventory_v2.json").read_text())
        def pack(value): return next(row for row in value["files"] if row["path"] == "SlayTheSpire2.pck")
        self.assertEqual((pack(matching)["sha256"], pack(matching)["size_bytes"]), (patcher.SOURCE_SHA256, patcher.SOURCE_SIZE))
        self.assertNotEqual(pack(newer)["sha256"], patcher.SOURCE_SHA256)

    def test_cli_returns_json_and_never_accepts_an_unknown_pack(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            status = patcher.main([str(self.source), str(self.output)])
        self.assertEqual(status, 2)
        self.assertTrue(json.loads(output.getvalue())["errors"])
        self.assertFalse(self.output.exists())
        with mock.patch.object(patcher, "patch_sts2_pack", return_value={"changed_paths": [FMOD]}), mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            status = patcher.main([str(self.source), str(self.output)])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())["errors"], [])

    def test_actual_observed_manifests_fit_append_writer(self):
        capture = Path(__file__).parent / "prototype_packed_extensions_v1.json"
        if not capture.exists(): self.skipTest("Local manifest capture not supplied")
        observation = json.loads(capture.read_text())
        before = next(pack for pack in observation["packs"] if pack["path"].endswith("before-sentry-patch"))
        self.resources = {row["path"]: row["text"].encode() for row in before["extension_configs"]}
        self.resources["assets/data.txt"] = b"unmodified synthetic payload"
        self.write_source()
        from adapt_packed_manifests import adapt_bundle
        report = self.run_patch(transform=adapt_bundle)
        self.assertEqual(report["changed_paths"], [FMOD, SENTRY])
        parsed, _ = reader.inspect_pack(self.output)
        for row in parsed["extension_configs"]:
            if row["path"] in patcher.RECIPES:
                self.assertEqual(row["sha256"], patcher.RECIPES[row["path"]][1])

    @unittest.skipUnless(os.environ.get("STS2_GODOT_PACK_TEST_ENGINE"), "Independent Godot reader not supplied")
    def test_official_godot_reads_patched_pack_and_unchanged_asset(self):
        self.resources["project.godot"] = b'[application]\nconfig/name="PCK Smoke"\n'
        self.resources["smoke.gd"] = b'''extends SceneTree
func _initialize():
    assert(FileAccess.get_file_as_string("res://assets/data.txt").strip_edges() == "untouched_asset")
    assert(FileAccess.get_file_as_string("res://addons/fmod/fmod.gdextension") == "after_fmod")
    assert(FileAccess.get_file_as_string("res://addons/sentry/sentry.gdextension") == "after_sentry")
    print("PCK_APPEND_SMOKE_OK")
    quit()
'''
        self.write_source()
        self.run_patch()
        environment = dict(os.environ, GODOT_SILENCE_ROOT_WARNING="1", XDG_CACHE_HOME=str(self.root / "cache"),
                           XDG_DATA_HOME=str(self.root / "data"), XDG_CONFIG_HOME=str(self.root / "config"))
        result = subprocess.run([os.environ["STS2_GODOT_PACK_TEST_ENGINE"], "--headless", "--main-pack", str(self.output),
                                 "--script", "res://smoke.gd"], cwd=self.root, env=environment,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PCK_APPEND_SMOKE_OK", result.stdout)
        self.assertNotIn("SCRIPT ERROR", result.stdout + result.stderr)


if __name__ == "__main__": unittest.main()
