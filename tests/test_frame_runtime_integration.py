"""Integration checks for automatic runtime + Frame ZIP routing."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from megcfbt.artwork import detected_steam_appid, fetch_official_steam_portrait
from megcfbt.router import output_path_for_source
from megcfbt.frame_package import create_frame_zip, write_frame_metadata


def test_output_name_prefers_detected_title(tmp_path):
    result = output_path_for_source(tmp_path / "game", tmp_path, "Brotato")
    assert result.name == "Brotato-frame"


def test_output_name_falls_back_to_source(tmp_path):
    result = output_path_for_source(tmp_path / "game", tmp_path)
    assert result.name == "game-frame"


def test_frame_zip_contains_single_launcher_and_payload(tmp_path):
    build = tmp_path / "Brotato-frame"
    build.mkdir()
    launcher = build / "launch.sh"
    launcher.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    (build / "godot.arm64").write_bytes(b"runtime")
    write_frame_metadata(
        build, name="Brotato", launcher_path=launcher, engine="godot"
    )
    archive = create_frame_zip(build)
    assert archive.name == "Brotato-linux-aarch64.zip"
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        assert "Brotato-frame/launch.sh" in names
        assert "Brotato-frame/payload/godot.arm64" in names
        assert "Brotato-frame/payload/.megcfbt/package.json" in names
        assert all(not name.endswith(".tmp") for name in names)


def test_artwork_match_requires_appid(tmp_path, monkeypatch):
    assert detected_steam_appid(tmp_path) is None
    assert fetch_official_steam_portrait(tmp_path) is None
    (tmp_path / "steam_appid.txt").write_text("1942280\n", encoding="utf-8")
    assert detected_steam_appid(tmp_path) == "1942280"


def test_artwork_rejects_unrelated_appid(tmp_path):
    (tmp_path / "steam_appid.txt").write_text("not-a-number", encoding="utf-8")
    assert detected_steam_appid(tmp_path) is None
