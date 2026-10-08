from __future__ import annotations

import hashlib
import shutil
import struct
import tarfile
from pathlib import Path

import pytest

from renframe.builder import build_game
from renframe.inspect_service import inspect_game
from renframe.runtime import (
    RuntimeDownloadError,
    RuntimeManager,
    _parse_sha256,
    normalize_release_version,
    python_tag_for_generation,
)


def _write_elf(path: Path, machine: int = 183) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = bytearray(64)
    header[:4] = b"\x7fELF"
    header[4] = 2
    header[5] = 1
    header[6] = 1
    struct.pack_into("<H", header, 16, 3)
    struct.pack_into("<H", header, 18, machine)
    path.write_bytes(header)


def _sdkarm_archive(path: Path, version: str = "8.5.3", tag: str = "py3") -> str:
    source = path.parent / "sdk-source"
    platform = source / f"renpy-{version}-sdk" / "lib" / f"{tag}-linux-aarch64"
    _write_elf(platform / "renpy")
    _write_elf(platform / "python")
    (platform / "payload.txt").write_text("arm runtime", encoding="utf-8")

    with tarfile.open(path, "w:bz2") as archive:
        archive.add(source / f"renpy-{version}-sdk", arcname=f"renpy-{version}-sdk")

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _renpy_game(root: Path, version: str = "8.5.3") -> Path:
    (root / "renpy").mkdir(parents=True)
    (root / "game").mkdir()
    (root / "lib/py3-linux-x86_64").mkdir(parents=True)
    (root / "renpy/__init__.py").write_text("# renpy\n", encoding="utf-8")
    (root / "renpy/versions.py").write_text(
        f'version = "{version}"\n',
        encoding="utf-8",
    )
    (root / "game/script.rpy").write_text(
        'label start:\n    "hello"\n',
        encoding="utf-8",
    )
    (root / "renpy.py").write_text("# launcher entry\n", encoding="utf-8")
    (root / "Game.sh").write_text(
        "#!/bin/sh\n"
        'UNAME="$(uname -s)-$(uname -m)"\n'
        'case "$UNAME" in\n'
        '    Linux-*)\n'
        '        RENPY_PLATFORM="linux-x86_64"\n'
        '        ;;\n'
        'esac\n'
        'exec "$RENPY_PLATFORM" "$@"\n',
        encoding="utf-8",
        newline="\n",
    )
    return root


def test_normalizes_exact_release_versions() -> None:
    assert normalize_release_version("8.5.3") == "8.5.3"
    assert normalize_release_version("8.5.3.26051504") == "8.5.3"
    with pytest.raises(RuntimeDownloadError):
        normalize_release_version("8.5")


def test_python_tag_tracks_renpy_generation() -> None:
    assert python_tag_for_generation(8) == "py3"
    assert python_tag_for_generation(7) == "py2"
    with pytest.raises(RuntimeDownloadError):
        python_tag_for_generation(6)


def test_checksum_parser_uses_sha256_section() -> None:
    filename = "renpy-8.5.3-sdkarm.tar.bz2"
    digest = "a" * 64
    text = (
        "-----BEGIN PGP SIGNED MESSAGE-----\n"
        "Hash: SHA512\n"
        "# md5\n"
        + ("b" * 32)
        + f" {filename}\n"
        "# sha256\n"
        + digest
        + f" {filename}\n"
    )
    assert _parse_sha256(text, filename) == digest


def test_runtime_manager_downloads_verifies_extracts_and_reuses_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "renpy-8.5.3-sdkarm.tar.bz2"
    digest = _sdkarm_archive(archive)
    manager = RuntimeManager(
        cache_dir=tmp_path / "cache",
        base_url="https://example.invalid/dl",
    )

    checksums = f"# sha256\n{digest} {archive.name}\n"
    monkeypatch.setattr(manager, "_read_url", lambda url: checksums)

    calls = {"download": 0}

    def fake_download(
        url: str,
        destination: Path,
        *,
        progress,
    ) -> None:
        calls["download"] += 1
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(archive, destination)

    monkeypatch.setattr(manager, "_download", fake_download)

    first = manager.ensure_platform("8.5.3", "py3")
    second = manager.ensure_platform("8.5.3", "py3")

    assert first == second
    assert calls["download"] == 1
    assert first.name == "py3-linux-aarch64"
    assert (first / "renpy").is_file()
    assert (first / "payload.txt").read_text(encoding="utf-8") == "arm runtime"


def test_runtime_manager_refuses_versions_before_official_aarch64_support(
    tmp_path: Path,
) -> None:
    manager = RuntimeManager(cache_dir=tmp_path / "cache")
    with pytest.raises(RuntimeDownloadError, match="predates official Linux AArch64"):
        manager.ensure_platform("7.4.11", "py2")


def test_vc_version_source_recovers_exact_release(tmp_path: Path) -> None:
    root = _renpy_game(tmp_path / "game")
    (root / "renpy/versions.py").unlink()
    (root / "renpy/vc_version.py").write_text(
        "version = '8.5.3.26051504'\n",
        encoding="utf-8",
    )

    result = inspect_game(root)

    assert result.is_renpy
    assert result.renpy_version == "8.5.3"
    assert result.version_source == "renpy/vc_version.py"


def test_automatic_builder_grafts_arm_platform_and_patches_launcher(
    tmp_path: Path,
) -> None:
    source = _renpy_game(tmp_path / "Synthetic")
    # Shipped Ren'Py installations can contain bytecode-only stdlib modules.
    stdlib = source / "lib" / "python3.9"
    (stdlib / "encodings").mkdir(parents=True)
    (stdlib / "encodings" / "__init__.pyc").write_bytes(b"bytecode")
    (stdlib / "__future__.pyc").write_bytes(b"bytecode")
    cache = stdlib / "__pycache__"
    cache.mkdir()
    (cache / "abc.cpython-39.pyc").write_bytes(b"bytecode")
    platform = tmp_path / "runtime" / "8.5.3" / "py3-linux-aarch64"
    _write_elf(platform / "renpy")
    (platform / "runtime-marker.txt").write_text("arm", encoding="utf-8")

    class FakeManager:
        def platform_path(self, version: str, python_tag: str) -> Path:
            assert version == "8.5.3"
            assert python_tag == "py3"
            return platform

        def ensure_platform(
            self,
            version: str,
            python_tag: str,
            *,
            progress=None,
            force: bool = False,
        ) -> Path:
            assert force is False
            return self.platform_path(version, python_tag)

    output = tmp_path / "Synthetic-frame"
    result = build_game(
        source,
        output=output,
        runtime_manager=FakeManager(),
    )

    assert result.success
    assert result.runtime_version == "8.5.3"
    assert result.runtime_architecture == "aarch64"
    assert result.launcher_path == output / "launch.sh"
    installer = (output / "add-to-steam.sh").read_text(encoding="utf-8")
    assert "steam://addnonsteamgame/" in installer
    assert "python3 -" in installer

    # The distributed engine/game remains the source of truth.
    assert (output / "renpy/versions.py").read_text(encoding="utf-8") == (
        'version = "8.5.3"\n'
    )
    assert (output / "game/script.rpy").is_file()
    assert (output / "lib/py3-linux-x86_64").is_dir()
    assert (output / "lib/python3.9/encodings/__init__.pyc").read_bytes() == b"bytecode"
    assert (output / "lib/python3.9/__future__.pyc").read_bytes() == b"bytecode"
    assert (output / "lib/python3.9/__pycache__/abc.cpython-39.pyc").read_bytes() == b"bytecode"

    # Only the exact ARM platform slice is grafted in.
    assert (output / "lib/py3-linux-aarch64/renpy").is_file()
    assert (output / "lib/py3-linux-aarch64/Game").is_file()
    assert (output / "lib/py3-linux-aarch64/runtime-marker.txt").read_text(
        encoding="utf-8"
    ) == "arm"

    patched = (output / "Game.sh").read_text(encoding="utf-8")
    assert "*-aarch64|*-arm64)" in patched
    assert 'RENPY_PLATFORM="linux-aarch64"' in patched

    launcher = (output / "launch.sh").read_text(encoding="utf-8")
    assert 'export RENPY_PLATFORM="linux-aarch64"' in launcher
    assert 'exec bash "$ROOT/Game.sh" "$ROOT" "$@"' in launcher
    assert 'chmod u+x "$binary"' in launcher
    assert 'RUNTIME_DIR="$ROOT/lib/py3-linux-aarch64"' in launcher


def test_automatic_builder_dry_run_does_not_download(tmp_path: Path) -> None:
    source = _renpy_game(tmp_path / "Synthetic")

    class NoDownloadManager:
        def platform_path(self, version: str, python_tag: str) -> Path:
            return tmp_path / "would-be-cache" / python_tag

        def ensure_platform(self, *args, **kwargs):
            raise AssertionError("dry-run must not download a runtime")

    output = tmp_path / "Synthetic-frame"
    result = build_game(
        source,
        output=output,
        dry_run=True,
        runtime_manager=NoDownloadManager(),
    )

    assert result.success
    assert not output.exists()
