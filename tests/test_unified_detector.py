from __future__ import annotations

import json
import struct
import zipfile
from pathlib import Path

from multi_engine_game_conversion_framework_by_tovakai.detector import inspect_source
from multi_engine_game_conversion_framework_by_tovakai.models import Backend
from rpgmframe.godot import PCK_MAGIC


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _renpy_game(root: Path) -> Path:
    _write(root / "game/script.rpy", 'label start:\n    "hello"\n')
    _write(root / "renpy/__init__.py", '# RenPy engine\nversion = "8.3.4"\n')
    _write(root / "renpy/vc_version.py", 'version = "8.3.4"\n')
    _write(root / "lib/py3-linux-x86_64/.keep")
    _write(
        root / "TinyRenpy.sh",
        '#!/bin/sh\nRENPY_PLATFORM="linux-x86_64"\necho "$RENPY_PLATFORM"\n',
    )
    return root


def _mv_game(root: Path) -> Path:
    _write(
        root / "www/js/rpg_core.js",
        'Utils.RPGMAKER_VERSION = "1.6.1";\n',
    )
    _write(root / "www/data/System.json", json.dumps({"gameTitle": "Tiny MV"}))
    _write(root / "www/index.html", "<html></html>")
    _write(root / "package.json", json.dumps({"name": "tiny-mv", "main": "www/index.html"}))
    return root


def _godot_game(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    pck = struct.pack("<IIIII", PCK_MAGIC, 3, 4, 3, 0) + b"fixture"
    (root / "TinyGodot.pck").write_bytes(pck)
    return root


def test_detects_renpy(tmp_path: Path) -> None:
    info = inspect_source(_renpy_game(tmp_path / "renpy"))
    assert info.recognized
    assert info.backend is Backend.RENPY
    assert info.engine == "Ren'Py"
    assert info.engine_version == "8.3.4"
    assert info.buildable


def test_detects_rpg_maker_mv(tmp_path: Path) -> None:
    info = inspect_source(_mv_game(tmp_path / "mv"))
    assert info.recognized
    assert info.backend is Backend.RPGMFRAME
    assert info.family == "rpgmaker"
    assert info.engine == "RPG Maker MV"
    assert info.engine_version == "1.6.1"


def test_detects_godot(tmp_path: Path) -> None:
    info = inspect_source(_godot_game(tmp_path / "godot"))
    assert info.recognized
    assert info.backend is Backend.RPGMFRAME
    assert info.family == "godot"
    assert info.engine == "Godot"
    assert info.engine_version == "4.3.0"


def test_unknown_source_is_not_buildable(tmp_path: Path) -> None:
    root = tmp_path / "unknown"
    root.mkdir()
    _write(root / "readme.txt", "hello")
    info = inspect_source(root)
    assert not info.recognized
    assert info.backend is Backend.UNKNOWN
    assert not info.buildable


def test_zip_wrapper_is_inspected(tmp_path: Path) -> None:
    source = _mv_game(tmp_path / "source" / "TinyMV")
    archive = tmp_path / "TinyMV.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for path in source.rglob("*"):
            if path.is_file():
                z.write(path, Path("TinyMV") / path.relative_to(source))

    info = inspect_source(archive)
    assert info.recognized
    assert info.engine == "RPG Maker MV"


def test_zip_traversal_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("../escape.txt", "nope")

    info = inspect_source(archive)
    assert not info.recognized
    assert any("unsafe path" in warning.lower() for warning in info.warnings)
