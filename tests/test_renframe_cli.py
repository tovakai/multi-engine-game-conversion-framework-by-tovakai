"""CLI-level tests for inspect output, build, and exit codes."""

from __future__ import annotations

import json
from pathlib import Path

from renframe.cli import EXIT_COMPATIBILITY, EXIT_ERROR, EXIT_INVALID_GAME, EXIT_OK, main
from tests.fixtures import make_game, make_runtime, write_elf, EM_X86_64


def test_inspect_human_report(tmp_path: Path, capsys) -> None:
    game = make_game(tmp_path / "Example Game")
    code = main(["inspect", str(game)])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert "RenFrame compatibility scan" in captured.out
    assert "Detected Ren'Py version: 8.3.2" in captured.out
    assert "LIKELY_COMPATIBLE" in captured.out


def test_inspect_json(tmp_path: Path, capsys) -> None:
    game = make_game(tmp_path / "JsonGame")
    code = main(["inspect", str(game), "--json"])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    payload = json.loads(captured.out)
    assert payload["is_renpy"] is True
    assert payload["renpy_version"] == "8.3.2"
    assert payload["compatibility"] == "LIKELY_COMPATIBLE"


def test_inspect_invalid_game_exit_code(tmp_path: Path, capsys) -> None:
    plain = tmp_path / "nope"
    plain.mkdir()
    code = main(["inspect", str(plain)])
    assert code == EXIT_INVALID_GAME


def test_inspect_incompatible_exit_code(tmp_path: Path, capsys) -> None:
    game = make_game(tmp_path / "BadNative", with_native_x86=True)
    code = main(["inspect", str(game)])
    assert code == EXIT_COMPATIBILITY


def test_build_requires_runtime_flag(tmp_path: Path, capsys) -> None:
    game = make_game(tmp_path / "Later")
    code = main(["build", str(game)])
    captured = capsys.readouterr()
    assert code == EXIT_ERROR
    assert "--runtime is required" in captured.err


def test_build_dry_run_cli(tmp_path: Path, capsys) -> None:
    game = make_game(tmp_path / "ExampleGame")
    runtime = make_runtime(tmp_path / "arm-sdk")
    code = main(
        [
            "build",
            str(game),
            "--runtime",
            str(runtime),
            "--dry-run",
        ]
    )
    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert "dry-run" in captured.out.lower()
    assert not (tmp_path / "ExampleGame-frame").exists()


def test_build_success_cli(tmp_path: Path, capsys) -> None:
    game = make_game(tmp_path / "ExampleGame")
    runtime = make_runtime(tmp_path / "arm-sdk")
    output = tmp_path / "out-frame"
    code = main(
        [
            "build",
            str(game),
            "--runtime",
            str(runtime),
            "--output",
            str(output),
        ]
    )
    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert "RenFrame build complete" in captured.out
    assert output.is_dir()
    assert any(output.glob("*.sh"))


def test_build_json_cli(tmp_path: Path, capsys) -> None:
    game = make_game(tmp_path / "ExampleGame")
    runtime = make_runtime(tmp_path / "arm-sdk")
    output = tmp_path / "json-frame"
    code = main(
        [
            "build",
            str(game),
            "--runtime",
            str(runtime),
            "--output",
            str(output),
            "--json",
        ]
    )
    captured = capsys.readouterr()
    assert code == EXIT_OK
    payload = json.loads(captured.out)
    assert payload["success"] is True
    assert payload["dry_run"] is False
    assert Path(payload["output_path"]) == output.resolve()


def test_build_incompatible_exit(tmp_path: Path, capsys) -> None:
    game = make_game(tmp_path / "Bad", with_native_x86=True)
    # ensure native is present (fixture already does)
    write_elf(game / "game" / "python-packages" / "extra.so", EM_X86_64)
    runtime = make_runtime(tmp_path / "arm-sdk")
    code = main(
        ["build", str(game), "--runtime", str(runtime), "--output", str(tmp_path / "x")]
    )
    captured = capsys.readouterr()
    assert code == EXIT_COMPATIBILITY
    assert "error:" in captured.err.lower()
