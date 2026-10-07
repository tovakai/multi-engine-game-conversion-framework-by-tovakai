from __future__ import annotations

import struct
from pathlib import Path

from rpgmframe.detector import inspect_game
from rpgmframe.godot import PCK_MAGIC, find_godot_pack, materialize_pack
from rpgmframe.models import Compatibility, EngineFamily, EngineVariant


def _pck_bytes(version: tuple[int, int, int] = (4, 3, 0)) -> bytes:
    major, minor, patch = version
    return struct.pack("<IIIII", PCK_MAGIC, 3, major, minor, patch) + b"fixture"


def test_detects_standalone_godot_pck(tmp_path: Path) -> None:
    (tmp_path / "Tiny Game.exe").write_bytes(b"MZ")
    (tmp_path / "Tiny Game.pck").write_bytes(_pck_bytes())

    result = inspect_game(tmp_path)

    assert result.family is EngineFamily.GODOT
    assert result.engine is EngineVariant.GODOT
    assert result.runtime == "godot"
    assert result.engine_version == "4.3.0"
    assert result.game_name == "Tiny Game"
    assert result.compatibility is Compatibility.NEEDS_TESTING


def test_detects_and_extracts_embedded_godot_pck(tmp_path: Path) -> None:
    pck = _pck_bytes((4, 2, 2))
    exe = tmp_path / "Embedded.exe"
    exe.write_bytes(b"MZ" + b"\0" * 62 + pck + struct.pack("<QI", len(pck), PCK_MAGIC))

    result = inspect_game(tmp_path)

    assert result.engine is EngineVariant.GODOT
    assert result.engine_version == "4.2.2"
    assert any("embedded" in warning.lower() for warning in result.warnings)

    pack = find_godot_pack(tmp_path)
    assert pack is not None and pack.embedded
    extracted = tmp_path / "out.pck"
    materialize_pack(pack, extracted)
    assert extracted.read_bytes() == pck


def test_multiple_godot_packs_are_not_guessed(tmp_path: Path) -> None:
    (tmp_path / "a.pck").write_bytes(_pck_bytes())
    (tmp_path / "b.pck").write_bytes(_pck_bytes())

    result = inspect_game(tmp_path)

    assert result.family is EngineFamily.GODOT
    assert not result.recognized
    assert any("Multiple Godot game packs" in warning for warning in result.warnings)


def test_godot_csharp_export_is_recognized_but_not_buildable(tmp_path: Path) -> None:
    (tmp_path / "Game.pck").write_bytes(_pck_bytes())
    (tmp_path / "Game.runtimeconfig.json").write_text("{}", encoding="utf-8")

    result = inspect_game(tmp_path)

    assert result.engine is EngineVariant.GODOT
    assert result.compatibility is Compatibility.UNKNOWN
    assert any("C#/.NET" in warning for warning in result.warnings)
