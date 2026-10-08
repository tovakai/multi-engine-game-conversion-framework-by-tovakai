import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import probe_fmod_header as probe


class FmodHeaderTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / ".git").mkdir()
        for name in probe.FILES:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"synthetic current\r\n")

    def metadata(self, root, *args):
        return {"rev-parse": probe.EXPECTED.encode(), "show": b"synthetic base\r\n", "diff": b"synthetic diff\r\n"}[args[0]]

    def test_raw_hashes_guarded_paths_and_no_writes(self):
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with mock.patch.object(probe, "git", side_effect=self.metadata) as git:
            result = probe.collect(self.root)
        self.assertEqual(result["errors"], [])
        self.assertEqual([row["path"] for row in result["files"]], list(probe.FILES))
        for row in result["files"]:
            self.assertEqual(row["current_sha256"], hashlib.sha256(b"synthetic current\r\n").hexdigest())
            self.assertEqual(row["base_sha256"], hashlib.sha256(b"synthetic base\r\n").hexdigest())
            self.assertEqual(row["diff_sha256"], hashlib.sha256(b"synthetic diff\r\n").hexdigest())
            self.assertFalse(row["diff_truncated"])
        for call in git.call_args_list:
            if call.args[1] == "diff":
                self.assertIn("--no-ext-diff", call.args)
                self.assertIn("--no-textconv", call.args)
                self.assertIn(call.args[-1], probe.FILES)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_unknown_commit_timeouts_and_symlinks_withhold_contents(self):
        with mock.patch.object(probe, "git", return_value=b"unknown") as git:
            result = probe.collect(self.root)
        self.assertEqual(result["files"], [])
        self.assertEqual(git.call_count, 1)
        with mock.patch.object(probe, "git", side_effect=subprocess.TimeoutExpired("private", 120)):
            self.assertNotIn("private", str(probe.collect(self.root)))
        link = self.root / "link"
        link.symlink_to(self.root, target_is_directory=True)
        with mock.patch.object(probe, "git") as git:
            self.assertEqual(probe.collect(link)["files"], [])
            git.assert_not_called()

    def test_size_concurrent_change_and_diff_limits(self):
        with mock.patch.object(probe, "git", side_effect=self.metadata), mock.patch.object(probe, "read", side_effect=[b"a", b"b", b"a", b"b"]):
            result = probe.collect(self.root)
        self.assertEqual(result["files"], [])
        self.assertEqual(len(result["errors"]), 2)
        def oversized_diff(root, *args):
            return b"x" * 9000 if args[0] == "diff" else self.metadata(root, *args)
        with mock.patch.object(probe, "git", side_effect=oversized_diff):
            result = probe.collect(self.root)
        for row in result["files"]:
            self.assertEqual(len(row["diff"]), 8192)
            self.assertTrue(row["diff_truncated"])
        with (self.root / probe.FILES[0]).open("wb") as stream:
            stream.truncate(1048577)
        with self.assertRaisesRegex(ValueError, "oversized"):
            probe.read(self.root / probe.FILES[0])

    def test_archived_guard_diff_hash_and_additional_change_are_preserved(self):
        observation = json.loads((Path(__file__).parent / "fmod_checkout_observation_v1.json").read_text())
        self.assertEqual(observation["errors"], [])
        self.assertFalse(observation["search_incomplete"])
        outer, nested = observation["repositories"]
        self.assertEqual(outer["commit"], probe.EXPECTED)
        self.assertEqual(nested["commit"], "e83fd0904c13356ed1d4c3d09f8bb9132bdc6b77")
        self.assertEqual(hashlib.sha256(outer["sconstruct_diff"].encode()).hexdigest(), outer["sconstruct_diff_sha256"])
        self.assertFalse(outer["sconstruct_diff_truncated"])
        self.assertIn('+    if env["arch"] != "arm64":', outer["sconstruct_diff"])
        self.assertIn("src/helpers/common.h", "\n".join(outer["tracked_changes"]))

    def test_real_git_with_staged_and_unstaged_edits_preserves_metadata(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "add", "SConstruct", "src/helpers/common.h"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                        "commit", "-q", "-m", "synthetic"], check=True, capture_output=True)
        commit = probe.git(self.root, "rev-parse", "HEAD").decode().strip()
        for name in probe.FILES: (self.root / name).write_bytes(b"changed source\n")
        subprocess.run(["git", "-C", str(self.root), "add", "SConstruct"], check=True, capture_output=True)
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with mock.patch.object(probe, "EXPECTED", commit): result = probe.collect(self.root)
        self.assertEqual(result["errors"], [])
        self.assertEqual(len(result["files"]), 2)
        for row in result["files"]: self.assertIn("+changed source", row["diff"])
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})


if __name__ == "__main__":
    unittest.main()
