import ast
import zipfile
from pathlib import Path

from renpy_arm.convert import create_zip_archive


def test_desktop_app_source_parses() -> None:
    source = Path("app/main.py").read_text(encoding="utf-8")
    ast.parse(source)


def test_create_zip_archive_reports_byte_progress(tmp_path: Path) -> None:
    game = tmp_path / "Game"
    game.mkdir()
    (game / "Game.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    payload = game / "game"
    payload.mkdir()
    (payload / "archive.rpa").write_bytes(b"x" * (2 * 1024 * 1024))

    events = []

    def progress(stage, fraction, detail):
        events.append((stage, fraction, detail))

    out = tmp_path / "Game-linux-aarch64.zip"
    create_zip_archive(
        game,
        "Game",
        out,
        progress=progress,
    )

    assert out.is_file()
    assert events
    assert events[-1][0] == "Creating output zip"
    assert events[-1][1] == 1.0
    assert any(
        stage == "Creating output zip" and fraction is not None and 0.0 < fraction < 1.0
        for stage, fraction, _detail in events
    )

    with zipfile.ZipFile(out) as zf:
        assert zf.read("Game/game/archive.rpa") == b"x" * (2 * 1024 * 1024)
