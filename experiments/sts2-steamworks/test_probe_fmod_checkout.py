from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import probe_fmod_checkout as probe


class FmodCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.folder = self.root / "extension"
        (self.folder / ".git").mkdir(parents=True)

    def test_bounded_diff_only_for_expected_commit_and_no_sdk_contents(self):
        diff = "synthetic patch\n" * 1000
        def metadata(folder, *args):
            if args[:2] == ("rev-parse", "HEAD"): return probe.EXPECTED
            if args[0] == "diff": return diff
            return ""
        with mock.patch.object(probe, "git", side_effect=metadata) as git:
            result = probe.collect(self.root)
        row = result["repositories"][0]
        self.assertTrue(row["matches_expected_extension_commit"])
        self.assertTrue(row["sconstruct_diff_truncated"])
        self.assertEqual(len(row["sconstruct_diff"]), 8192)
        args = git.call_args_list[-1].args
        self.assertIn("--no-ext-diff", args)
        self.assertIn("--no-textconv", args)
        self.assertEqual(args[-1], "SConstruct")
        with mock.patch.object(probe, "git", return_value="unknown") as git:
            result = probe.collect(self.root)
            self.assertNotIn("sconstruct_diff", result["repositories"][0])
            self.assertFalse(any("diff" in call.args for call in git.call_args_list))

    def test_search_bounds_skips_and_symlink_refusal(self):
        sdk = self.root / "sdk-layout" / "sdk-repo"
        (sdk / ".git").mkdir(parents=True)
        linked = self.root / "linked"
        linked.symlink_to(self.folder, target_is_directory=True)
        with mock.patch.object(probe, "git", return_value=""):
            result = probe.collect(self.root)
        self.assertEqual(len(result["repositories"]), 1)
        self.assertEqual(probe.collect(linked)["repositories"], [])
        with mock.patch.object(probe.os, "walk", return_value=[(str(self.root), [], [])] * 501):
            self.assertTrue(probe.collect(self.root)["search_incomplete"])

    def test_private_failures_withheld_and_command_uses_optional_lock_guard(self):
        with mock.patch.object(probe, "git", side_effect=OSError("private")):
            result = probe.collect(self.root)
        self.assertNotIn("private", str(result))
        self.assertEqual(len(result["repositories"][0]["errors"]), 5)
        with mock.patch.object(probe.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run:
            probe.git(self.folder, "rev-parse", "HEAD")
        self.assertIn("--no-optional-locks", run.call_args.args[0])
        self.assertIn("core.fsmonitor=false", run.call_args.args[0])

    def test_real_modified_checkout_and_metadata_preserved(self):
        subprocess.run(["git", "init", "-q", str(self.folder)], check=True, capture_output=True)
        source = self.folder / "SConstruct"
        source.write_text("synthetic original\n")
        subprocess.run(["git", "-C", str(self.folder), "add", "SConstruct"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.folder), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                        "commit", "-q", "-m", "synthetic"], check=True, capture_output=True)
        commit = subprocess.run(["git", "-C", str(self.folder), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        source.write_text("synthetic changed\n")
        (self.folder / "custom.py").write_text("never execute this\n")
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with mock.patch.object(probe, "EXPECTED", commit):
            result = probe.collect(self.root)
        row = result["repositories"][0]
        self.assertEqual(row["errors"], [])
        self.assertEqual(row["tracked_changes"], ["M SConstruct"])
        self.assertIn("+synthetic changed", row["sconstruct_diff"])
        self.assertEqual(row["untracked_build_paths"], ["custom.py"])
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})


if __name__ == "__main__":
    unittest.main()
