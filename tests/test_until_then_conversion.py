"""Production inspection -> backend -> router -> ZIP, synthetic owned-game fixtures."""
import hashlib
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from megcfbt import router, steam_library
from megcfbt.fmod_sdk_setup import requirement
from rpgmframe import until_then as profile, godot_extension_runtime as runtime
from rpgmframe.godot_overlay import read_resource, write_pack


def elf(machine=183):
    data = bytearray(64)
    data[:6] = b"\x7fELF\x02\x01"
    data[18:20] = machine.to_bytes(2, "little")
    return bytes(data)


def tar_files(path, files):
    with tarfile.open(path, "w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))


@pytest.fixture
def converted_fixture(tmp_path, monkeypatch):
    source = tmp_path / "Steam/steamapps/common/Until Then"
    source.mkdir(parents=True)
    hashes = {}
    for name in profile.SOURCE_LIBRARIES:
        data = ("synthetic Windows extension " + name).encode()
        (source / name).write_bytes(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
    files = {f"addons/{name}/{name}.gdextension": b"synthetic original descriptor"
             for name in profile.LIBRARIES}
    files[profile.THUMBNAIL_SCRIPT] = b"# independently authored fixture\n" + profile.OLD_LOADER_CALL
    pack = source / "UntilThen.pck"
    write_pack(pack, files)
    monkeypatch.setattr(profile, "PACK_SIZE", pack.stat().st_size)
    monkeypatch.setattr(profile, "PACK_SHA256", profile.digest(pack))
    monkeypatch.setattr(profile, "SOURCE_LIBRARIES", hashes)
    (source / "manual.txt").write_text("synthetic retained companion")
    (source / "UntilThen.exe").write_bytes(b"MZ synthetic executable")
    sdk = tmp_path / profile.FMOD_FILENAME
    tar_files(sdk, {**{f"fmodstudioapi20235linux/api/{component}/lib/arm64/lib{name}.so.13.35": elf()
                   for component, name in (("core", "fmod"), ("studio", "fmodstudio"))},
                   "fmodstudioapi20235linux/doc/LICENSE.TXT": b"Synthetic vendor license"})
    monkeypatch.setattr(profile, "FMOD_SIZE", sdk.stat().st_size)
    monkeypatch.setattr(profile, "FMOD_SHA256", profile.digest(sdk))
    bundle = tmp_path / "runtime"
    bundle.mkdir()
    payload = {name: elf() for name in runtime.REQUIRED}
    payload["NOTICE.txt"] = b"Synthetic license fixture"
    pinned = {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()}
    manifest = {"recipe_id": profile.RECIPE, "engine_version": "4.1.4", "architecture": "aarch64",
        "capabilities": {"resource_overlay_before_extensions": True, "extension_symbols": "isolated",
            "fmod_abi": "2.02", "steam_api_provider": "steam-frame-installed"}, "files": pinned}
    payload["runtime.json"] = json.dumps(manifest).encode()
    for name, data in payload.items():
        (bundle / name).parent.mkdir(parents=True, exist_ok=True)
        (bundle / name).write_bytes(data)
    archive = tmp_path / (profile.RECIPE + ".tar.gz")
    tar_files(archive, payload)
    entry = {"recipe_id": profile.RECIPE, "executable": "godot.arm64", "archive_name": archive.name,
        "archive_files": sorted(payload), "files": pinned, "sha256": profile.digest(archive),
        "url": "https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/releases/download/runtime-until-then-arm64-v1/" + archive.name}
    index = tmp_path / "runtime-index.json"
    index.write_text(json.dumps({"recipes": {profile.RECIPE: entry}}))
    monkeypatch.setattr(runtime, "INDEX_PATH", index)
    monkeypatch.setattr(router, "complete_frame_artwork", lambda *args, **kwargs: None)
    monkeypatch.setattr(profile, "find_fmod_sdk", lambda: None)
    return source, sdk, bundle, archive


def snapshot(root):
    return {path.relative_to(root): (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
            for path in root.rglob("*") if path.is_file()}


def convert(tmp_path, fixture, **options):
    source, sdk, bundle, _ = fixture
    return router.build_source(source, output=tmp_path / "converted", backend_runtime=bundle,
        until_then_sdk=sdk, archive=True, **options)


@pytest.mark.parametrize("manifest", [False, True])
def test_complete_pipeline_preserves_audited_identity_and_native_contract(tmp_path, converted_fixture, manifest):
    source, sdk, bundle, _ = converted_fixture
    if manifest:
        (source.parents[1] / "appmanifest_1574820.acf").write_text(
            '"AppState" { "appid" "1574820" "installdir" "Until Then" }')
    before = snapshot(source)
    runtime_before = snapshot(bundle)
    inspection = router.inspect_source(source)
    assert inspection.buildable and inspection.backend == "rpgmframe"
    assert inspection.engine == "godot" and inspection.runtime_kind == profile.RUNTIME_KIND
    result = convert(tmp_path, converted_fixture)
    assert result.archive_path.is_file() and "-conv-v" in result.archive_path.name
    output = result.output_path
    assert (output / "game/UntilThen.pck").read_bytes() == (source / "UntilThen.pck").read_bytes()
    assert (output / "game/manual.txt").is_file()
    assert not list((output / "game").rglob("*.dll"))
    assert not (output / "game/UntilThen.exe").exists()
    for component, (_, library) in profile.LIBRARIES.items():
        assert (output / "game" / profile.extension_directory(component) / library).read_bytes() == elf()
    assert (output / "game/addons/fmod/native/linux/libfmod.so.13").read_bytes() == elf()
    assert (output / "licenses/LICENSE-FMOD-SDK.txt").read_bytes() == b"Synthetic vendor license"
    overlay = output / "game/untilthen-native-overlay.pck"
    assert profile.OLD_LOADER_CALL not in read_resource(overlay, profile.THUMBNAIL_SCRIPT)
    assert profile.NEW_LOADER_CALL in read_resource(overlay, profile.THUMBNAIL_SCRIPT)
    assert b"linux.release" in read_resource(overlay, "addons/inkcpp/inkcpp.gdextension")
    launcher = (output / "launch.sh").read_text()
    assert "MEGCFBT_RESOURCE_OVERLAY" in launcher and "--path" in launcher
    assert 'export SteamAppId=1574820' in launcher and 'export SteamGameId=1574820' in launcher
    assert (output / 'game/steam_appid.txt').read_bytes() == b'1574820\n'
    assert "MESA_LOADER_DRIVER_OVERRIDE" not in launcher
    assert 'import_graphics_env' not in launcher and "libsteam_api.so" in launcher
    assert "proton" not in launcher.casefold() and "fex" not in launcher.casefold()
    assert "megcfbt/until-then" in (output / "game/override.cfg").read_text()
    assert snapshot(source) == before and snapshot(bundle) == runtime_before
    with zipfile.ZipFile(result.archive_path) as archive:
        copies = [name for name in archive.namelist() if name.endswith(".megcfbt/package.json")]
        assert len(copies) == 2
        for name in copies:
            metadata = json.loads(archive.read(name))
            assert metadata["engine"] == "godot" and metadata["backend"] == "rpgmframe"
            assert metadata["compatibility_profile"] == profile.PROFILE
            assert metadata["runtime_engine_version"] == "4.1.4"
            assert metadata["steam_runtime_appid"] == 1574820
            assert steam_library.identity(metadata) == 1574820
            assert metadata.get("steam_identity") == ({"source": "installed-source-manifest", "appid": 1574820} if manifest else None)
            assert steam_library.capability(metadata)[0] is False
        installer = [name for name in archive.namelist() if name.endswith(".megcfbt/steam_library.py")][0]
        assert profile.PROFILE.encode() in archive.read(installer)


def test_sidecar_cannot_select_or_establish_identity(tmp_path, converted_fixture):
    source = converted_fixture[0]
    (source / "steam_appid.txt").write_text("999999")
    result = convert(tmp_path, converted_fixture)
    assert (result.output_path / "steam_appid.txt").read_text().strip() == "1574820"
    data = json.loads((result.output_path / ".megcfbt/package.json").read_text())
    assert data.get("steam_identity") is None and steam_library.identity(data) == 1574820


def test_conflicting_manifest_fails_before_creating_output(tmp_path, converted_fixture):
    source = converted_fixture[0]
    (source.parents[1] / "appmanifest_413150.acf").write_text(
        '"AppState" { "appid" "413150" "installdir" "Until Then" }')
    with pytest.raises(router.ConversionError, match="Conflicting"):
        convert(tmp_path, converted_fixture)
    assert not (tmp_path / "converted").exists()


def test_modified_pack_fails_safely_despite_fast_inspection_hint(tmp_path, converted_fixture):
    pack = converted_fixture[0] / "UntilThen.pck"
    content = bytearray(pack.read_bytes())
    content[-10] ^= 1
    pack.write_bytes(content)
    with pytest.raises(router.ConversionError, match="audited Steam build"):
        convert(tmp_path, converted_fixture)
    assert not (tmp_path / "converted").exists()


def test_changed_extension_disables_automatic_profile(tmp_path, converted_fixture):
    (converted_fixture[0] / "inkcpp.dll").write_bytes(b"incompatible extension update")
    inspection = router.inspect_source(converted_fixture[0])
    assert not inspection.buildable and inspection.runtime_kind == "godot-native-extensions"


def test_missing_sdk_is_actionable_and_leaves_no_output(tmp_path, converted_fixture):
    source, _, bundle, _ = converted_fixture
    with pytest.raises(router.ConversionError, match="2.02.35.*--fmod-sdk"):
        router.build_source(source, output=tmp_path / "converted", backend_runtime=bundle)
    assert not (tmp_path / "converted").exists()


def test_wrong_sdk_does_not_erase_previous_conversion(tmp_path, converted_fixture):
    convert(tmp_path, converted_fixture)
    before = snapshot(tmp_path / "converted")
    converted_fixture[1].write_bytes(b"wrong SDK")
    with pytest.raises(router.ConversionError, match="2.02.35"):
        convert(tmp_path, converted_fixture, force=True)
    assert snapshot(tmp_path / "converted") == before


def test_force_reconversion_is_idempotent(tmp_path, converted_fixture):
    first = convert(tmp_path, converted_fixture)
    pack = (first.output_path / "game/UntilThen.pck").read_bytes()
    second = convert(tmp_path, converted_fixture, force=True)
    assert first.archive_path == second.archive_path
    assert (second.output_path / "game/UntilThen.pck").read_bytes() == pack
    assert len(list(second.output_path.rglob("untilthen-native-overlay.pck"))) == 1


@pytest.mark.parametrize("path", ["godot.arm64", "extensions/inkcpp/libinkcpp.so"])
def test_runtime_tampering_fails_integrity_validation(tmp_path, converted_fixture, path):
    (converted_fixture[2] / path).write_bytes(b"tampered")
    with pytest.raises(router.ConversionError, match="integrity"):
        convert(tmp_path, converted_fixture)


def test_embedded_verified_bundle_needs_no_network(tmp_path, converted_fixture, monkeypatch):
    monkeypatch.setattr(runtime, "EMBEDDED_PATH", converted_fixture[3].parent)
    monkeypatch.setattr(runtime, "_cache_parent", lambda: tmp_path / "cache")
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: pytest.fail("Unexpected network request"))
    selected = runtime.resolve_runtime()
    assert selected.is_dir() and runtime.validate_runtime(selected)
    assert runtime.resolve_runtime() == selected


def test_corrupt_embedded_archive_fails_closed(tmp_path, converted_fixture, monkeypatch):
    converted_fixture[3].write_bytes(b"corrupted")
    monkeypatch.setattr(runtime, "EMBEDDED_PATH", converted_fixture[3].parent)
    monkeypatch.setattr(runtime, "_cache_parent", lambda: tmp_path / "cache")
    with pytest.raises(Exception, match="SHA-256 mismatch"):
        runtime.resolve_runtime()


def test_runtime_symlink_is_rejected(tmp_path, converted_fixture):
    path = converted_fixture[2] / "extensions/inkcpp/libinkcpp.so"
    path.unlink()
    try:
        path.symlink_to(converted_fixture[2] / "godot.arm64")
    except OSError:
        pytest.skip("Symlink privileges unavailable")
    with pytest.raises(ValueError, match="integrity"):
        runtime.validate_runtime(converted_fixture[2])


def test_shared_fmod_dialog_uses_until_then_sdk_version():
    settings = requirement("until-then")
    assert settings["version"] == "2.02.35" and settings["attribute"] == "until_then_sdk"
    assert requirement("celesteframe")["version"] == "2.03.15"


@pytest.mark.parametrize("unsafe", ["../evil", "/absolute", "a\\b", "a//b", "a/../b"])
def test_overlay_rejects_unsafe_paths(tmp_path, unsafe):
    with pytest.raises(ValueError, match="Unsafe"):
        write_pack(tmp_path / "overlay.pck", {unsafe: b"data"})


def test_overlay_resource_checksum_rejects_modified_content(tmp_path):
    path = tmp_path / "test.pck"
    write_pack(path, {"file.gd": b"synthetic script"})
    data = bytearray(path.read_bytes())
    data[-16] ^= 1
    path.write_bytes(data)
    with pytest.raises(ValueError, match="checksum"):
        read_resource(path, "file.gd")


@pytest.mark.parametrize("appid,expected", [(1574820, "1574820"), (None, "7557288")])
def test_launcher_executes_with_correct_steam_context(tmp_path, appid, expected):
    import os
    import shutil
    import subprocess
    from rpgmframe.launchers import godot_launcher_body
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("Bash unavailable")
    (tmp_path / "game").mkdir()
    (tmp_path / "godot.arm64").write_bytes(b'#!/usr/bin/env bash\nprintf "%s|%s|%s" "$SteamAppId" "$SteamGameId" "$DISPLAY"\n')
    launcher = tmp_path / "launch.sh"
    launcher.write_bytes(godot_launcher_body("game/test.pck", preserve_launch_environment=True, steam_app_id=appid).encode())
    env = dict(os.environ, SteamAppId="7557288", SteamGameId="7557288", DISPLAY=":verified", MEGCFBT_FRAME_ENV_IMPORTED="1")
    result = subprocess.run([bash, str(launcher)], env=env, capture_output=True, text=True, check=True)
    assert result.stdout == f"{expected}|{expected}|:verified"
