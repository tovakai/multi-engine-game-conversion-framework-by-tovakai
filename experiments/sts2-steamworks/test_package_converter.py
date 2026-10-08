import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

import fetch_converter_runtimes as fetcher
import package_converter
import verify_output
from test_convert_sts2 import pin


class SoftwareDistributionTests(unittest.TestCase):
    def test_fixed_allowlist_reproducible_zip_and_clean_stdlib_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "first.zip", root / "second.zip"
            report = package_converter.package(first)
            package_converter.package(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(report["sha256"], hashlib.sha256(first.read_bytes()).hexdigest())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(set(archive.namelist()), {"sts2-converter/" + name for name in (*package_converter.FILES, "LICENSE")})
                self.assertFalse(any(name.endswith((".dll", ".so", ".pck", ".tpz", ".nupkg")) for name in archive.namelist()))
                archive.extractall(root / "unpacked")
            unpacked = root / "unpacked/sts2-converter"
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            for script in ("convert_sts2.py", "fetch_converter_runtimes.py", "verify_output.py",
                           "pipeline.py", "build_native.py", "preflight.py"):
                # -S removes site packages; the distribution must really be stdlib-only.
                result = subprocess.run([sys.executable, "-S", str(unpacked / script), "--help"], cwd=root,
                                        env=environment, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout)
            before = first.read_bytes()
            with self.assertRaises(OSError):
                package_converter.package(first)
            self.assertEqual(before, first.read_bytes())


class DownloaderTests(unittest.TestCase):
    def test_new_download_checksum_size_guard_and_no_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = b"official synthetic archive"
            profile = {"archives": {"godot": {"pin": pin(raw), "url": "https://example.test/pinned"}}}
            class Response(io.BytesIO):
                def geturl(self):
                    return "https://example.test/pinned"
            with mock.patch.object(fetcher.json, "loads", return_value=profile), mock.patch.object(fetcher.urllib.request, "urlopen", return_value=Response(raw)):
                result = fetcher.fetch(root)
            path = Path(result["godot"])
            self.assertEqual(path.read_bytes(), raw)
            path.unlink()
            for bad in (raw + b"extra", raw[:-1], b"x" * len(raw)):
                with mock.patch.object(fetcher.json, "loads", return_value=profile), mock.patch.object(fetcher.urllib.request, "urlopen", return_value=Response(bad)):
                    with self.assertRaises(ValueError):
                        fetcher.fetch(root)
                self.assertFalse(path.exists())
                self.assertEqual(list(root.iterdir()), [])

    def test_non_https_redirect_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = b"fixture"
            profile = {"archives": {"godot": {"pin": pin(raw), "url": "https://example.test/pinned"}}}
            class Response(io.BytesIO):
                def geturl(self):
                    return "http://example.test/not-secure"
            with mock.patch.object(fetcher.json, "loads", return_value=profile), mock.patch.object(fetcher.urllib.request, "urlopen", return_value=Response(raw)):
                with self.assertRaisesRegex(ValueError, "HTTPS"):
                    fetcher.fetch(directory)
            self.assertEqual(list(Path(directory).iterdir()), [])


class DiagnosticGuardTests(unittest.TestCase):
    def test_manifest_malformed_and_unsafe_records_produce_json_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for value in ([], {"manifest_version": 1, "files": ["bad record"]},
                          {"manifest_version": 1, "files": [{"path": "../escape"}]}):
                (root / verify_output.MANIFEST).write_text(json.dumps(value))
                with mock.patch("sys.stdout", new_callable=io.StringIO) as output:
                    self.assertEqual(verify_output.main([str(root)]), 2)
                    self.assertTrue(json.loads(output.getvalue())["errors"])


if __name__ == "__main__":
    unittest.main()
