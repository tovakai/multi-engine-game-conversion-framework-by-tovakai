from __future__ import annotations

import json
from pathlib import Path

from megcfbt.router import inspect_source, output_path_for_source


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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
