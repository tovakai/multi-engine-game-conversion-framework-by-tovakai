from __future__ import annotations

import importlib

from multi_engine_game_conversion_framework_by_tovakai.cli import APP_NAME, main


def test_unified_modules_import() -> None:
    for module in (
        "multi_engine_game_conversion_framework_by_tovakai.builder",
        "multi_engine_game_conversion_framework_by_tovakai.detector",
        "multi_engine_game_conversion_framework_by_tovakai.gui",
        "renpy_arm.convert",
        "renpy_arm.profiles",
        "rpgmframe.builder",
        "rpgmframe.godot_backend",
        "rpgmframe.mkxp_backend",
    ):
        importlib.import_module(module)


def test_backends_command_uses_full_application_name(capsys) -> None:
    assert main(["backends"]) == 0
    output = capsys.readouterr().out
    assert APP_NAME == "Multi-Engine Game Conversion Framework by Tovakai"
    assert APP_NAME in output
    assert "Ren'Py" in output
    assert "RPG Maker XP/VX/VX Ace" in output
    assert "Godot" in output


def test_parser_does_not_expose_half_imported_mod_library(capsys) -> None:
    try:
        main(["mod-library"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("mod-library unexpectedly remained a public subcommand")
    assert "invalid choice" in capsys.readouterr().err
