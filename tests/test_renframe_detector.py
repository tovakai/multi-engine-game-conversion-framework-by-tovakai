"""Tests for Ren'Py directory and version detection."""

from __future__ import annotations

from pathlib import Path

from renframe.detector import (
    collect_version_hints,
    looks_like_renpy_game,
    select_best_version,
    strategy_lib_python_generation,
    strategy_versions_py,
)
from renframe.inspect_service import inspect_game
from renframe.models import Compatibility


def _make_minimal_game(
    root: Path,
    *,
    version: str | None = "8.3.4",
    with_lib: str | None = "py3-linux-x86_64",
) -> Path:
    game = root / "game"
    renpy = root / "renpy"
    game.mkdir(parents=True)
    renpy.mkdir(parents=True)
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    (renpy / "__init__.py").write_text("# renpy\n", encoding="utf-8")
    if version is not None:
        (renpy / "versions.py").write_text(
            f'version = "{version}"\nvc_version = 2409600\n',
            encoding="utf-8",
        )
    if with_lib:
        (root / "lib" / with_lib).mkdir(parents=True)
    (root / "ExampleGame.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    return root


def test_detects_renpy_game(tmp_path: Path) -> None:
    game = _make_minimal_game(tmp_path / "MyGame")
    assert looks_like_renpy_game(game)


def test_rejects_non_renpy_directory(tmp_path: Path) -> None:
    plain = tmp_path / "notes"
    plain.mkdir()
    (plain / "readme.txt").write_text("hello", encoding="utf-8")
    assert not looks_like_renpy_game(plain)


def test_detects_game_scripts_without_full_renpy_tree(tmp_path: Path) -> None:
    root = tmp_path / "shipped"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "archive.rpa").write_bytes(b"RPA-3.0")
    (root / "lib" / "py3-linux-x86_64").mkdir(parents=True)
    (root / "Game.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    assert looks_like_renpy_game(root)


def test_version_from_versions_py(tmp_path: Path) -> None:
    game = _make_minimal_game(tmp_path / "VerGame", version="8.2.1")
    hint = strategy_versions_py(game)
    assert hint is not None
    assert hint.version == "8.2.1"
    assert hint.generation == 8


def test_generation_7_from_version(tmp_path: Path) -> None:
    game = _make_minimal_game(tmp_path / "OldGame", version="7.6.1", with_lib="py2-linux-x86_64")
    hints = collect_version_hints(game)
    best = select_best_version(hints)
    assert best is not None
    assert best.version == "7.6.1"
    assert best.generation == 7


def test_lib_python_generation_without_version_file(tmp_path: Path) -> None:
    game = _make_minimal_game(tmp_path / "NoVer", version=None, with_lib="py3-linux-x86_64")
    hint = strategy_lib_python_generation(game)
    assert hint is not None
    assert hint.version is None
    assert hint.generation == 8


def test_inspect_not_a_renpy_game(tmp_path: Path) -> None:
    plain = tmp_path / "empty"
    plain.mkdir()
    result = inspect_game(plain)
    assert result.compatibility == Compatibility.NOT_A_RENPY_GAME
    assert not result.is_renpy
