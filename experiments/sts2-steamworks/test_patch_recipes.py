"""Installer tests against the uploaded assembly, supplied via STS2_WRAPPER_DLL."""

import os
from pathlib import Path
import stat
import tempfile
import unittest

import patch_accessors as patcher


FIXTURE = os.environ.get("STS2_WRAPPER_DLL")


@unittest.skipUnless(FIXTURE, "Set STS2_WRAPPER_DLL to the original uploaded wrapper")
class PatchRecipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = Path(FIXTURE).read_bytes()
        if patcher.sha256(cls.original) != patcher.ORIGINAL_SHA256:
            raise ValueError("Fixture does not match the inspected original wrapper")
        cls.v1 = patcher.patched_bytes(cls.original)
        cls.client = patcher.patched_bytes(cls.v1, "client023-v2")

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "Steamworks.NET.dll"
        patcher.write_new(self.path, self.v1, 0o640)

    def test_exact_single_byte_and_string(self):
        self.assertEqual(len(self.v1), len(self.client))
        self.assertEqual([(i, a, b) for i, (a, b) in enumerate(zip(self.v1, self.client)) if a != b], [(360492, 0x31, 0x33)])
        self.assertEqual(self.client[360466:360494], "SteamClient023".encode("utf-16-le"))
        self.assertEqual(patcher.sha256(self.client), patcher.CLIENT_PATCHED_SHA256)

    def test_generate_does_not_change_input_or_overwrite_output(self):
        output = self.path.with_name("candidate.dll")
        result = patcher.run(self.path, output=output, recipe="client023-v2")
        self.assertEqual(result["status"], "generated")
        self.assertEqual(self.path.read_bytes(), self.v1)
        self.assertEqual(output.read_bytes(), self.client)
        with self.assertRaises(FileExistsError):
            patcher.run(self.path, output=output, recipe="client023-v2")

    def test_install_repeat_restore_and_mode(self):
        result = patcher.run(self.path, install=True, recipe="client023-v2")
        self.assertEqual(result["changed_byte_count"], 1)
        self.assertEqual(self.path.read_bytes(), self.client)
        backup = Path(result["backup"])
        self.assertEqual(backup.read_bytes(), self.v1)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o640)
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o640)
        self.assertEqual(patcher.run(self.path, install=True, recipe="client023-v2")["status"], "already-patched")
        self.assertEqual(patcher.run(self.path, restore=True, recipe="client023-v2")["status"], "restored")
        self.assertEqual(self.path.read_bytes(), self.v1)
        self.assertEqual(patcher.run(self.path, restore=True, recipe="client023-v2")["status"], "already-source")

    def test_bad_source_and_backup_are_refused(self):
        for content in (self.original, patcher.patched_bytes(self.v1, "http-generic-v2"), b"invalid"):
            with self.subTest(content_hash=patcher.sha256(content)):
                with self.assertRaises(ValueError):
                    patcher.patched_bytes(content, "client023-v2")
        backup = self.path.with_name(self.path.name + ".before-client023-v2")
        patcher.write_new(backup, b"unrelated existing backup", 0o640)
        with self.assertRaises(ValueError):
            patcher.run(self.path, install=True, recipe="client023-v2")
        self.assertEqual(self.path.read_bytes(), self.v1)
        self.assertEqual(backup.read_bytes(), b"unrelated existing backup")

    def test_symlink_assembly_and_backup_are_refused(self):
        link = self.path.with_name("link.dll")
        link.symlink_to(self.path)
        with self.assertRaises(ValueError):
            patcher.run(link, install=True, recipe="client023-v2")
        backup = self.path.with_name(self.path.name + ".before-client023-v2")
        backup.symlink_to(self.path)
        with self.assertRaises(ValueError):
            patcher.run(self.path, install=True, recipe="client023-v2")

    def test_restore_chain_and_wrong_layer_refusal(self):
        original_path = self.path.with_name("original.dll")
        patcher.write_new(original_path, self.original, 0o640)
        patcher.run(original_path, install=True)
        patcher.run(original_path, install=True, recipe="client023-v2")
        with self.assertRaises(ValueError):
            patcher.run(original_path, restore=True)
        patcher.run(original_path, restore=True, recipe="client023-v2")
        patcher.run(original_path, restore=True)
        self.assertEqual(original_path.read_bytes(), self.original)

    def test_corrupt_backup_prevents_repeat_install_and_restore(self):
        result = patcher.run(self.path, install=True, recipe="client023-v2")
        with Path(result["backup"]).open("wb") as stream:
            stream.write(b"corrupt")
        for action in ({"install": True}, {"restore": True}):
            with self.assertRaises(ValueError):
                patcher.run(self.path, recipe="client023-v2", **action)
        self.assertEqual(self.path.read_bytes(), self.client)

    def test_atomic_replace_rejects_changed_input(self):
        with self.assertRaises(ValueError):
            patcher.replace_atomically(self.path, self.client, 0o640, "wrong-hash")
        self.assertEqual(self.path.read_bytes(), self.v1)
        self.assertEqual(sorted(p.name for p in self.path.parent.iterdir()), [self.path.name])


if __name__ == "__main__":
    unittest.main()
