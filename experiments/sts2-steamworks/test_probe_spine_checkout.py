from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import probe_spine_checkout as probe


class SpineProvenanceProbeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def checkout(self, path=None):
        folder = path or self.root / "build" / "spine-runtimes"
        folder.mkdir(parents=True)
        (folder / ".git").mkdir()
        return folder

    def test_git_commands_are_read_only_and_contents_not_requested(self):
        self.checkout()
        with mock.patch.object(probe.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "metadata\n", "")) as run:
            result = probe.collect([self.root, self.root])
        self.assertEqual(len(result["checkouts"]), 1)
        self.assertEqual(result["checkouts"][0]["commit"], "metadata")
        self.assertEqual(run.call_count, 4)
        for call in run.call_args_list:
            self.assertIn("--no-optional-locks", call.args[0])
            self.assertIn("core.fsmonitor=false", call.args[0])
            self.assertNotIn("fetch", call.args[0])
            self.assertNotIn("remote", call.args[0])

    def test_bounds_skips_symlinks_and_missing_roots_are_explicit(self):
        folder = self.checkout(self.root / ".cache" / "spine-runtimes")
        (self.root / "link").symlink_to(folder, target_is_directory=True)
        self.checkout(self.root / "a" / "b" / "spine-runtimes")
        with mock.patch.object(probe.subprocess, "run") as run:
            result = probe.collect([self.root, self.root / "missing"], max_depth=1)
            self.assertEqual(result["checkouts"], [])
            run.assert_not_called()
            limited = probe.collect([self.root], max_directories=1)
        self.assertTrue(limited["search_incomplete"])
        self.assertEqual(limited["checkouts"], [])

    def test_git_failure_and_timeout_do_not_claim_a_source_pin(self):
        self.checkout()
        with mock.patch.object(probe.subprocess, "run", side_effect=[
            subprocess.CompletedProcess([], 128, "", "private remote URL"),
            subprocess.TimeoutExpired("git", 20), OSError("private path"),
            subprocess.CompletedProcess([], 0, "", "")]):
            result = probe.collect([self.root])
        row = result["checkouts"][0]
        self.assertNotIn("commit", row)
        self.assertEqual(len(row["errors"]), 3)
        self.assertNotIn("private", str(result))

    def test_real_git_probe_does_not_write_index_or_working_tree(self):
        folder = self.root / "spine-runtimes"
        folder.mkdir()
        for command in (["git", "init", "-q", str(folder)],
                        ["git", "-C", str(folder), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                         "commit", "-q", "--allow-empty", "-m", "synthetic"]):
            subprocess.run(command, check=True, capture_output=True)
        before = {str(path.relative_to(folder)): path.read_bytes() for path in folder.rglob("*") if path.is_file()}
        result = probe.collect([self.root])
        self.assertEqual(result["checkouts"][0]["errors"], [])
        self.assertEqual(len(result["checkouts"][0]["commit"]), 40)
        self.assertEqual(result["checkouts"][0]["tracked_changes"], [])
        self.assertEqual(result["checkouts"][0]["submodules"], [])
        self.assertEqual(before, {str(path.relative_to(folder)): path.read_bytes() for path in folder.rglob("*") if path.is_file()})


if __name__ == "__main__":
    unittest.main()
