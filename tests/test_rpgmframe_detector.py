from __future__ import annotations

import json
from pathlib import Path

from rpgmframe.detector import inspect_game
from rpgmframe.models import Compatibility, Confidence, EngineVariant


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_system(path: Path, title: str) -> None:
    _write(path, json.dumps({"gameTitle": title}))


def test_detects_windows_mv_layout(tmp_path: Path) -> None:
    _write(
        tmp_path / "www/js/rpg_core.js",
        'Utils.RPGMAKER_VERSION = "1.6.2";\n',
    )
    _write_system(tmp_path / "www/data/System.json", "MV Test Game")
    _write(tmp_path / "www/index.html", "<html></html>")
    _write(
        tmp_path / "package.json",
        json.dumps({"name": "mv-test", "main": "www/index.html"}),
    )

    result = inspect_game(tmp_path)

    assert result.engine is EngineVariant.MV
    assert result.runtime == "nwjs"
    assert result.compatibility is Compatibility.SUPPORTED
    assert result.confidence is Confidence.HIGH
    assert result.game_root == tmp_path / "www"
    assert result.game_name == "MV Test Game"
    assert result.engine_version == "1.6.2"
    assert result.package_json == tmp_path / "package.json"


def test_detects_mv_when_payload_root_is_selected(tmp_path: Path) -> None:
    _write(tmp_path / "js/rpg_core.js", 'Utils.RPGMAKER_VERSION = "1.5.1";')
    _write_system(tmp_path / "data/System.json", "Bare MV")

    result = inspect_game(tmp_path)

    assert result.engine is EngineVariant.MV
    assert result.game_root == tmp_path
    assert result.game_name == "Bare MV"
    assert result.engine_version == "1.5.1"


def test_detects_mz_layout(tmp_path: Path) -> None:
    _write(
        tmp_path / "js/rmmz_core.js",
        'Utils.RPGMAKER_VERSION = "1.9.0";\n',
    )
    _write_system(tmp_path / "data/System.json", "MZ Test Game")
    _write(tmp_path / "index.html", "<html></html>")
    _write(
        tmp_path / "package.json",
        json.dumps({"name": "mz-test", "main": "index.html"}),
    )

    result = inspect_game(tmp_path)

    assert result.engine is EngineVariant.MZ
    assert result.runtime == "nwjs"
    assert result.confidence is Confidence.HIGH
    assert result.compatibility is Compatibility.SUPPORTED
    assert result.game_root == tmp_path
    assert result.game_name == "MZ Test Game"
    assert result.engine_version == "1.9.0"


def test_package_json_alone_is_not_treated_as_rpg_maker(tmp_path: Path) -> None:
    _write(tmp_path / "package.json", json.dumps({"name": "definitely-not-rpgmaker"}))

    result = inspect_game(tmp_path)

    assert result.engine is EngineVariant.UNKNOWN
    assert not result.recognized
    assert result.compatibility is Compatibility.UNKNOWN


def test_core_without_system_json_warns_but_is_recognized(tmp_path: Path) -> None:
    _write(tmp_path / "js/rmmz_core.js", 'Utils.RPGMAKER_VERSION = "1.8.0";')

    result = inspect_game(tmp_path)

    assert result.engine is EngineVariant.MZ
    assert result.recognized
    assert result.confidence is Confidence.LOW
    assert any("System.json" in warning for warning in result.warnings)


def test_equal_mv_mz_signatures_are_rejected_as_ambiguous(tmp_path: Path) -> None:
    _write(tmp_path / "js/rpg_core.js", "")
    _write(tmp_path / "js/rmmz_core.js", "")

    result = inspect_game(tmp_path)

    assert result.engine is EngineVariant.UNKNOWN
    assert not result.recognized
    assert any("Conflicting MV and MZ" in warning for warning in result.warnings)


def test_missing_path_is_not_recognized(tmp_path: Path) -> None:
    result = inspect_game(tmp_path / "missing")

    assert not result.recognized
    assert any("does not exist" in warning for warning in result.warnings)


def test_auto_descends_single_wrapper_directory(tmp_path: Path) -> None:
    wrapper = tmp_path / "jailbreak_win"
    _write(
        wrapper / "www/js/rpg_core.js",
        'Utils.RPGMAKER_VERSION = "1.6.1";\n',
    )
    _write_system(wrapper / "www/data/System.json", "Wrapped MV")
    _write(wrapper / "www/index.html", "<html></html>")
    _write(
        wrapper / "package.json",
        json.dumps({"name": "wrapped-mv", "main": "www/index.html"}),
    )

    result = inspect_game(tmp_path)

    assert result.engine is EngineVariant.MV
    assert result.game_root == wrapper / "www"
    assert result.package_json == wrapper / "package.json"
    assert result.game_name == "Wrapped MV"
    assert result.engine_version == "1.6.1"
    assert "jailbreak_win/www/js/rpg_core.js" in result.evidence
    assert any("Auto-descended" in warning for warning in result.warnings)


def test_auto_descends_multiple_wrapper_directories(tmp_path: Path) -> None:
    wrapper = tmp_path / "OMORI.v1.0.8d" / "OMORI"
    _write(
        wrapper / "www/js/rpg_core.js",
        'Utils.RPGMAKER_VERSION = "1.6.1";\n',
    )
    _write_system(wrapper / "www/data/System.json", "Deep Wrapped MV")
    _write(wrapper / "www/index.html", "<html></html>")
    _write(
        wrapper / "package.json",
        json.dumps({"name": "deep-mv", "main": "www/index.html"}),
    )

    result = inspect_game(tmp_path)

    assert result.engine is EngineVariant.MV
    assert result.game_root == wrapper / "www"
    assert result.package_json == wrapper / "package.json"
    assert "OMORI.v1.0.8d/OMORI/www/js/rpg_core.js" in result.evidence
    assert any("OMORI.v1.0.8d/OMORI" in warning for warning in result.warnings)


def test_detects_rpg_maker_xp_from_renamed_ini_and_archive(tmp_path: Path) -> None:
    _write(
        tmp_path / "To the Moon.ini",
        "[Game]\n"
        "Library=RGSS104E.dll\n"
        "Scripts=Data\\Scripts.rxdata\n"
        "Title=To the Moon\n"
        "RTP1=Standard\n",
    )
    _write(tmp_path / "To the Moon.rgssad", "encrypted fixture")

    result = inspect_game(tmp_path)

    assert result.engine is EngineVariant.XP
    assert result.runtime == "mkxp-z"
    assert result.compatibility is Compatibility.NEEDS_TESTING
    assert result.confidence is Confidence.HIGH
    assert result.game_root == tmp_path
    assert result.game_name == "To the Moon"
    assert result.engine_version == "RGSS104E"
    assert "To the Moon.ini" in result.evidence
    assert "To the Moon.rgssad" in result.evidence


def test_detects_rpg_maker_vx_from_scripts_data(tmp_path: Path) -> None:
    _write(
        tmp_path / "Game.ini",
        "[Game]\nLibrary=RGSS202E.dll\nScripts=Data\\Scripts.rvdata\nTitle=VX Game\n",
    )
    _write(tmp_path / "Data/Scripts.rvdata", "fixture")
    _write(tmp_path / "Data/System.rvdata", "fixture")

    result = inspect_game(tmp_path)

    assert result.engine is EngineVariant.VX
    assert result.runtime == "mkxp-z"
    assert result.game_name == "VX Game"


def test_detects_rpg_maker_vx_ace_from_scripts_data(tmp_path: Path) -> None:
    _write(
        tmp_path / "Game.ini",
        "[Game]\nLibrary=RGSS301.dll\nScripts=Data\\Scripts.rvdata2\nTitle=Ace Game\n",
    )
    _write(tmp_path / "Data/Scripts.rvdata2", "fixture")

    result = inspect_game(tmp_path)

    assert result.engine is EngineVariant.VX_ACE
    assert result.runtime == "mkxp-z"
    assert result.game_name == "Ace Game"
