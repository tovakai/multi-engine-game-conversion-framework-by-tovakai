from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import probe_spine_build_inputs as probe


class SpineBuildInputTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "spine-runtimes"
        for folder in (self.root, self.root / "spine-godot/godot-cpp"):
            (folder / ".git").mkdir(parents=True)

    def test_scopes_read_only_operations_and_output_bounds(self):
        paths = "\0".join("file " + str(i) for i in range(45)) + "\0"
        with mock.patch.object(probe.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, paths, "")) as run:
            result = probe.collect(self.root)
        self.assertEqual(run.call_count, 10)
        self.assertEqual(result["repositories"][0]["path_scope"], ["spine-godot", "spine-cpp/spine-cpp"])
        self.assertEqual(result["repositories"][1]["path_scope"], [])
        for row in result["repositories"]:
            self.assertEqual(row["untracked_count"], 45)
            self.assertEqual(len(row["untracked_paths"]), 40)
            self.assertTrue(row["untracked_listing_truncated"])
        for call in run.call_args_list:
            self.assertIn("--no-optional-locks", call.args[0])
            self.assertIn("core.fsmonitor=false", call.args[0])
            self.assertEqual(call.kwargs["timeout"], 120)

    def test_failures_withhold_fields_and_private_stderr(self):
        with mock.patch.object(probe.subprocess, "run", side_effect=[
            subprocess.TimeoutExpired("git", 120), OSError("private"),
            subprocess.CompletedProcess([], 128, "", "private")]*4):
            result = probe.collect(self.root)
        self.assertNotIn("private", str(result))
        for row in result["repositories"]:
            self.assertNotIn("commit", row)
            self.assertEqual(len(row["errors"]), 5)

    def test_missing_metadata_and_symlinks_refused(self):
        missing = self.root / "missing"
        linked = self.root / "linked"
        linked.symlink_to(self.root, target_is_directory=True)
        with mock.patch.object(probe.subprocess, "run") as run:
            self.assertTrue(probe.collect(missing)["repositories"][0]["errors"])
            self.assertTrue(probe.collect(linked)["repositories"][0]["errors"])
            run.assert_not_called()

    def test_real_git_status_finds_changes_without_modifying_metadata(self):
        for folder in (self.root, self.root / "spine-godot/godot-cpp"):
            subprocess.run(["git", "init", "-q", str(folder)], check=True, capture_output=True)
            file = folder / "spine-godot/build/input.txt" if folder == self.root else folder / "input.txt"
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("original\n")
            subprocess.run(["git", "-C", str(folder), "add", str(file)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(folder), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                            "commit", "-q", "-m", "synthetic"], check=True, capture_output=True)
            file.write_text("changed\n")
            (file.parent / "new.txt").write_text("untracked\n")
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result = probe.collect(self.root)
        for row in result["repositories"]:
            self.assertEqual(row["errors"], [])
            self.assertEqual(len(row["tracked_changes"]), 1)
            self.assertGreater(row["untracked_count"], 0)
            self.assertEqual(len(row["commit"]), 40)
        self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})


if __name__ == "__main__":
    unittest.main()
