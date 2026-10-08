import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import patch_accessors
import patch_stats as stats


FIXTURES = tuple(os.environ.get(name) for name in ("STS2_WRAPPER_DLL", "STS2_GAME_DLL", "STS2_NATIVE_LIBRARY"))


@unittest.skipUnless(all(FIXTURES), "Set the original wrapper, game, and native inspection fixture paths")
class StatsPatchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.data = Path(self.directory.name)
        wrapper = Path(FIXTURES[0]).read_bytes()
        wrapper = patch_accessors.patched_bytes(wrapper)
        wrapper = patch_accessors.patched_bytes(wrapper, "client023-v2")
        for name, blob in (
            ("Steamworks.NET.dll", wrapper),
            ("sts2.dll", Path(FIXTURES[1]).read_bytes()),
            ("libsteam_api64.so", Path(FIXTURES[2]).read_bytes()),
        ):
            stats.write_new(self.data / name, blob, 0o640)

    def hashes(self):
        return [stats.sha256((self.data / r[0]).read_bytes()) for r in stats.RECIPES]

    def test_read_only_inspection_and_exact_patch_scope(self):
        before = {p: p.read_bytes() for p in self.data.iterdir()}
        result = stats.run(self.data)
        self.assertEqual(result["status"], "inspected-no-writes")
        self.assertEqual([f["changed_byte_count"] for f in result["files"]], [1, 54])
        self.assertEqual(before, {p: p.read_bytes() for p in self.data.iterdir()})
        for recipe in stats.RECIPES:
            original = before[self.data / recipe[0]]
            candidate = stats.patched_bytes(original, recipe)
            self.assertEqual(len(original), len(candidate))
            offset = recipe[3]
            self.assertEqual(original[:offset], candidate[:offset])
            self.assertEqual(original[offset + len(recipe[4]):], candidate[offset + len(recipe[5]):])

    def test_install_repeat_restore_and_permissions(self):
        sources = [r[1] for r in stats.RECIPES]
        targets = [r[2] for r in stats.RECIPES]
        stats.run(self.data, "install")
        self.assertEqual(self.hashes(), targets)
        repeated = stats.run(self.data, "install")
        self.assertEqual([f["changed_byte_count"] for f in repeated["files"]], [0, 0])
        for recipe in stats.RECIPES:
            path = self.data / recipe[0]
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            self.assertEqual(stats.sha256(path.with_name(path.name + stats.BACKUP_SUFFIX).read_bytes()), recipe[1])
        stats.run(self.data, "restore")
        self.assertEqual(self.hashes(), sources)
        stats.run(self.data, "restore")
        self.assertEqual(self.hashes(), sources)

    def test_unknown_second_assembly_preflight_makes_no_writes(self):
        game = self.data / "sts2.dll"
        game.write_bytes(b"unrecognized game")
        before = {p: p.read_bytes() for p in self.data.iterdir()}
        with self.assertRaises(ValueError):
            stats.run(self.data, "install")
        self.assertEqual(before, {p: p.read_bytes() for p in self.data.iterdir()})

    def test_invalid_backup_preflight_makes_no_writes(self):
        backup = self.data / ("sts2.dll" + stats.BACKUP_SUFFIX)
        backup.write_bytes(b"unrelated backup")
        before = {p: p.read_bytes() for p in self.data.iterdir()}
        with self.assertRaises(ValueError):
            stats.run(self.data, "install")
        self.assertEqual(before, {p: p.read_bytes() for p in self.data.iterdir()})

    def test_second_replace_failure_rolls_back_first(self):
        replace = stats.replace_atomically
        def failing_replace(path, blob, mode, expected):
            if path.name == "sts2.dll":
                raise OSError("test replacement failure")
            replace(path, blob, mode, expected)
        with patch.object(stats, "replace_atomically", side_effect=failing_replace):
            with self.assertRaisesRegex(ValueError, 'rollback errors: \\[\\]'):
                stats.run(self.data, "install")
        self.assertEqual(self.hashes(), [r[1] for r in stats.RECIPES])

    def test_restore_failure_rolls_back_to_installed_pair(self):
        stats.run(self.data, "install")
        replace = stats.replace_atomically
        def failing_restore(path, blob, mode, expected):
            if path.name == "Steamworks.NET.dll":
                raise OSError("test restore failure")
            replace(path, blob, mode, expected)
        with patch.object(stats, "replace_atomically", side_effect=failing_restore):
            with self.assertRaisesRegex(ValueError, 'rollback errors: \\[\\]'):
                stats.run(self.data, "restore")
        self.assertEqual(self.hashes(), [r[2] for r in stats.RECIPES])

    def test_rollback_preserves_unknown_concurrent_change(self):
        replace = stats.replace_atomically
        wrapper = self.data / "Steamworks.NET.dll"
        def concurrent_change(path, blob, mode, expected):
            if path.name == "sts2.dll":
                wrapper.write_bytes(b"unrelated concurrent change")
                raise OSError("test replacement failure")
            replace(path, blob, mode, expected)
        with patch.object(stats, "replace_atomically", side_effect=concurrent_change):
            with self.assertRaisesRegex(ValueError, 'rollback errors: \\["'):
                stats.run(self.data, "install")
        self.assertEqual(wrapper.read_bytes(), b"unrelated concurrent change")
        self.assertEqual(stats.sha256((self.data / "sts2.dll").read_bytes()), stats.GAME_SOURCE)

    def test_interrupted_pair_can_roll_forward_or_restore(self):
        stats.run(self.data, "install")
        game = self.data / "sts2.dll"
        game.write_bytes(Path(FIXTURES[1]).read_bytes())
        stats.run(self.data, "install")
        self.assertEqual(self.hashes(), [r[2] for r in stats.RECIPES])
        stats.run(self.data, "restore")
        self.assertEqual(self.hashes(), [r[1] for r in stats.RECIPES])

    def test_symlinks_and_missing_backups_refused(self):
        wrapper = self.data / "Steamworks.NET.dll"
        link = self.data / "wrapper-link"
        link.symlink_to(wrapper)
        with self.assertRaises(ValueError):
            stats.read_regular(link)
        backup = wrapper.with_name(wrapper.name + stats.BACKUP_SUFFIX)
        backup.symlink_to(wrapper)
        with self.assertRaises(ValueError):
            stats.run(self.data, "install")
        backup.unlink()
        stats.run(self.data, "install")
        backup.unlink()
        with self.assertRaises(ValueError):
            stats.run(self.data, "install")
        with self.assertRaises(ValueError):
            stats.run(self.data, "restore")

    def test_native_hash_refused_and_generation_keeps_sources(self):
        before = self.hashes()
        output = self.data / "generated"
        output.mkdir()
        stats.run(self.data, "generate", output)
        self.assertEqual(self.hashes(), before)
        self.assertEqual([stats.sha256((output / r[0]).read_bytes()) for r in stats.RECIPES], [r[2] for r in stats.RECIPES])
        with self.assertRaises(ValueError):
            stats.run(self.data, "generate", output)
        (self.data / "libsteam_api64.so").write_bytes(b"unrecognized native library")
        with self.assertRaises(ValueError):
            stats.run(self.data, "install")


if __name__ == "__main__":
    unittest.main()
