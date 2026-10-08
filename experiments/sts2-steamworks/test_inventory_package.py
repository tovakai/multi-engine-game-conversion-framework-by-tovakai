import hashlib
import json
from pathlib import Path
import os
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import inventory_package as inventory


class PackageInventoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_full_tree_is_deterministic_and_read_only(self):
        files = {"game.pck": b"GDPC assets", "launch.sh": b"private launch content",
                 "data_sts2_linuxbsd_arm64/sts2.dll": b"synthetic IL fixture"}
        for name, data in files.items():
            path = self.root / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(data)
        first = inventory.collect(self.root)
        self.assertEqual(first, inventory.collect(self.root))
        self.assertEqual(first["errors"], [])
        self.assertEqual(first["files_hashed"], 3)
        for item in first["files"]:
            self.assertEqual(item["sha256"], hashlib.sha256(files[item["path"]]).hexdigest())
            self.assertEqual((self.root / item["path"]).read_bytes(), files[item["path"]])
        self.assertNotIn("private launch content", json.dumps(first))
        self.assertFalse(any(first["prototype_patch_checks"].values()))

    def test_symlink_files_and_directories_are_not_followed(self):
        with tempfile.TemporaryDirectory() as other:
            outside = Path(other)
            (outside / "account-token").write_text("secret")
            (self.root / "outside").symlink_to(outside, target_is_directory=True)
            (self.root / "file").symlink_to(outside / "account-token")
            (self.root / "broken").symlink_to("missing")
            report = inventory.collect(self.root)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["files_hashed"], 0)
        self.assertEqual(len(report["files"]), 3)
        self.assertNotIn(other, json.dumps(report))
        self.assertNotIn("account-token", json.dumps(report))
        self.assertEqual(report["files"][0]["target"], "missing")

    def test_excludes_only_declared_personal_directories_not_godot_assets(self):
        for name in ("saves", "userdata", "logs", ".git", ".godot"):
            folder = self.root / name
            folder.mkdir()
            (folder / "data").write_bytes(b"payload")
        report = inventory.collect(self.root)
        self.assertEqual(report["excluded"], [".git", "logs", "saves", "userdata"])
        self.assertEqual([item["path"] for item in report["files"]], [".godot/data"])

    def test_elf_byte_order_and_architecture(self):
        for byte_order, marker in (("<", 1), (">", 2)):
            for machine in (183, 62):
                data = bytearray(64)
                data[:6] = b"\x7fELF" + bytes((2, marker))
                struct.pack_into(byte_order + "H", data, 18, machine)
                path = self.root / "library.so"
                path.write_bytes(data)
                self.assertEqual(inventory.inspect_file(path)["elf"], {"class_bits": 64, "machine": machine})

    def test_runtimeconfig_exposes_only_version_metadata(self):
        path = self.root / "game.runtimeconfig.json"
        path.write_text(json.dumps({"runtimeOptions": {"tfm": "net9.0", "framework": {
            "name": "Microsoft.NETCore.App", "version": "9.0.7"}, "configProperties": {
                "private": "account-token"}}, "secret": "do not expose"}))
        result = inventory.inspect_file(path)
        self.assertEqual(result["dotnet"], {"tfm": "net9.0", "frameworks": [
            {"name": "Microsoft.NETCore.App", "version": "9.0.7"}]})
        self.assertNotIn("account-token", json.dumps(result))
        self.assertNotIn("do not expose", json.dumps(result))

    def test_malformed_files_are_reported_not_silently_accepted(self):
        (self.root / "bad.runtimeconfig.json").write_bytes(b"not JSON")
        (self.root / "bad.so").write_bytes(b"\x7fELF")
        os.mkfifo(self.root / "pipe")
        report = inventory.collect(self.root)
        self.assertEqual(len(report["errors"]), 3)
        self.assertFalse(report["inventory_complete"])

    def test_modified_file_is_refused(self):
        path = self.root / "file"
        path.write_bytes(b"content")
        with mock.patch.object(inventory, "identity", side_effect=[1, 2]):
            with self.assertRaisesRegex(ValueError, "file changed"):
                inventory.inspect_file(path)

    def test_windows_stat_families_can_differ_without_false_change(self):
        path = self.root / "file.dll"
        content = b"synthetic unchanged assembly"
        path.write_bytes(content)
        native_fstat = os.fstat
        def windows_handle_stat(fd):
            value = native_fstat(fd)
            return SimpleNamespace(st_mode=value.st_mode, st_size=value.st_size,
                                   st_dev=value.st_dev + 1, st_ino=0,
                                   st_mtime_ns=value.st_mtime_ns // 1000000000 * 1000000000,
                                   st_ctime_ns=0)
        with mock.patch.object(inventory, "COMPARE_HANDLE_PATH_STATS", False):
            with mock.patch.object(inventory.os, "fstat", side_effect=windows_handle_stat):
                item = inventory.inspect_file(path)
        self.assertEqual(item["sha256"], hashlib.sha256(content).hexdigest())
        self.assertIn("st_ino", item["stat_api_difference_fields"])
        self.assertIn("st_ctime_ns", item["stat_api_difference_fields"])
        self.assertEqual(path.read_bytes(), content)

    def test_windows_still_refuses_real_descriptor_changes(self):
        path = self.root / "file"
        path.write_bytes(b"content")
        value = path.stat()
        changed = SimpleNamespace(**{name: getattr(value, name) for name in inventory.STAT_FIELDS},
                                  st_mode=value.st_mode)
        changed.st_mtime_ns += 1
        with mock.patch.object(inventory, "COMPARE_HANDLE_PATH_STATS", False):
            with mock.patch.object(inventory.os, "fstat", side_effect=[value, changed]):
                with self.assertRaisesRegex(ValueError, "file changed"):
                    inventory.inspect_file(path)

    def test_windows_still_refuses_path_replacement(self):
        path = self.root / "file"
        path.write_bytes(b"content")
        value = path.stat()
        replaced = SimpleNamespace(**{name: getattr(value, name) for name in inventory.STAT_FIELDS},
                                   st_mode=value.st_mode)
        replaced.st_ino += 1
        with mock.patch.object(inventory, "COMPARE_HANDLE_PATH_STATS", False):
            with mock.patch.object(Path, "lstat", side_effect=[value, replaced]):
                with self.assertRaisesRegex(ValueError, "file changed"):
                    inventory.inspect_file(path)

    def test_windows_still_refuses_inconsistent_stream_size(self):
        path = self.root / "file"
        path.write_bytes(b"content")
        value = path.stat()
        handle = SimpleNamespace(**{name: getattr(value, name) for name in inventory.STAT_FIELDS},
                                 st_mode=value.st_mode)
        handle.st_size += 1
        with mock.patch.object(inventory, "COMPARE_HANDLE_PATH_STATS", False):
            with mock.patch.object(inventory.os, "fstat", return_value=handle):
                with self.assertRaisesRegex(ValueError, "file changed"):
                    inventory.inspect_file(path)

    def test_posix_retains_cross_api_identity_guard(self):
        path = self.root / "file"
        path.write_bytes(b"content")
        value = path.stat()
        other = SimpleNamespace(**{name: getattr(value, name) for name in inventory.STAT_FIELDS},
                                st_mode=value.st_mode)
        other.st_ino += 1
        with mock.patch.object(inventory, "COMPARE_HANDLE_PATH_STATS", True):
            with mock.patch.object(inventory.os, "fstat", return_value=other):
                with self.assertRaisesRegex(ValueError, "file changed"):
                    inventory.inspect_file(path)

    def test_missing_or_symlink_root_is_refused(self):
        self.assertTrue(inventory.collect(self.root / "missing")["errors"])
        link = self.root / "link"
        link.symlink_to(self.root, target_is_directory=True)
        self.assertTrue(inventory.collect(link)["errors"])

    def test_published_heredoc_contains_the_complete_tested_script(self):
        directory = Path(__file__).parent
        source = (directory / "inventory_package.py").read_text()
        document = (directory / "FRAME_INVENTORY.md").read_text()
        self.assertEqual(document.count("```bash"), 1)
        self.assertIn("python3 - <<'PY'\n" + source + "PY\n```", document)

    def test_clean_source_shell_blocks_share_the_tested_collector(self):
        directory = Path(__file__).parent
        source = (directory / "inventory_package.py").read_text().replace(
            'ROOT = Path("/run/media/steamos/SD512/sts2-arm64-proto")',
            'ROOT = Path(r"REPLACE_WITH_CLEAN_STS2_DIRECTORY")')
        document = (directory / "CLEAN_SOURCE_INVENTORY.md").read_text()
        self.assertEqual(document.count(source), 2)
        self.assertIn("python3 - <<'PY'\n" + source + "PY\n```", document)
        self.assertIn("@'\n" + source + "'@ | python -\n```", document)

    def test_clean_source_bash_block_executes_without_repository_dependencies(self):
        document = (Path(__file__).parent / "CLEAN_SOURCE_INVENTORY.md").read_text()
        block = document.split("```bash\n", 1)[1].split("\n```", 1)[0]
        block = block.replace('Path(r"REPLACE_WITH_CLEAN_STS2_DIRECTORY")',
                              "Path(" + json.dumps(str(self.root)) + ")")
        content = b"synthetic unmodified assembly"
        (self.root / "sts2.dll").write_bytes(content)
        result = subprocess.run(["bash"], input=block, text=True, capture_output=True, cwd=self.root, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["files_hashed"], 1)
        self.assertEqual(report["files"][0]["sha256"], hashlib.sha256(content).hexdigest())
        self.assertFalse(any(report["prototype_patch_checks"].values()))
        self.assertEqual(list(self.root.iterdir()), [self.root / "sts2.dll"])
        self.assertEqual((self.root / "sts2.dll").read_bytes(), content)


if __name__ == "__main__":
    unittest.main()
