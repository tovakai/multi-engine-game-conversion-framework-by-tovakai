from __future__ import annotations

import json
import stat
import zipfile

from megcfbt.frame_package import (
    create_frame_zip,
    create_install_manifest,
    embed_steam_cover,
    write_frame_metadata,
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
        assert "Example-frame/payload/launch.sh" in names
        assert "Example-frame/.megcfbt/package.json" in names
        assert "Example-frame/.megcfbt/artwork/grid.png" in names
        assert "Example-frame/payload/.megcfbt/package.json" in names

        trampoline = zf.read("Example-frame/launch.sh").decode("utf-8")
        assert 'PAYLOAD="$ROOT/payload"' in trampoline
        assert 'exec "$PAYLOAD/$TARGET" "$@"' in trampoline

        launch_mode = zf.getinfo("Example-frame/launch.sh").external_attr >> 16
        payload_launch_mode = zf.getinfo("Example-frame/payload/launch.sh").external_attr >> 16
        data_mode = zf.getinfo("Example-frame/payload/data.txt").external_attr >> 16
        assert stat.S_IMODE(launch_mode) == 0o755
        assert stat.S_IMODE(payload_launch_mode) == 0o755
        assert stat.S_IMODE(data_mode) == 0o644

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
