"""Tests for Frame build orchestration, path safety, and version rules."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from renframe.builder import (
    BuildError,
    build_game,
    check_version_compatibility,
    default_output_path,
    validate_force_delete_target,
    validate_output_paths,
)
from renframe.models import GameInspection, RuntimeInspection
from renframe.utils import is_dangerous_output_path, paths_conflict
from tests.fixtures import make_game, make_runtime


def test_default_output_path(tmp_path: Path) -> None:
    source = tmp_path / "MyGame"
    source.mkdir()
    assert default_output_path(source) == (tmp_path / "MyGame-frame").resolve()


def test_version_same_generation_allowed() -> None:
    game = GameInspection(
        source_path=Path("."),
        is_renpy=True,
        renpy_version="8.2.1",
        generation=8,
    )
    runtime = RuntimeInspection(
        path=Path("."),
        is_renpy_runtime=True,
        version="8.4.0",
        generation=8,
    )
    warnings = check_version_compatibility(game, runtime, allow_mismatch=False)
    assert any("8.2.1" in w and "8.4.0" in w for w in warnings)


def test_version_7_with_7_allowed() -> None:
    game = GameInspection(
        source_path=Path("."),
        is_renpy=True,
        renpy_version="7.6.1",
        generation=7,
    )
    runtime = RuntimeInspection(
        path=Path("."),
        is_renpy_runtime=True,
        version="7.6.3",
        generation=7,
    )
    warnings = check_version_compatibility(game, runtime, allow_mismatch=False)
    assert any("7.6.1" in w for w in warnings)


def test_version_generation_mismatch_rejected() -> None:
    game = GameInspection(
        source_path=Path("."),
        is_renpy=True,
        renpy_version="7.6.1",
        generation=7,
    )
    runtime = RuntimeInspection(
        path=Path("."),
        is_renpy_runtime=True,
        version="8.3.4",
        generation=8,
    )
    with pytest.raises(BuildError, match="generation mismatch"):
        check_version_compatibility(game, runtime, allow_mismatch=False)


def test_version_mismatch_override() -> None:
    game = GameInspection(
        source_path=Path("."),
        is_renpy=True,
        renpy_version="7.6.1",
        generation=7,
    )
    runtime = RuntimeInspection(
        path=Path("."),
        is_renpy_runtime=True,
        version="8.3.4",
        generation=8,
    )
    warnings = check_version_compatibility(game, runtime, allow_mismatch=True)
    assert any("allow-version-mismatch" in w for w in warnings)


def test_path_safety_source_equals_output(tmp_path: Path) -> None:
    source = tmp_path / "game"
    source.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    with pytest.raises(BuildError, match="conflicts with source"):
        validate_output_paths(source, source, runtime)


def test_path_safety_output_inside_source(tmp_path: Path) -> None:
    source = tmp_path / "game"
    source.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    with pytest.raises(BuildError, match="conflicts with source"):
        validate_output_paths(source, source / "frame", runtime)


def test_path_safety_output_parent_of_source(tmp_path: Path) -> None:
    source = tmp_path / "parent" / "game"
    source.mkdir(parents=True)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    with pytest.raises(BuildError, match="conflicts with source"):
        validate_output_paths(source, tmp_path / "parent", runtime)


def test_path_safety_output_equals_runtime(tmp_path: Path) -> None:
    source = tmp_path / "game"
    source.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    with pytest.raises(BuildError, match="conflicts with runtime"):
        validate_output_paths(source, runtime, runtime)


def test_path_safety_dangerous_root() -> None:
    assert is_dangerous_output_path(Path("/"))


def test_path_safety_safe_sibling_accepted(tmp_path: Path) -> None:
    source = tmp_path / "game"
    source.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    output = tmp_path / "game-frame"
    validate_output_paths(source, output, runtime)
    assert not paths_conflict(source, output)


def test_force_delete_refuses_source(tmp_path: Path) -> None:
    source = tmp_path / "game"
    source.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    with pytest.raises(BuildError, match="source"):
        validate_force_delete_target(source, source=source, runtime=runtime)


def test_build_requires_runtime(tmp_path: Path) -> None:
    game = make_game(tmp_path / "ExampleGame")
    with pytest.raises(BuildError, match="--runtime is required"):
        build_game(game)


def test_build_rejects_x86_runtime(tmp_path: Path) -> None:
    game = make_game(tmp_path / "ExampleGame")
    runtime = make_runtime(tmp_path / "x86-sdk", arch="x86_64")
    with pytest.raises(BuildError, match="x86-only"):
        build_game(game, runtime=runtime, output=tmp_path / "out")


def test_build_rejects_non_renpy_runtime(tmp_path: Path) -> None:
    game = make_game(tmp_path / "ExampleGame")
    runtime = tmp_path / "not-runtime"
    runtime.mkdir()
    with pytest.raises(BuildError, match="does not look like"):
        build_game(game, runtime=runtime, output=tmp_path / "out")


def test_build_rejects_incompatible_native(tmp_path: Path) -> None:
    game = make_game(tmp_path / "BadNative", with_native_x86=True)
    runtime = make_runtime(tmp_path / "arm-sdk")
    with pytest.raises(BuildError, match="incompatible"):
        build_game(game, runtime=runtime, output=tmp_path / "out")


def test_build_generation_mismatch_and_override(tmp_path: Path) -> None:
    game = make_game(tmp_path / "OldGame", version="7.6.1", lib_arch="py2-linux-x86_64")
    runtime = make_runtime(tmp_path / "arm8", version="8.3.4")
    with pytest.raises(BuildError, match="generation mismatch"):
        build_game(game, runtime=runtime, output=tmp_path / "out")

    result = build_game(
        game,
        runtime=runtime,
        output=tmp_path / "out-override",
        allow_version_mismatch=True,
        dry_run=True,
    )
    assert result.success
    assert any("allow-version-mismatch" in w for w in result.warnings)


def test_existing_output_rejected_without_force(tmp_path: Path) -> None:
    game = make_game(tmp_path / "ExampleGame")
    runtime = make_runtime(tmp_path / "arm-sdk")
    output = tmp_path / "ExampleGame-frame"
    output.mkdir()
    (output / "marker.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(BuildError, match="already exists"):
        build_game(game, runtime=runtime, output=output)


def test_force_replaces_output_only(tmp_path: Path) -> None:
    game = make_game(tmp_path / "ExampleGame")
    runtime = make_runtime(tmp_path / "arm-sdk")
    output = tmp_path / "ExampleGame-frame"
    output.mkdir()
    (output / "old.txt").write_text("old", encoding="utf-8")

    result = build_game(game, runtime=runtime, output=output, force=True)
    assert result.success
    assert not (output / "old.txt").exists()
    assert (output / "game" / "script.rpy").is_file()
    assert game.is_dir()
    assert (game / "game" / "script.rpy").is_file()
    assert runtime.is_dir()
    assert (runtime / "renpy.sh").is_file()


def test_successful_fixture_build(tmp_path: Path) -> None:
    game = make_game(tmp_path / "ExampleGame", version="8.3.2")
    # Marker that must remain only in source, not copied as runtime.
    (game / "lib" / "py3-linux-x86_64" / "ONLY_SOURCE_X86").write_text(
        "x86", encoding="utf-8"
    )
    runtime = make_runtime(tmp_path / "arm-sdk", version="8.3.4")
    (runtime / "game" / "script.rpy").write_text(
        "# TEMPLATE\n", encoding="utf-8"
    )

    output = tmp_path / "ExampleGame-frame"
    result = build_game(game, runtime=runtime, output=output)

    assert result.success
    assert result.launcher_path is not None
    assert result.launcher_path.is_file()
    assert result.source_version == "8.3.2"
    assert result.runtime_version == "8.3.4"

    # Runtime copied
    assert (output / "renpy.sh").is_file()
    assert (output / "renpy" / "versions.py").is_file()
    assert (output / "lib" / "py3-linux-aarch64" / "python").is_file()

    # Template game replaced with source payload
    script = (output / "game" / "script.rpy").read_text(encoding="utf-8")
    assert "TEMPLATE" not in script
    assert "label start" in script
    assert (output / "game" / "archive.rpa").is_file()
    assert (output / "game" / "images" / "bg.png").is_file()
    assert (output / "game" / "audio" / "beep.ogg").is_file()

    # Source x86 runtime not copied
    assert not (output / "lib" / "py3-linux-x86_64").exists()
    assert not (output / "lib" / "py3-linux-aarch64" / "ONLY_SOURCE_X86").exists()

    # Launcher content
    launcher = result.launcher_path.read_text(encoding="utf-8")
    assert launcher.startswith("#!/usr/bin/env bash")
    assert "renpy.sh" in launcher
    assert 'exec "$ROOT/renpy.sh" "$ROOT" "$@"' in launcher

    if os.name != "nt":
        mode = result.launcher_path.stat().st_mode
        assert mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # Source unchanged
    assert (game / "game" / "script.rpy").is_file()
    assert (game / "lib" / "py3-linux-x86_64" / "ONLY_SOURCE_X86").is_file()

    # Dev junk ignored
    assert not (output / "__pycache__").exists()


def test_dry_run_copies_nothing(tmp_path: Path) -> None:
    game = make_game(tmp_path / "ExampleGame")
    runtime = make_runtime(tmp_path / "arm-sdk")
    output = tmp_path / "ExampleGame-frame"
    result = build_game(game, runtime=runtime, output=output, dry_run=True)
    assert result.success
    assert result.dry_run is True
    assert not output.exists()


def test_failure_cleans_temporary_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    game = make_game(tmp_path / "ExampleGame")
    runtime = make_runtime(tmp_path / "arm-sdk")
    output = tmp_path / "ExampleGame-frame"

    import renframe.builder as builder_mod

    real_copy = builder_mod._copy_runtime_and_game

    def boom(**kwargs):
        # Populate staging, then fail before atomic replace.
        real_copy(**kwargs)
        raise RuntimeError("simulated failure after staging")

    monkeypatch.setattr(builder_mod, "_copy_runtime_and_game", boom)

    with pytest.raises(BuildError, match="simulated failure"):
        build_game(game, runtime=runtime, output=output)

    assert not output.exists()
    leftovers = list(tmp_path.glob(".ExampleGame-frame.tmp-*"))
    assert leftovers == []


def test_failure_before_replace_leaves_existing_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    game = make_game(tmp_path / "ExampleGame")
    runtime = make_runtime(tmp_path / "arm-sdk")
    output = tmp_path / "ExampleGame-frame"
    output.mkdir()
    (output / "keep.txt").write_text("keep-me", encoding="utf-8")

    import renframe.builder as builder_mod

    def boom(*_a, **_k):
        raise RuntimeError("fail early in copy")

    monkeypatch.setattr(builder_mod, "_copy_runtime_and_game", boom)

    with pytest.raises(BuildError, match="fail early"):
        build_game(game, runtime=runtime, output=output, force=True)

    assert (output / "keep.txt").read_text(encoding="utf-8") == "keep-me"
