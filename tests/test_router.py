from __future__ import annotations

import json
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from megcfbt.router import (
    ConversionError,
    build_source,
    inspect_source,
    output_path_for_source,
)


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_bytes(path: Path, content: bytes = b"") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _write_godot_pack(
    path: Path,
    *,
    major: int = 4,
    minor: int = 3,
    patch: int = 0,
) -> None:
    _write_bytes(path, struct.pack("<IIIII", 0x43504447, 3, major, minor, patch))


def test_detects_renpy_before_other_backends(tmp_path: Path) -> None:
    root = tmp_path / "renpy-game"
    _write(root / "renpy/__init__.py", '__version__ = "8.3.0"\n')
    _write(root / "renpy/versions.py", 'version = "8.3.0"\n')
    _write(root / "game/script.rpy", 'label start:\n    "hello"\n')
    _write(root / "Game.sh", "#!/bin/sh\n")

    result = inspect_source(root)

    assert result.backend == "renframe"
    assert result.engine == "renpy"
    assert result.engine_label == "Ren'Py"
    assert result.engine_version == "8.3.0"


def test_detects_rpg_maker_mv(tmp_path: Path) -> None:
    root = tmp_path / "mv-game"
    _write(
        root / "www/js/rpg_core.js",
        'Utils.RPGMAKER_VERSION = "1.6.1";\n',
    )
    _write(
        root / "www/data/System.json",
        json.dumps({"gameTitle": "Synthetic MV"}),
    )
    _write(root / "www/index.html", "<html></html>")
    _write(root / "package.json", json.dumps({"main": "www/index.html"}))

    result = inspect_source(root)

    assert result.backend == "rpgmframe"
    assert result.engine == "mv"
    assert result.engine_label == "RPG Maker MV"


def test_detects_nested_godot_with_sibling_wrapper_directories(tmp_path: Path) -> None:
    root = tmp_path / "wrapped-godot"
    (root / "steam_settings").mkdir(parents=True)
    game = root / "Brotato/common/Brotato"
    _write_bytes(game / "Brotato.exe", b"MZ")
    _write_godot_pack(game / "Brotato.pck")
    _write_godot_pack(game / "BrotatoAbyssalTerrors.pck")

    result = inspect_source(root)

    assert result.backend == "rpgmframe"
    assert result.engine == "godot"
    assert result.engine_label == "Godot"
    assert result.game_name == "Brotato"
    assert result.buildable is True
    assert any("subfolder" in warning.lower() for warning in result.warnings)



def test_custom_godot_build_is_detected_without_executing_it(tmp_path: Path) -> None:
    root = tmp_path / "custom-godot"
    game = root / "Brotato"
    _write_bytes(
        game / "Brotato.exe",
        (
            b"MZ\\x00"
            b"3.7.dev.custom_build\\x00"
            b"modules/godotsteam/godotsteam.cpp\\x00"
            b"get_godotsteam_version\\x00"
        ),
    )
    _write_godot_pack(game / "Brotato.pck", major=3, minor=7, patch=0)

    result = inspect_source(root)

    assert result.backend == "rpgmframe"
    assert result.engine == "godot"
    assert result.engine_version == "3.7.0"
    assert result.buildable is False
    assert result.runtime_kind == "godot-custom"
    assert any("custom godot development build" in warning.lower() for warning in result.warnings)
    assert any("godotsteam" in warning.lower() for warning in result.warnings)
    assert any("godotsteam" in evidence.lower() for evidence in result.evidence)



def _write_custom_godot_export(root: Path) -> Path:
    game = root / "Brotato"
    _write_bytes(
        game / "Brotato.exe",
        (
            b"MZ\\x00"
            b"3.7.dev.custom_build\\x00"
            b"modules/godotsteam/godotsteam.cpp\\x00"
            b"get_godotsteam_version\\x00"
        ),
    )
    _write_godot_pack(game / "Brotato.pck", major=3, minor=7, patch=0)
    return game


def test_custom_godot_build_requires_runtime_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "custom-godot"
    _write_custom_godot_export(root)
    # Simulate a recipe that is neither published nor buildable locally.
    # Published recipes are intentionally usable on Windows now.
    monkeypatch.setattr(
        "megcfbt.router.downloadable",
        lambda recipe: False,
    )
    monkeypatch.setattr(
        "megcfbt.router.host_can_build_automatic_runtime",
        lambda: False,
    )

    with pytest.raises(ConversionError, match="custom ARM64 runtime"):
        build_source(root, output=tmp_path / "out", archive=False)


def test_custom_godot_automatic_runtime_reaches_backend_without_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "custom-godot"
    _write_custom_godot_export(root)
    output = tmp_path / "out"
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        "megcfbt.router.host_can_build_automatic_runtime",
        lambda: True,
    )

    def fake_build(path, **kwargs):
        seen["path"] = path
        seen["runtime"] = kwargs.get("runtime")
        return SimpleNamespace(
            launcher_path=output / "launch.sh",
            warnings=[],
            game_name="Brotato",
            engine_version="3.7.0",
        )

    monkeypatch.setattr("megcfbt.router.build_rpgm_game", fake_build)

    result = build_source(
        root,
        output=output,
        archive=False,
    )

    assert seen["runtime"] is None
    assert result.engine == "godot"
    assert result.game_name == "Brotato"


def test_custom_godot_runtime_override_reaches_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "custom-godot"
    _write_custom_godot_export(root)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    output = tmp_path / "out"
    seen: dict[str, object] = {}

    def fake_build(path, **kwargs):
        seen["path"] = path
        seen["runtime"] = kwargs.get("runtime")
        return SimpleNamespace(
            launcher_path=output / "launch.sh",
            warnings=[],
            game_name="Brotato",
            engine_version="3.7.0",
        )

    monkeypatch.setattr("megcfbt.router.build_rpgm_game", fake_build)

    result = build_source(
        root,
        output=output,
        backend_runtime=runtime,
        archive=False,
    )

    assert seen["runtime"] == runtime
    assert result.engine == "godot"
    assert result.game_name == "Brotato"


def test_detects_nested_rpg_maker_with_sibling_wrapper_directories(tmp_path: Path) -> None:
    root = tmp_path / "wrapped-mz"
    (root / "steam_settings").mkdir(parents=True)
    game = root / "Game/common/Game"
    _write(game / "js/rmmz_core.js", 'Utils.RPGMAKER_VERSION = "1.8.0";\n')
    _write(game / "data/System.json", json.dumps({"gameTitle": "Nested MZ"}))
    _write(game / "index.html", "<html></html>")
    _write(game / "package.json", json.dumps({"name": "nested-mz"}))

    result = inspect_source(root)

    assert result.backend == "rpgmframe"
    assert result.engine == "mz"
    assert result.game_name == "Nested MZ"
    assert result.buildable is True
    assert any("subfolder" in warning.lower() for warning in result.warnings)

def test_unknown_source_is_not_buildable(tmp_path: Path) -> None:
    root = tmp_path / "mystery"
    root.mkdir()
    _write(root / "readme.txt", "nothing to see here")

    result = inspect_source(root)

    assert result.backend is None
    assert result.engine == "unknown"
    assert result.buildable is False


def test_unwraps_single_directory_archives_for_renpy(tmp_path: Path) -> None:
    import zipfile

    archive = tmp_path / "wrapped.zip"
    staging = tmp_path / "staging"
    _write(staging / "Some Game/renpy/__init__.py", '# RenPy\n')
    _write(staging / "Some Game/renpy/versions.py", 'version = "8.2.1"\n')
    _write(staging / "Some Game/game/script.rpy", "label start:\n    pass\n")
    _write(staging / "Some Game/Game.sh", "#!/bin/sh\n")

    with zipfile.ZipFile(archive, "w") as z:
        for path in (staging / "Some Game").rglob("*"):
            if path.is_file():
                z.write(path, path.relative_to(staging))

    result = inspect_source(archive)

    assert result.backend == "renframe"
    assert result.engine_version == "8.2.1"


def test_output_name_keeps_the_stupidly_simple_frame_suffix(tmp_path: Path) -> None:
    source = tmp_path / "game.zip"
    expected = tmp_path / "out/game-frame"
    assert output_path_for_source(source, tmp_path / "out") == expected
