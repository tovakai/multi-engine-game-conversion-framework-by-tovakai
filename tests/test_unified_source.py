from pathlib import Path

from multi_engine_game_conversion_framework_by_tovakai.source import source_base_name


def test_source_base_name_strips_transfer_archive_suffixes() -> None:
    assert source_base_name(Path("Game.zip")) == "Game"
    assert source_base_name(Path("Game.tar.gz")) == "Game"
    assert source_base_name(Path("Game.tgz")) == "Game"
    assert source_base_name(Path("Game")) == "Game"
