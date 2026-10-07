from pathlib import Path


def test_native_build_scripts_exist_and_keep_full_name() -> None:
    windows = Path("build/build_windows.ps1").read_text(encoding="utf-8")
    linux = Path("build/build_linux_aarch64.sh").read_text(encoding="utf-8")
    full = "Multi-Engine Game Conversion Framework by Tovakai"
    assert full in windows
    assert full in linux
    assert "--collect-submodules renpy_arm" in windows
    assert "--collect-submodules rpgmframe" in windows
    assert "--collect-submodules renpy_arm" in linux
    assert "--collect-submodules rpgmframe" in linux
