"""Tests for native dependency scanning and ownership."""

from __future__ import annotations

import struct
from pathlib import Path

from renframe.models import Compatibility, Ownership
from renframe.scanner import (
    classify_compatibility,
    classify_ownership,
    scan_native_dependencies,
)
from renframe.inspect_service import inspect_game


def _write_elf(path: Path, machine: int) -> None:
    data = bytearray(64)
    data[0:4] = b"\x7fELF"
    data[4] = 2
    data[5] = 1
    data[6] = 1
    struct.pack_into("<H", data, 16, 3)
    struct.pack_into("<H", data, 18, machine)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(data))


def _base_game(root: Path) -> Path:
    (root / "game").mkdir(parents=True)
    (root / "renpy").mkdir(parents=True)
    (root / "game" / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    (root / "renpy" / "__init__.py").write_text("# renpy\n", encoding="utf-8")
    (root / "renpy" / "versions.py").write_text('version = "8.3.4"\n', encoding="utf-8")
    (root / "lib" / "py3-linux-x86_64").mkdir(parents=True)
    return root


def test_runtime_vs_game_owned_libraries(tmp_path: Path) -> None:
    root = _base_game(tmp_path / "Game")
    runtime_so = root / "lib" / "py3-linux-x86_64" / "librenpy.so"
    game_so = root / "game" / "python-packages" / "foo.cpython-312-x86_64-linux-gnu.so"
    _write_elf(runtime_so, 62)
    _write_elf(game_so, 62)

    deps = scan_native_dependencies(root)
    by_name = {d.path.name: d for d in deps}

    assert by_name["librenpy.so"].ownership == Ownership.RUNTIME
    assert by_name["librenpy.so"].architecture == "x86_64"
    assert by_name["foo.cpython-312-x86_64-linux-gnu.so"].ownership == Ownership.GAME
    assert by_name["foo.cpython-312-x86_64-linux-gnu.so"].architecture == "x86_64"

    assert classify_ownership(root, runtime_so) == Ownership.RUNTIME
    assert classify_ownership(root, game_so) == Ownership.GAME


def test_runtime_x86_does_not_mark_incompatible(tmp_path: Path) -> None:
    root = _base_game(tmp_path / "Clean")
    _write_elf(root / "lib" / "py3-linux-x86_64" / "librenpy.so", 62)
    (root / "Example.exe").write_bytes(b"MZ\x00\x00")

    result = inspect_game(root)
    assert result.compatibility == Compatibility.LIKELY_COMPATIBLE
    assert any("Example.exe" in w for w in result.windows_executables)


def test_game_owned_x86_so_is_incompatible(tmp_path: Path) -> None:
    root = _base_game(tmp_path / "NativeMod")
    _write_elf(
        root / "game" / "python-packages" / "mod.so",
        62,
    )
    result = inspect_game(root)
    assert result.compatibility == Compatibility.INCOMPATIBLE_NATIVE_CODE
    assert any("mod.so" in issue for issue in result.potential_issues)


def test_classify_compatibility_unknown_version() -> None:
    compat, issues = classify_compatibility(
        is_renpy=True,
        renpy_version=None,
        generation=None,
        native_dependencies=[],
        warnings=[],
    )
    assert compat == Compatibility.UNKNOWN_RENPY_VERSION
    assert issues
