import copy
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock
import zipfile

import convert_sts2 as converter
import converter_io
import fetch_converter_runtimes as fetcher
import patch_pack
import patch_stats
from test_patch_pack import adapt, FMOD, SENTRY, SPINE, LIST
from test_probe_packed_extensions import make_pack
from verify_output import verify


def pin(raw):
    return {"size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def elf(label):
    result = bytearray(64)
    result[:6] = b"\x7fELF\x02\x01"
    result[18:20] = b"\xb7\0"
    return bytes(result) + label.encode()


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "clean game"
        self.native = self.root / "authorized dependencies"
        self.output = self.root / "converted game"
        self.source.mkdir()
        self.native.mkdir()
        self.profile = copy.deepcopy(converter.load_profile())
        self.archives = {}
        for item in self.profile["copy_files"]:
            raw = b"unchanged fixture: " + item["source"].encode()
            item.update(pin(raw))
            self.write_source(item["source"], raw)
        for name, item in self.profile["managed_inputs"].items():
            raw = b"synthetic original " + name.encode()
            item.update(pin(raw))
            self.write_source(converter.SOURCE_DATA + "/" + name, raw)
        for item in self.profile["native_files"]:
            raw = elf(item["provider_name"])
            item.update(pin(raw))
            (self.native / item["provider_name"]).write_bytes(raw)
        self.resources = {FMOD: b"before_fmod", SENTRY: b"before_sentry", SPINE: b"unchanged_spine", LIST: b"",
                          "assets/data.txt": b"untouched_asset\n", "project.godot": b'[application]\nconfig/name="Converter Smoke"\n',
                          "smoke.gd": b'''extends SceneTree
func _initialize():
    assert(FileAccess.get_file_as_string("res://assets/data.txt").strip_edges() == "untouched_asset")
    assert(FileAccess.get_file_as_string("res://addons/fmod/fmod.gdextension") == "after_fmod")
    print("CONVERTER_PACK_SMOKE_OK")
    quit()
'''}
        self.pack = make_pack(list(self.resources.items()), base=128, directory=8192)
        self.profile["pack"] = pin(self.pack)
        self.write_source("SlayTheSpire2.pck", self.pack)
        for key, recipe in self.profile["archives"].items():
            path = self.root / (key + ".zip")
            with zipfile.ZipFile(path, "w") as archive:
                for item in recipe["members"]:
                    name = item["destination"]
                    raw = elf(name) if name.endswith(".so") or ".so." in name or converter.executable(name) else b"fixture " + name.encode()
                    item.update(pin(raw))
                    archive.writestr(item["member"], raw)
                archive.writestr("../unselected-unsafe-name", b"not extracted")
            recipe["pin"] = pin(path.read_bytes())
            self.archives[key] = path
        self.prepare = mock.patch.object(converter, "prepare_pair", side_effect=lambda game, wrapper: {
            "sts2.dll": b"patched game", "Steamworks.NET.dll": b"patched wrapper"})
        self.deps = mock.patch.object(converter, "adapt_deps", return_value=b'{"fixture": "linux-arm64"}')
        self.prepare.start()
        self.deps.start()
        self.addCleanup(self.prepare.stop)
        self.addCleanup(self.deps.stop)

    def write_source(self, name, raw):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    def run_conversion(self, **kwargs):
        return converter.convert(self.source, kwargs.pop("output", self.output), self.native, self.archives,
                                 authorized=kwargs.pop("authorized", True), _profile=self.profile,
                                 _pack_transform=adapt, **kwargs)

    def snapshot(self, root):
        return {p.relative_to(root).as_posix(): pin(p.read_bytes()) for p in root.rglob("*") if p.is_file()}

    def assert_no_stage(self):
        self.assertFalse(list(self.root.glob(".sts2-conversion-*")))

    def test_complete_conversion_preserves_source_and_excludes_unselected_files(self):
        for path in ["data_sts2_windows_x86_64/steam_api64.dll", "data_sts2_windows_x86_64/steam_settings/stats.txt",
                     "SlayTheSpire2.exe", "save.dat", "unknown.dll"]:
            self.write_source(path, b"must not be deployed")
        before = self.snapshot(self.source)
        report = self.run_conversion()
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["validation"]["errors"], [])
        self.assertEqual(self.snapshot(self.source), before)
        manifest = json.loads((self.output / "conversion-manifest.json").read_bytes())
        expected = len(self.profile["copy_files"]) + len(self.profile["native_files"]) + len(self.profile["legal_files"]) + 3 + 1 + 4 + sum(len(v["members"]) for v in self.profile["archives"].values())
        self.assertEqual(len(manifest["files"]), expected)
        self.assertEqual(verify(self.output, check_modes=True)["errors"], [])
        for path in before:
            if path.endswith(".exe") or "steam_settings" in path or path in {"save.dat", "unknown.dll"}:
                self.assertFalse((self.output / path).exists())
        for item in self.profile["copy_files"]:
            self.assertEqual((self.output / item["destination"]).read_bytes(), (self.source / item["source"]).read_bytes())
        self.assertEqual((self.output / converter.DATA / "sts2.dll").read_bytes(), b"patched game")
        self.assert_no_stage()

    def test_existing_output_and_in_place_or_nested_outputs_refused(self):
        self.output.mkdir()
        (self.output / "user.txt").write_text("untouched")
        with self.assertRaisesRegex(ValueError, "exists"):
            self.run_conversion()
        self.assertEqual((self.output / "user.txt").read_text(), "untouched")
        for path in [self.source, self.source / "converted", self.native / "converted"]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.run_conversion(output=path)
        self.assert_no_stage()

    def test_authorization_required(self):
        with self.assertRaisesRegex(ValueError, "Acknowledge"):
            self.run_conversion(authorized=False)
        self.assertFalse(self.output.exists())

    def test_source_copy_managed_native_and_archive_corruption_refused(self):
        paths = [self.source / self.profile["copy_files"][0]["source"],
                 self.source / converter.SOURCE_DATA / "sts2.dll",
                 self.native / self.profile["native_files"][0]["provider_name"], self.archives["dotnet"]]
        for path in paths:
            original = path.read_bytes()
            path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "SHA-256"):
                self.run_conversion()
            path.write_bytes(original)
            self.assertFalse(self.output.exists())
            self.assert_no_stage()

    def test_pack_hash_failure_after_staging_cleans_everything(self):
        self.profile["pack"]["sha256"] = "0" * 64
        before = self.snapshot(self.source)
        with self.assertRaisesRegex(ValueError, "Source hash"):
            self.run_conversion()
        self.assertFalse(self.output.exists())
        self.assertEqual(before, self.snapshot(self.source))
        self.assert_no_stage()

    def test_wrong_native_architecture_even_with_test_hash_refused(self):
        item = self.profile["native_files"][0]
        raw = bytearray((self.native / item["provider_name"]).read_bytes())
        raw[18:20] = b"\x3e\0"
        (self.native / item["provider_name"]).write_bytes(raw)
        item.update(pin(raw))
        with self.assertRaisesRegex(ValueError, "AArch64"):
            self.run_conversion()
        self.assert_no_stage()

    def test_selected_archive_symlink_duplicate_encryption_and_member_hash_guard(self):
        recipe = self.profile["archives"]["godot"]
        member = recipe["members"][0]
        path = self.archives["godot"]
        for variant in ("symlink", "duplicate", "hash", "traversal"):
            with self.subTest(variant=variant):
                info = zipfile.ZipInfo(member["member"])
                info.create_system = 3
                info.external_attr = (0o120777 if variant == "symlink" else 0o100644) << 16
                raw = elf(member["destination"])
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr(info, raw)
                    if variant == "duplicate":
                        archive.writestr(info, raw)
                recipe["pin"] = pin(path.read_bytes())
                member["sha256"] = "0" * 64 if variant == "hash" else pin(raw)["sha256"]
                old_name = member["destination"]
                if variant == "traversal":
                    member["destination"] = "../escape"
                with self.assertRaises(ValueError):
                    self.run_conversion()
                member["destination"] = old_name
                self.assertFalse(self.output.exists())
                self.assertFalse((self.root / "escape").exists())
                self.assert_no_stage()

    def test_output_collision_at_publication_preserves_concurrent_user_directory(self):
        real = converter.publish_new
        def race(stage, output):
            output.mkdir()
            return real(stage, output)
        with mock.patch.object(converter, "publish_new", side_effect=race):
            with self.assertRaises(OSError):
                self.run_conversion()
        self.assertTrue(self.output.is_dir())
        self.assertEqual(list(self.output.iterdir()), [])
        self.assert_no_stage()

    def test_disk_or_validation_failure_leaves_no_output(self):
        with mock.patch.object(converter, "write_new", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.run_conversion()
        with mock.patch.object(converter, "verify", return_value={"errors": ["fixture integrity failure"]}):
            with self.assertRaisesRegex(ValueError, "verification"):
                self.run_conversion()
        self.assertFalse(self.output.exists())
        self.assert_no_stage()

    def test_symlink_inputs_parents_and_destination_refused(self):
        link = self.root / "linked"
        link.symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Symbolic"):
            converter.convert(link, self.output, self.native, self.archives, authorized=True, _profile=self.profile)
        self.output.symlink_to(self.root / "missing")
        with self.assertRaisesRegex(ValueError, "Symbolic"):
            self.run_conversion()

    def test_output_tampering_unexpected_files_permissions_and_symlinks_detected(self):
        self.run_conversion()
        path = self.output / "SlayTheSpire2"
        path.write_bytes(b"changed")
        (self.output / "steam_settings").mkdir()
        (self.output / "steam_settings/config.ini").write_text("unexpected")
        (self.output / "linked").symlink_to(self.source)
        errors = verify(self.output, check_modes=True)["errors"]
        self.assertTrue(any(e["path"] == "SlayTheSpire2" for e in errors))
        self.assertTrue(any(e["path"] == "steam_settings/config.ini" for e in errors))
        self.assertTrue(any(e["path"] == "linked" for e in errors))

    def test_transfer_archive_round_trip_hashes_and_linux_modes(self):
        self.run_conversion()
        archive = self.root / "transfer.tar"
        result = converter.create_tar(self.output, archive)
        self.assertEqual(result["sha256"], pin(archive.read_bytes())["sha256"])
        restored = self.root / "restored"
        restored.mkdir()
        with tarfile.open(archive) as packaged:
            for item in packaged.getmembers():
                self.assertTrue(item.isfile())
                self.assertTrue(item.name.startswith("sts2-arm64/"))
                self.assertNotIn("..", Path(item.name).parts)
                name = item.name.removeprefix("sts2-arm64/")
                self.assertEqual(item.mode, 0o755 if converter.executable(name) else 0o644)
                target = restored / item.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(packaged.extractfile(item).read())
                target.chmod(item.mode)
        self.assertEqual(verify(restored / "sts2-arm64", check_modes=True)["errors"], [])
        with self.assertRaisesRegex(ValueError, "new"):
            converter.create_tar(self.output, archive)
        self.assertEqual(result["sha256"], pin(archive.read_bytes())["sha256"])

    def test_pck_staging_does_not_require_hardlinks(self):
        with mock.patch.object(patch_pack.os, "link", side_effect=OSError("hardlinks unsupported")):
            self.run_conversion()
        self.assertEqual(verify(self.output)["errors"], [])

    def test_json_cli_complete_workflow_and_bad_inputs(self):
        args = [str(self.source), str(self.output), "--native-dir", str(self.native), "--godot-templates", str(self.archives["godot"]),
                "--dotnet-runtime", str(self.archives["dotnet"]), "--sentry-archive", str(self.archives["sentry"]), "--acknowledge-licenses", "--tar", str(self.root / "transfer.tar")]
        real_rewrite = converter.rewrite_pack
        def synthetic_rewrite(*args, **kwargs):
            return real_rewrite(*args, **kwargs, transform=adapt)
        with mock.patch.object(converter, "load_profile", return_value=self.profile), mock.patch.object(converter, "rewrite_pack", side_effect=synthetic_rewrite), mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(converter.main(args), 0)
            result = json.loads(output.getvalue())
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["validation"]["errors"], [])
        with mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(converter.main(args), 2)
            self.assertTrue(json.loads(output.getvalue())["errors"])

    def test_generated_scripts_parse_and_launcher_does_not_invent_steam_context(self):
        self.run_conversion()
        for name in ("launch.sh", "collect-startup.sh"):
            self.assertEqual(subprocess.run(["bash", "-n", str(self.output / name)], capture_output=True).returncode, 0)
        environment = dict(os.environ)
        environment.pop("SteamAppId", None)
        result = subprocess.run(["bash", str(self.output / "launch.sh")], capture_output=True, text=True, env=environment)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("export SteamAppId", converter.LAUNCH.decode())
        self.assertNotIn("export SteamGameId", converter.LAUNCH.decode())
        self.assertNotIn("LD_PRELOAD", converter.LAUNCH.decode())

    @unittest.skipUnless(os.environ.get("STS2_GODOT_PACK_TEST_ENGINE"), "Independent Godot reader not supplied")
    def test_official_engine_reads_complete_converter_output_pack(self):
        self.run_conversion()
        environment = dict(os.environ, GODOT_SILENCE_ROOT_WARNING="1", XDG_CACHE_HOME=str(self.root / "cache"),
                           XDG_CONFIG_HOME=str(self.root / "config"), XDG_DATA_HOME=str(self.root / "data"))
        result = subprocess.run([os.environ["STS2_GODOT_PACK_TEST_ENGINE"], "--headless", "--main-pack",
                                 str(self.output / "SlayTheSpire2.pck"), "--script", "res://smoke.gd"],
                                env=environment, cwd=self.output, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CONVERTER_PACK_SMOKE_OK", result.stdout)


class InputIoTests(unittest.TestCase):
    def test_input_changes_during_stream_use_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            path.write_bytes(b"original")
            with self.assertRaisesRegex(ValueError, "changed"):
                with converter_io.verified_stream(path, pin(b"original")):
                    path.write_bytes(b"modified")

    def test_no_replace_publication_does_not_replace_an_empty_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "stage").mkdir()
            (root / "existing").mkdir()
            with self.assertRaises(OSError):
                converter_io.publish_new(root / "stage", root / "existing")
            self.assertTrue((root / "stage").is_dir())
            self.assertTrue((root / "existing").is_dir())

    def test_runtime_fetch_reuses_verified_cache_and_preserves_wrong_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = {"archives": {"godot": {"pin": pin(b"fixture"), "url": "https://example.test/archive"}}}
            path = root / "Godot_v4.5.1-stable_mono_export_templates.tpz"
            path.write_bytes(b"fixture")
            with mock.patch.object(fetcher.json, "loads", return_value=profile), mock.patch.object(fetcher.urllib.request, "urlopen") as network:
                self.assertEqual(fetcher.fetch(root)["godot"], str(path))
                network.assert_not_called()
                path.write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    fetcher.fetch(root)
                self.assertEqual(path.read_bytes(), b"changed")


@unittest.skipUnless(all(os.environ.get(k) for k in ("STS2_GAME_DLL", "STS2_WRAPPER_DLL", "STS2_SOURCE_DEPS",
                         "STS2_GODOT_MONO_TEMPLATES", "STS2_DOTNET_RUNTIME_PACKAGE", "STS2_SENTRY_ARCHIVE", "STS2_NATIVE_LIBRARY")),
                     "Real inspected managed inputs and official archives not supplied")
class OfficialArtifactPipelineTests(unittest.TestCase):
    setUp = ConversionTests.setUp
    write_source = ConversionTests.write_source
    run_conversion = ConversionTests.run_conversion
    snapshot = ConversionTests.snapshot
    def actual_inputs(self):
        self.prepare.stop()
        self.deps.stop()
        def windows(raw):
            header = struct.unpack_from("<I", raw, 60)[0]
            return raw[:header + 4] + b"\x64\x86" + raw[header + 6:]
        for name, variable in [("sts2.dll", "STS2_GAME_DLL"), ("Steamworks.NET.dll", "STS2_WRAPPER_DLL")]:
            self.write_source(converter.SOURCE_DATA + "/" + name, windows(Path(os.environ[variable]).read_bytes()))
            self.profile["managed_inputs"][name] = converter.load_profile()["managed_inputs"][name]
        self.write_source(converter.SOURCE_DATA + "/sts2.deps.json", Path(os.environ["STS2_SOURCE_DEPS"]).read_bytes())
        self.profile["managed_inputs"]["sts2.deps.json"] = converter.load_profile()["managed_inputs"]["sts2.deps.json"]
        self.profile["archives"] = converter.load_profile()["archives"]
        self.archives = {"godot": Path(os.environ["STS2_GODOT_MONO_TEMPLATES"]),
                         "dotnet": Path(os.environ["STS2_DOTNET_RUNTIME_PACKAGE"]), "sentry": Path(os.environ["STS2_SENTRY_ARCHIVE"])}
        steam = self.profile["native_files"][-1]
        steam.update(pin(Path(os.environ["STS2_NATIVE_LIBRARY"]).read_bytes()))
        (self.native / steam["provider_name"]).write_bytes(Path(os.environ["STS2_NATIVE_LIBRARY"]).read_bytes())

    def test_real_recipes_and_official_archives_in_complete_pipeline(self):
        self.actual_inputs()
        before = self.snapshot(self.source)
        report = self.run_conversion()
        self.assertEqual(report["validation"]["errors"], [])
        self.assertEqual(pin((self.output / converter.DATA / "sts2.dll").read_bytes())["sha256"], patch_stats.GAME_TARGET)
        self.assertEqual(pin((self.output / converter.DATA / "Steamworks.NET.dll").read_bytes())["sha256"], patch_stats.WRAPPER_TARGET)
        self.assertEqual(len([p for p in (self.output / converter.DATA).glob("*")]), 205)
        self.assertEqual(before, self.snapshot(self.source))
        self.assertEqual(verify(self.output)["errors"], [])

    def test_relocated_software_bundle_real_cli_without_site_packages(self):
        import package_converter
        self.actual_inputs()
        capture = Path(converter.__file__).parent / "prototype_packed_extensions_v1.json"
        if not capture.exists():
            self.skipTest("Actual packed-manifest capture not supplied")
        before = next(item for item in json.loads(capture.read_bytes())["packs"]
                      if item["path"].endswith("before-sentry-patch"))
        resources = {row["path"]: row["text"].encode() for row in before["extension_configs"]}
        resources["assets/data.txt"] = b"unchanged fixture asset"
        raw = make_pack(list(resources.items()), base=128, directory=65536)
        self.write_source("SlayTheSpire2.pck", raw)
        self.profile["pack"] = pin(raw)
        archive = self.root / "software.zip"
        package_converter.package(archive)
        with zipfile.ZipFile(archive) as packaged:
            packaged.extractall(self.root / "software")
        software = self.root / "software/sts2-converter"
        # Only this temporary test profile identifies the synthetic stand-ins.
        # Production profile hashes and the real managed recipes are unchanged.
        (software / "converter_profile_v1.json").write_text(json.dumps(self.profile))
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        before_source = self.snapshot(self.source)
        result = subprocess.run([sys.executable, "-S", str(software / "convert_sts2.py"),
                                 str(self.source), str(self.output), "--native-dir", str(self.native),
                                 "--godot-templates", str(self.archives["godot"]), "--dotnet-runtime", str(self.archives["dotnet"]),
                                 "--sentry-archive", str(self.archives["sentry"]), "--acknowledge-licenses"],
                                cwd=self.root, env=environment, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["validation"]["errors"], [])
        self.assertEqual(report["validation"]["files_verified"], 226)
        self.assertEqual(before_source, self.snapshot(self.source))
        self.assertEqual(verify(self.output)["errors"], [])


if __name__ == "__main__":
    unittest.main()
