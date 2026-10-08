from __future__ import annotations

from pathlib import Path

import pytest

from rpgmframe.godot_backend import (
    GodotBuildError,
    _copy_godotsteam_data,
    _copy_runtime_bundle,
)
from rpgmframe.launchers import godot_launcher_body


def _write_elf(path: Path, machine: int) -> None:
    header = bytearray(20)
    header[:4] = b"\x7fELF"
    header[4] = 2
    header[5] = 1
    header[18:20] = machine.to_bytes(2, "little")
    path.write_bytes(header)


def test_custom_runtime_bundle_copies_arm64_shared_libraries(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    staging = tmp_path / "staging"
    runtime.mkdir()
    staging.mkdir()

    _write_elf(runtime / "godot.arm64", 183)
    _write_elf(runtime / "libsteam_api.so", 183)

    copied = _copy_runtime_bundle(runtime, staging)

    assert copied == ["godot.arm64", "libsteam_api.so"]
    assert (staging / "godot.arm64").is_file()
    assert (staging / "libsteam_api.so").is_file()


def test_custom_runtime_bundle_rejects_wrong_arch_shared_library(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    staging = tmp_path / "staging"
    runtime.mkdir()
    staging.mkdir()

    _write_elf(runtime / "godot.arm64", 183)
    _write_elf(runtime / "libsteam_api.so", 62)

    with pytest.raises(GodotBuildError, match="not aarch64"):
        _copy_runtime_bundle(runtime, staging)


def test_godotsteam_data_is_copied_beside_runtime(tmp_path: Path) -> None:
    source = tmp_path / "game"
    staging = tmp_path / "staging"
    source.mkdir()
    staging.mkdir()
    (source / "steam_data.json").write_text('{"app_id":"1942280"}', encoding="utf-8")

    copied = _copy_godotsteam_data(source, staging)
    assert copied == source / "steam_data.json"
    assert (staging / "steam_data.json").read_text(encoding="utf-8") == '{"app_id":"1942280"}'


def test_missing_godotsteam_data_is_not_invented(tmp_path: Path) -> None:
    source = tmp_path / "game"
    staging = tmp_path / "staging"
    source.mkdir()
    staging.mkdir()

    assert _copy_godotsteam_data(source, staging) is None
    assert not (staging / "steam_data.json").exists()


def test_custom_godot_launcher_uses_proven_zink_path() -> None:
    launcher = godot_launcher_body("game/Brotato.pck", force_zink=True)

    assert 'MESA_LOADER_DRIVER_OVERRIDE="${MESA_LOADER_DRIVER_OVERRIDE:-zink}"' in launcher
    assert 'GALLIUM_DRIVER="${GALLIUM_DRIVER:-zink}"' in launcher
    assert 'LD_LIBRARY_PATH="$ROOT' in launcher


def test_stable_godot_launcher_does_not_force_zink() -> None:
    launcher = godot_launcher_body("game/Test.pck")

    assert "MESA_LOADER_DRIVER_OVERRIDE" not in launcher
    assert "GALLIUM_DRIVER" not in launcher
