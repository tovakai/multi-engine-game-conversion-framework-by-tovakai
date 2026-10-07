from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from rpgmframe.mkxp_runtime import MkxpRuntimeError, MkxpRuntimeManager


def _write_elf(path: Path, machine: int = 183) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = bytearray(64)
    header[:4] = b"\x7fELF"
    header[4] = 2
    header[5] = 1
    header[6] = 1
    header[18:20] = machine.to_bytes(2, "little")
    path.write_bytes(header)


def _artifact(tmp_path: Path, machine: int = 183) -> Path:
    payload = tmp_path / "payload"
    _write_elf(payload / "mkxp-z.aarch64", machine)
    (payload / "LICENSE.txt").write_text("GPL", encoding="utf-8")
    (payload / "stdlib").mkdir()
    (payload / "scripts").mkdir()

    archive = tmp_path / "mkxp-z.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for path in payload.rglob("*"):
            if path.is_file():
                zipped.write(path, path.relative_to(payload))
        zipped.writestr("stdlib/", "")
        zipped.writestr("scripts/", "")
    return archive


def test_downloads_verifies_and_reuses_mkxpz(tmp_path: Path) -> None:
    archive = _artifact(tmp_path)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    manager = MkxpRuntimeManager(
        cache_dir=tmp_path / "cache",
        revision="test",
        download_url=archive.as_uri(),
        expected_sha256=digest,
    )
    messages: list[str] = []

    first = manager.ensure_mkxpz(progress=messages.append)
    assert (first / "mkxp-z.aarch64").is_file()
    assert any("Verified SHA256" in message for message in messages)

    archive.unlink()
    messages.clear()
    second = manager.ensure_mkxpz(progress=messages.append)

    assert second == first
    assert any("Using cached" in message for message in messages)


def test_rejects_wrong_mkxpz_architecture(tmp_path: Path) -> None:
    archive = _artifact(tmp_path, machine=62)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    manager = MkxpRuntimeManager(
        cache_dir=tmp_path / "cache",
        revision="test",
        download_url=archive.as_uri(),
        expected_sha256=digest,
    )

    with pytest.raises(MkxpRuntimeError, match="expected self-contained ARM64"):
        manager.ensure_mkxpz()
