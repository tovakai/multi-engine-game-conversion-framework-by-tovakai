from __future__ import annotations

from pathlib import Path

import pytest

from rpgmframe.godot_backend import GodotBuildError, _copy_runtime_bundle


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
