from __future__ import annotations

import json
import stat

import megcfbt.steam_install as steam_install


def test_title_id_is_safe_for_valve_devkit_names():
    assert steam_install.title_id("My Game!") == "My_Game"
    assert steam_install.title_id("2048") == "_2048"
    assert steam_install.title_id("steam") == "steam_game"


def test_supported_host_is_linux_arm64(monkeypatch):
    monkeypatch.setattr(steam_install.platform, "system", lambda: "Linux")
    monkeypatch.setattr(steam_install.platform, "machine", lambda: "aarch64")
    assert steam_install.is_supported_host()

    monkeypatch.setattr(steam_install.platform, "machine", lambda: "x86_64")
    assert not steam_install.is_supported_host()


def test_install_tree_writes_devkit_sidecars_and_launcher_mode(tmp_path, monkeypatch):
    source = tmp_path / "Example-frame"
    source.mkdir()
    launcher = source / "launch.sh"
    launcher.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    devkit = tmp_path / "devkit-game"
    monkeypatch.setattr(steam_install, "_DEVKIT_ROOT", devkit)

    destination = steam_install._install_tree(source, "Example_Game", "launch.sh")

    assert destination == devkit / "Example_Game"
    assert stat.S_IMODE((destination / "launch.sh").stat().st_mode) & 0o111
    assert json.loads((devkit / "Example_Game-argv.json").read_text()) == ["launch.sh"]
    assert json.loads((devkit / "Example_Game-env.json").read_text()) == {}
    settings = json.loads((devkit / "Example_Game-settings.json").read_text())
    assert settings == {
        "steam_play": "0",
        "compat_tool": "SteamLinuxRuntime_4-arm64",
    }
