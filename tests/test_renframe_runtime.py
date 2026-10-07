"""Tests for runtime inspection and layout detection."""

from __future__ import annotations

from pathlib import Path

from tests.fixtures import make_runtime
from renframe.runtime import (
    detect_runtime_layout,
    inspect_runtime,
    looks_like_renpy_runtime,
    runtime_architecture_is_clearly_x86,
)


def test_valid_arm64_runtime(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path / "renpy-arm64", version="8.4.0", arch="aarch64")
    result = inspect_runtime(runtime)
    assert result.is_renpy_runtime is True
    assert result.architecture == "aarch64"
    assert result.version == "8.4.0"
    assert result.generation == 8
    assert result.has_renpy_sh is True
    assert "aarch64" in result.lib_architectures
    assert not runtime_architecture_is_clearly_x86(result)


def test_x86_64_runtime_detected_as_x86(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path / "renpy-x64", arch="x86_64")
    result = inspect_runtime(runtime)
    assert result.is_renpy_runtime is True
    assert result.architecture == "x86_64"
    assert runtime_architecture_is_clearly_x86(result)


def test_non_renpy_directory_rejected(tmp_path: Path) -> None:
    plain = tmp_path / "notes"
    plain.mkdir()
    (plain / "readme.txt").write_text("hello", encoding="utf-8")
    assert not looks_like_renpy_runtime(plain)
    result = inspect_runtime(plain)
    assert result.is_renpy_runtime is False


def test_runtime_version_detected(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path / "sdk", version="8.2.1")
    result = inspect_runtime(runtime)
    assert result.version == "8.2.1"
    assert result.generation == 8


def test_runtime_layout_prefers_renpy_sh(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path / "sdk")
    layout = detect_runtime_layout(runtime)
    assert layout.launcher is not None
    assert layout.launcher.name == "renpy.sh"
    assert layout.launcher_relative == "renpy.sh"
    assert layout.arm_lib_dir is not None
    assert layout.python_bin is not None
