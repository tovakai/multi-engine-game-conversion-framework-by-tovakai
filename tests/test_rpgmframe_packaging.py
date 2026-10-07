from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from rpgmframe.packaging import PackagingError, create_tar_gz, default_archive_path


def test_default_archive_name_replaces_frame_suffix(tmp_path: Path) -> None:
    build = tmp_path / "jailbreak-frame"
    assert default_archive_path(build) == tmp_path / "jailbreak-linux-aarch64.tar.gz"


def test_create_tar_gz_contains_build_root_and_launcher(tmp_path: Path) -> None:
    build = tmp_path / "jailbreak-frame"
    build.mkdir()
    launcher = build / "launch.sh"
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher.chmod(0o755)
    (build / "www").mkdir()
    (build / "www/index.html").write_text("<html></html>", encoding="utf-8")

    archive = create_tar_gz(build)

    assert archive == tmp_path / "jailbreak-linux-aarch64.tar.gz"
    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
        assert "jailbreak-frame/launch.sh" in names
        assert "jailbreak-frame/www/index.html" in names
        launcher_member = tar.getmember("jailbreak-frame/launch.sh")
        assert launcher_member.mode & 0o111


def test_create_tar_gz_restores_linux_execute_bits_from_non_posix_source(
    tmp_path: Path,
) -> None:
    build = tmp_path / "game-frame"
    build.mkdir()

    for name in (
        "launch.sh",
        "nw",
        "chrome_crashpad_handler",
        "chrome-sandbox",
        "mkxp-z.aarch64",
        "godot.arm64",
    ):
        path = build / name
        path.write_bytes(b"placeholder")
        path.chmod(0o644)

    helper = build / "tools" / "post-install.sh"
    helper.parent.mkdir()
    helper.write_text("#!/bin/sh\n", encoding="utf-8")
    helper.chmod(0o644)

    data = build / "package.json"
    data.write_text("{}", encoding="utf-8")
    data.chmod(0o644)

    archive = create_tar_gz(build)

    with tarfile.open(archive, "r:gz") as tar:
        for name in (
            "game-frame/launch.sh",
            "game-frame/nw",
            "game-frame/chrome_crashpad_handler",
            "game-frame/chrome-sandbox",
            "game-frame/mkxp-z.aarch64",
            "game-frame/godot.arm64",
            "game-frame/tools/post-install.sh",
        ):
            assert tar.getmember(name).mode & 0o111

        assert not (tar.getmember("game-frame/package.json").mode & 0o111)


def test_create_tar_gz_refuses_existing_archive_without_force(tmp_path: Path) -> None:
    build = tmp_path / "game-frame"
    build.mkdir()
    archive = default_archive_path(build)
    archive.write_bytes(b"old")

    with pytest.raises(PackagingError, match="already exists"):
        create_tar_gz(build)

    replaced = create_tar_gz(build, force=True)
    assert replaced == archive
    assert archive.stat().st_size > 3
