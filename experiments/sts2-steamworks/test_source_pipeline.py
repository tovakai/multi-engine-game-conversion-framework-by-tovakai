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
from test_convert_sts2 import elf


def pin(raw):
    return {"size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


class SourcePipelineTests(unittest.TestCase):
    def test_native_build_reaches_both_compilers_with_verified_sdk_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sdk, work = root / "sdk", root / "work"
            headers = {"api/core/inc/fmod.hpp": b"core C++ header",
                       "api/core/inc/fmod_common.h": b"core C header",
                       "api/studio/inc/fmod_studio.hpp": b"studio C++ header"}
            for name, raw in headers.items():
                path = sdk / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            (root / "fmod_sdk_headers_v1.json").write_text(json.dumps({n: pin(raw) for n, raw in headers.items()}))
            vendor = {"libfmod.so.14": elf("core runtime"),
                      "libfmodstudio.so.14": elf("studio runtime")}
            for section, basename in (("core", "libfmod"), ("studio", "libfmodstudio")):
                lib = sdk / f"api/{section}/lib/arm64"
                lib.mkdir(parents=True)
                (lib / (basename + ".so.14.15")).write_bytes(vendor[basename + ".so.14"])
                (lib / (basename + ".so.14")).symlink_to(basename + ".so.14.15")
            steam = root / "steam.so"
            steam.write_bytes(elf("official platform fixture"))
            extension_names = ("libspine_godot.linux.template_release.arm64.so",
                               "libGodotFmod.linux.template_release.arm64.so")
            outputs = {**vendor, "libsteam_api64.so": steam.read_bytes(),
                       **{n: elf(n) for n in extension_names}}
            profile = {"native_files": [{"provider_name": n, **pin(raw)} for n, raw in outputs.items()]}

            def checkout(url, commit, destination, log):
                destination.mkdir(parents=True, exist_ok=True)
                if destination.name == "spine-runtimes":
                    (destination / "spine-cpp/spine-cpp").mkdir(parents=True)
                    (destination / "spine-cpp/spine-cpp/fixture.h").write_bytes(b"source")
                    (destination / "spine-godot/spine_godot").mkdir(parents=True)
                if destination.name == "fmod-gdextension":
                    for name in build_native.RECIPES:
                        path = destination / name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(b"source patch fixture")

            compiled = []
            def compile_source(args, cwd, log, env=None):
                compiled.append(cwd.name)
                for section, basename in (("core", "libfmod"), ("studio", "libfmodstudio")):
                    layout = work / "sdk-layout/linux" / section
                    for suffix in (".so", ".so.14"):
                        self.assertEqual((layout / "lib/arm64" / (basename + suffix)).read_bytes(), vendor[basename + ".so.14"])
                    expected = {Path(n).name: raw for n, raw in headers.items() if n.startswith(f"api/{section}/inc/")}
                    self.assertEqual({p.name: p.read_bytes() for p in (layout / "inc").iterdir()}, expected)
                self.assertIn("arch=arm64", args)
                self.assertIn("target=template_release", args)
                if cwd.name == "spine-godot":
                    target = cwd / "bin/linux" / extension_names[0]
                else:
                    self.assertIn("fmod_lib_dir=" + str(work / "sdk-layout") + "/", args)
                    target = cwd / "demo/addons/fmod/libs/linux" / extension_names[1]
                target.parent.mkdir(parents=True)
                target.write_bytes(outputs[target.name])

            def tool_output(args, **kwargs):
                if "--dyn-syms" in args:
                    symbol = "spine_godot_library_init" if "spine" in str(args[-1]) else "fmod_library_init"
                    return "1: 00001000 10 FUNC GLOBAL DEFAULT 11 " + symbol + "\n"
                return "synthetic tool output\n"

            with mock.patch.object(build_native, "HERE", root), \
                 mock.patch.object(build_native, "load_profile", return_value=profile), \
                 mock.patch.object(build_native.platform, "system", return_value="Linux"), \
                 mock.patch.object(build_native.platform, "machine", return_value="aarch64"), \
                 mock.patch.object(build_native.shutil, "which", side_effect=lambda name: name), \
                 mock.patch.object(build_native, "checkout", side_effect=checkout), \
                 mock.patch.object(build_native, "adapt_sources", side_effect=lambda resources: (resources, {"fixture": True})), \
                 mock.patch.object(build_native, "command", side_effect=compile_source), \
                 mock.patch.object(build_native.subprocess, "check_output", side_effect=tool_output):
                native, generated_profile, evidence = build_native.build(work, sdk, steam_api=steam)
            self.assertEqual(compiled, ["spine-godot", "fmod-gdextension"])
            self.assertEqual({p.name: p.read_bytes() for p in native.iterdir()}, outputs)
            self.assertTrue(all(evidence["matches_previous_extension_hashes"].values()))
            self.assertTrue((work / "native-build.json").is_file())
            self.assertEqual(generated_profile["native_files"], profile["native_files"])

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
            (source / "release_info.json").write_text('{"version":"v0.999.0","commit":"unsupported"}')
            with mock.patch.object(pipeline, "fetch") as fetch, mock.patch.object(pipeline, "build") as build:
                with self.assertRaisesRegex(ValueError, "Unsupported STS2 build"):
                    pipeline.run(source, root / "output", sdk=root / "sdk", cache=root / "cache")
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
                pipeline.run(source, root / "output", sdk=root / "sdk", cache=source / "cache")

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
