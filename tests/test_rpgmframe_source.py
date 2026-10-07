from __future__ import annotations

import stat
import zipfile
from pathlib import Path

import pytest

from rpgmframe.source import SourceError, prepare_source


def test_prepare_source_extracts_zip_to_temporary_workspace(tmp_path: Path) -> None:
    archive = tmp_path / "game.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("game/www/index.html", "<html></html>")

    extracted_root: Path | None = None
    with prepare_source(archive) as prepared:
        extracted_root = prepared.root
        assert prepared.archive_type == "zip"
        assert (prepared.root / "game/www/index.html").is_file()

    assert extracted_root is not None
    assert not extracted_root.exists()


def test_prepare_source_rejects_zip_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("../escape.txt", "nope")

    with pytest.raises(SourceError, match="unsafe path"):
        with prepare_source(archive):
            pass


def test_prepare_source_rejects_zip_symlink(tmp_path: Path) -> None:
    archive = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16

    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr(info, "../outside")

    with pytest.raises(SourceError, match="symlink"):
        with prepare_source(archive):
            pass


def test_prepare_source_rejects_unknown_archive_type(tmp_path: Path) -> None:
    archive = tmp_path / "game.rar"
    archive.write_bytes(b"not actually a rar")

    with pytest.raises(SourceError, match="currently accepts directories and .zip"):
        with prepare_source(archive):
            pass
