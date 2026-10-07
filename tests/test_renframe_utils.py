"""Tests for path safety helpers."""

from __future__ import annotations

from pathlib import Path

from renframe.utils import (
    is_ancestor,
    is_dangerous_output_path,
    is_path_inside,
    is_runtime_owned_path,
    normalize_path,
    paths_conflict,
    sanitize_fs_name,
)


def test_normalize_path_expands_user(tmp_path: Path, monkeypatch) -> None:
    # Path.expanduser() consults HOME on POSIX and USERPROFILE on Windows.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    path = normalize_path("~/game")
    assert path == (tmp_path / "game").resolve()


def test_refuse_root_output() -> None:
    assert is_dangerous_output_path(Path("/"))


def test_paths_conflict_same_and_nested(tmp_path: Path) -> None:
    source = tmp_path / "game"
    source.mkdir()
    assert paths_conflict(source, source)
    assert paths_conflict(source, source / "out")
    assert paths_conflict(source / "out", source)
    other = tmp_path / "elsewhere"
    other.mkdir()
    assert not paths_conflict(source, other)


def test_is_path_inside_and_ancestor(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)
    assert is_path_inside(child, parent)
    assert is_ancestor(parent, child)
    assert not is_ancestor(child, parent)


def test_sanitize_fs_name() -> None:
    assert sanitize_fs_name("Example Game") == "ExampleGame"
    assert sanitize_fs_name("My:Game*?") == "MyGame"
    assert sanitize_fs_name("@@@") == "Game"


def test_runtime_owned_path_rules() -> None:
    assert is_runtime_owned_path(Path("lib/py3-linux-x86_64/lib.so"))
    assert is_runtime_owned_path(Path("renpy/__init__.py"))
    assert is_runtime_owned_path(Path("Game.sh"))
    assert not is_runtime_owned_path(Path("game/python-packages/mod.so"))
    assert not is_runtime_owned_path(Path("game/script.rpy"))
