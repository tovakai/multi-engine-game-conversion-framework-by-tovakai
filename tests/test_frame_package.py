from __future__ import annotations

import json
import stat
import zipfile

import pytest

from megcfbt import frame_package
from megcfbt.frame_package import (
    create_frame_zip,
    create_install_manifest,
    embed_steam_cover,
    framedrop_zip_compatible,
    write_frame_metadata,
    zip_unpacked_size,
)


def test_frame_zip_is_drop_in_and_preserves_linux_modes(tmp_path):
    build = tmp_path / "Example-frame"
    build.mkdir()
    launcher = build / "launch.sh"
    launcher.write_text("#!/usr/bin/env bash\necho hi\n", encoding="utf-8")
    (build / "data.txt").write_text("payload", encoding="utf-8")

    cover = tmp_path / "cover.png"
    cover.write_bytes(b"not-decoded-by-packager")
    embed_steam_cover(build, cover)
    write_frame_metadata(
        build,
        name="Example Game",
        launcher_path=launcher,
        engine="renpy",
        engine_version="8.3.4",
    )

    archive = create_frame_zip(build, launcher_path=launcher)
    assert archive.name == "Example-linux-aarch64.zip"

    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        assert "Example-frame/launch.sh" in names
        assert "Example-frame/install-to-steam.sh" in names
        assert "Example-frame/INSTALL-ON-FRAME.txt" in names
        assert "Example-frame/.megcfbt/install-to-steam.py" in names
        assert "Example-frame/payload/launch.sh" in names
        assert "Example-frame/.megcfbt/package.json" in names
        assert "Example-frame/.megcfbt/artwork/grid.png" in names
        assert "Example-frame/payload/.megcfbt/package.json" in names

        trampoline = zf.read("Example-frame/launch.sh").decode("utf-8")
        assert 'PAYLOAD="$ROOT/payload"' in trampoline
        assert 'exec "$PAYLOAD/$TARGET" "$@"' in trampoline

        launch_mode = zf.getinfo("Example-frame/launch.sh").external_attr >> 16
        install_mode = zf.getinfo("Example-frame/install-to-steam.sh").external_attr >> 16
        payload_launch_mode = zf.getinfo("Example-frame/payload/launch.sh").external_attr >> 16
        data_mode = zf.getinfo("Example-frame/payload/data.txt").external_attr >> 16
        assert stat.S_IMODE(launch_mode) == 0o755
        assert stat.S_IMODE(install_mode) == 0o755
        assert stat.S_IMODE(payload_launch_mode) == 0o755
        assert stat.S_IMODE(data_mode) == 0o644

        installer = zf.read("Example-frame/.megcfbt/install-to-steam.py").decode("utf-8")
        compile(installer, "install-to-steam.py", "exec")
        assert "steam://addnonsteamgame/" in installer
        assert "zlib.crc32" in installer
        assert "shortcuts.vdf" in installer
        assert "Expected deterministic AppID" in installer
        assert 'ARTWORK = {' in installer

        metadata = json.loads(
            zf.read("Example-frame/.megcfbt/package.json").decode("utf-8")
        )
        assert metadata["launcher"] == "launch.sh"
        assert metadata["payload"] == "payload"
        assert metadata["payload_launcher"] == "launch.sh"
        assert metadata["runtime"] == "SteamLinuxRuntime_4-arm64"


def test_shared_install_manifest_contains_hash_size_and_explicit_launcher(tmp_path):
    package = tmp_path / "Example-linux-aarch64.zip"
    package.write_bytes(b"frame package")
    manifest = create_install_manifest(
        package,
        url="https://example.invalid/Example-linux-aarch64.zip",
        name="Example Game",
        launcher_in_archive="Example-frame/launch.sh",
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))

    assert payload["schema"] == "framedrop.install/v1"
    entry = payload["files"][0]
    assert entry["url"].startswith("https://")
    assert len(entry["sha256"]) == 64
    assert entry["size"] == package.stat().st_size
    assert entry["exe"] == "Example-frame/launch.sh"


def test_frame_metadata_rejects_escaping_launcher(tmp_path):
    from megcfbt.frame_package import FramePackageError, load_frame_metadata

    build = tmp_path / "Bad-frame"
    meta = build / ".megcfbt"
    meta.mkdir(parents=True)
    (meta / "package.json").write_text(
        json.dumps(
            {
                "schema": "megcfbt.frame-build/v1",
                "name": "Bad",
                "launcher": "../outside.sh",
            }
        ),
        encoding="utf-8",
    )

    try:
        load_frame_metadata(build)
    except FramePackageError as exc:
        assert "unsafe launcher" in str(exc)
    else:
        raise AssertionError("escaping launcher was accepted")


def test_framedrop_compatibility_uses_total_unpacked_zip_size(tmp_path, monkeypatch):
    package = tmp_path / "large-for-test.zip"
    with zipfile.ZipFile(package, "w") as zf:
        zf.writestr("a.bin", b"1234")
        zf.writestr("b.bin", b"5678")

    assert zip_unpacked_size(package) == 8

    monkeypatch.setattr(frame_package, "FRAMEDROP_ZIP_UNPACK_LIMIT", 7)
    assert not framedrop_zip_compatible(package)

    monkeypatch.setattr(frame_package, "FRAMEDROP_ZIP_UNPACK_LIMIT", 8)
    assert framedrop_zip_compatible(package)


def test_bundled_installer_matches_steam_shortcut_appid_formula(tmp_path):
    from megcfbt.nonsteam_package import INSTALLER_PYTHON

    namespace = {
        "__name__": "embedded_installer_test",
        "__file__": str(tmp_path / "Example-frame/.megcfbt/install-to-steam.py"),
    }
    exec(compile(INSTALLER_PYTHON, "install-to-steam.py", "exec"), namespace)

    exe = '"/home/steamos/Games/Brotato-frame/launch.sh"'
    assert namespace["shortcut_appid"](exe, "Brotato") == 3929824991
    assert namespace["to_unsigned32"](-365142305) == 3929824991


def test_bundled_installer_reads_shortcuts_vdf(tmp_path):
    from megcfbt.nonsteam_package import INSTALLER_PYTHON

    namespace = {
        "__name__": "embedded_installer_test",
        "__file__": str(tmp_path / "Example-frame/.megcfbt/install-to-steam.py"),
    }
    exec(compile(INSTALLER_PYTHON, "install-to-steam.py", "exec"), namespace)

    path = tmp_path / "shortcuts.vdf"
    original = {
        "0": {
            "appid": -365142305,
            "AppName": "Brotato",
            "Exe": '"/home/steamos/Games/Brotato-frame/launch.sh"',
            "tags": {"0": "Tovakai ARM64"},
        }
    }
    writer = (
        b"\x00shortcuts\x00"
        + b"\x00" + b"0\x00"
        + b"\x02appid\x00" + (-365142305).to_bytes(4, "little", signed=True)
        + b"\x01AppName\x00Brotato\x00"
        + b'\x01Exe\x00"/home/steamos/Games/Brotato-frame/launch.sh"\x00'
        + b"\x00tags\x00\x010\x00Tovakai ARM64\x00\x08"
        + b"\x08\x08\x08"
    )
    path.write_bytes(writer)
    assert namespace["load_shortcuts"](path) == original


def test_frame_zip_large_streamed_entry_uses_zip64(tmp_path, monkeypatch):
    # Emulate ZIP64's multi-gigabyte boundary without storing a huge fixture.
    # This failed with "File size too large, try using force_zip64" when the
    # streaming ZipInfo did not declare its source file's size.
    build = tmp_path / "Large-frame"
    build.mkdir()
    launcher = build / "launch.sh"
    launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    payload = build / "large.bin"
    payload.write_bytes(b"x" * 2048)

    monkeypatch.setattr(zipfile, "ZIP64_LIMIT", 256)
    archive = create_frame_zip(build, launcher_path=launcher)

    with zipfile.ZipFile(archive) as zf:
        name = "Large-frame/payload/large.bin"
        assert zf.testzip() is None
        assert zf.read(name) == payload.read_bytes()
        assert stat.S_IMODE(zf.getinfo(name).external_attr >> 16) == 0o644


def test_frame_zip_stream_error_removes_partial_archive(tmp_path, monkeypatch):
    build = tmp_path / "Interrupted-frame"
    build.mkdir()
    launcher = build / "launch.sh"
    launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (build / "data.bin").write_bytes(b"example data")
    archive = tmp_path / "Interrupted-linux-aarch64.zip"

    original_open = zipfile.ZipFile.open

    def interrupted_open(zf, name, mode="r", *args, **kwargs):
        handle = original_open(zf, name, mode, *args, **kwargs)
        if mode == "w":
            original_write = handle.write
            def interrupted_write(data):
                original_write(data[:2])
                raise OSError("interrupted while streaming")
            handle.write = interrupted_write
        return handle

    monkeypatch.setattr(zipfile.ZipFile, "open", interrupted_open)
    with pytest.raises(frame_package.FramePackageError, match="interrupted while streaming"):
        create_frame_zip(build, launcher_path=launcher, output=archive)
    assert not archive.exists()
    assert not list(tmp_path.glob(f".{archive.name}.tmp-*"))
