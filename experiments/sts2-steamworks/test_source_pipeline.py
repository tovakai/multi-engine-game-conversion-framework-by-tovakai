import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import io
import tarfile
from unittest import mock

import build_native
import pipeline
import preflight
import sdk_archive


def pin(raw):
    return {"size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


class SourcePipelineTests(unittest.TestCase):
    def test_malformed_release_is_a_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for raw in (b"[]", b"null", b"{broken", b"\xff"):
                (root / "release_info.json").write_bytes(raw)
                report = preflight.inspect_source(root)
                self.assertFalse(report["supported"])
                self.assertTrue(report["errors"])

    def test_complete_source_hash_validation_and_multiple_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release = json.dumps({"version": "v0.98.2", "commit": "f4eeecc6"}).encode()
            (root / "release_info.json").write_bytes(release)
            (root / "SlayTheSpire2.pck").write_bytes(b"pack")
            profile = {"release": "v0.98.2", "commit": "f4eeecc6",
                       "copy_files": [{"source": "release_info.json", **pin(release)},
                                      {"source": "missing.dll", **pin(b"missing")}],
                       "managed_inputs": {}, "pack": pin(b"different")}
            before = (root / "SlayTheSpire2.pck").read_bytes()
            report = preflight.inspect_source(root, profile=profile)
            self.assertTrue(report["supported"])
            self.assertFalse(report["source_verified"])
            self.assertEqual(len(report["errors"]), 2)
            self.assertEqual((root / "SlayTheSpire2.pck").read_bytes(), before)
            (root / "missing.dll").write_bytes(b"missing")
            profile["pack"] = pin(before)
            self.assertTrue(preflight.inspect_source(root, profile=profile)["source_verified"])

    def test_unsupported_source_never_downloads_or_builds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "release_info.json").write_text('{"version":"v0.107.1","commit":"59260271"}')
            with mock.patch.object(pipeline, "fetch") as fetch, mock.patch.object(pipeline, "build") as build:
                with self.assertRaisesRegex(ValueError, "Unsupported STS2 build"):
                    pipeline.run(source, root / "output", sdk=root / "sdk", cache=root / "cache", authorized=True)
                fetch.assert_not_called()
                build.assert_not_called()
            self.assertFalse((root / "cache").exists())
            self.assertFalse((root / "output").exists())

    def test_sdk_relative_vendor_alias_allowed_escape_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sdk = root / "sdk"
            sdk.mkdir()
            (sdk / "library.14.15").write_bytes(b"vendor")
            (sdk / "library.14").symlink_to("library.14.15")
            self.assertEqual(build_native.sdk_file(sdk, "library.14"), sdk / "library.14.15")
            (root / "outside").write_bytes(b"outside")
            (sdk / "escape").symlink_to("../outside")
            with self.assertRaisesRegex(ValueError, "escapes"):
                build_native.sdk_file(sdk, "escape")

    def test_existing_checkout_not_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = root / "checkout"
            checkout.mkdir()
            (checkout / "previous.so").write_bytes(b"previous artifact")
            with mock.patch.object(build_native, "command") as run:
                with self.assertRaisesRegex(ValueError, "not empty"):
                    build_native.checkout("https://example.test/source", "a" * 40, checkout, root / "log")
                run.assert_not_called()

    def test_all_sdk_headers_are_pinned_including_cpp_wrappers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "api/core/inc").mkdir(parents=True)
            header = root / "api/core/inc/fmod.hpp"
            header.write_bytes(b"original C++ wrapper")
            (header.parent / "fmod.cs").write_bytes(b"unused vendor C# wrapper")
            (root / "api/fsbank/inc").mkdir(parents=True)
            (root / "api/fsbank/inc/fsbank.h").write_bytes(b"unused bank compiler")
            pins = {"api/core/inc/fmod.hpp": pin(header.read_bytes())}
            with mock.patch.object(build_native.json, "loads", return_value=pins):
                self.assertEqual(build_native.sdk_headers(root)["api/core/inc/fmod.hpp"], b"original C++ wrapper")
                header.write_bytes(b"modified C++ wrapper")
                with self.assertRaises(ValueError):
                    build_native.sdk_headers(root)
                (header.parent / "extra.hpp").write_bytes(b"unexpected")
                with self.assertRaisesRegex(ValueError, "inventory"):
                    build_native.sdk_headers(root)

    def test_cache_cannot_modify_original_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            with self.assertRaisesRegex(ValueError, "Cache must be separate"):
                pipeline.run(source, root / "output", sdk=root / "sdk", cache=source / "cache", authorized=True)

    def test_vendor_archive_selects_headers_and_arm64_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "vendor.tar.gz"
            files = {"core/inc/fmod.hpp": b"header", "core/lib/arm64/libfmod.so.14.15": b"core",
                     "studio/lib/arm64/libfmodstudio.so.14.15": b"studio", "core/lib/x86_64/libfmod.so": b"excluded"}
            with tarfile.open(archive, "w:gz") as package:
                for name, raw in files.items():
                    member = tarfile.TarInfo(sdk_archive.PREFIX + name)
                    member.size = len(raw)
                    package.addfile(member, io.BytesIO(raw))
            with mock.patch.object(sdk_archive, "PIN", pin(archive.read_bytes())):
                sdk = sdk_archive.prepare_sdk(archive, root / "sdk")
            self.assertEqual((sdk / "api/core/inc/fmod.hpp").read_bytes(), b"header")
            self.assertEqual((sdk / "api/core/lib/arm64/libfmod.so.14").read_bytes(), b"core")
            self.assertFalse((sdk / "api/core/lib/x86_64").exists())
            self.assertFalse(any(p.is_symlink() for p in sdk.rglob("*")))

    def test_vendor_archive_traversal_never_extracts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "vendor.tar.gz"
            with tarfile.open(archive, "w:gz") as package:
                package.addfile(tarfile.TarInfo("../escape"), io.BytesIO())
            with mock.patch.object(sdk_archive, "PIN", pin(archive.read_bytes())):
                with self.assertRaisesRegex(ValueError, "Unsafe"):
                    sdk_archive.prepare_sdk(archive, root / "sdk")
            self.assertFalse((root / "sdk").exists())


if __name__ == "__main__":
    unittest.main()
