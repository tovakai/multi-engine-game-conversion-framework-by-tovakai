from __future__ import annotations

import hashlib
import io
import tarfile
from pathlib import Path

import pytest

from rpgmframe.runtime import RuntimeError, RuntimeManager, _request


def _write_elf(path: Path, machine: int = 183) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = bytearray(64)
    header[:4] = b"\x7fELF"
    header[4] = 2
    header[5] = 1
    header[6] = 1
    header[18:20] = machine.to_bytes(2, "little")
    path.write_bytes(header)


def _fake_remote(root: Path, version: str = "0.117.0") -> tuple[Path, str]:
    version_dir = root / f"v{version}"
    payload = root / "payload" / f"nwjs-v{version}-linux-arm64"
    _write_elf(payload / "nw")
    (payload / "resources.pak").write_text("runtime", encoding="utf-8")

    version_dir.mkdir(parents=True)
    filename = f"nwjs-v{version}-linux-arm64.tar.gz"
    archive = version_dir / filename
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(payload, arcname=payload.name)

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (version_dir / "SHASUMS256.txt").write_text(
        f"{digest}  {filename}\n",
        encoding="utf-8",
    )
    return version_dir, filename


def test_downloads_verifies_and_reuses_cached_runtime(tmp_path: Path) -> None:
    remote = tmp_path / "remote"
    version_dir, _ = _fake_remote(remote)
    manager = RuntimeManager(
        cache_dir=tmp_path / "cache",
        download_root=remote.as_uri(),
    )
    messages: list[str] = []

    first = manager.ensure_nwjs("0.117.0", progress=messages.append)

    assert (first / "nw").is_file()
    assert (first / "resources.pak").is_file()
    assert any("Verified SHA256" in message for message in messages)

    for path in version_dir.iterdir():
        path.unlink()

    messages.clear()
    second = manager.ensure_nwjs("v0.117.0", progress=messages.append)

    assert second == first
    assert any("Using cached" in message for message in messages)


def test_rejects_checksum_mismatch(tmp_path: Path) -> None:
    remote = tmp_path / "remote"
    version_dir, filename = _fake_remote(remote)
    (version_dir / "SHASUMS256.txt").write_text(
        f"{'0' * 64}  {filename}\n",
        encoding="utf-8",
    )
    manager = RuntimeManager(
        cache_dir=tmp_path / "cache",
        download_root=remote.as_uri(),
    )

    with pytest.raises(RuntimeError, match="SHA256 mismatch"):
        manager.ensure_nwjs("0.117.0")


def test_rejects_archive_path_traversal(tmp_path: Path) -> None:
    remote = tmp_path / "remote"
    version = "0.117.0"
    version_dir = remote / f"v{version}"
    version_dir.mkdir(parents=True)
    filename = f"nwjs-v{version}-linux-arm64.tar.gz"
    archive = version_dir / filename

    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo("../escape")
        data = b"nope"
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (version_dir / "SHASUMS256.txt").write_text(
        f"{digest}  {filename}\n",
        encoding="utf-8",
    )

    manager = RuntimeManager(
        cache_dir=tmp_path / "cache",
        download_root=remote.as_uri(),
    )

    with pytest.raises(RuntimeError, match="unsafe path"):
        manager.ensure_nwjs(version)


def test_http_request_uses_explicit_user_agent() -> None:
    request = _request("https://dl.nwjs.io/v0.117.0/SHASUMS256.txt")

    assert request.get_header("User-agent")
    assert not request.get_header("User-agent").startswith("Python-urllib")
    assert request.get_header("Accept") == "*/*"
