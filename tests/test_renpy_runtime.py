from __future__ import annotations

import hashlib
import io
import tarfile
from pathlib import Path

import pytest

from megcfbt import renpy_runtime
from megcfbt.renpy_runtime import (
    RenpyRuntimeError,
    RenpyRuntimeManager,
    _checksum_from_text,
    _normalize_version,
)


def _write_elf(path: Path, machine: int = 183) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = bytearray(64)
    header[:4] = b"\x7fELF"
    header[4] = 2
    header[5] = 1
    header[6] = 1
    header[18:20] = machine.to_bytes(2, "little")
    path.write_bytes(header)


def _fake_sdkarm(root: Path, version: str = "8.5.3") -> Path:
    sdk = root / f"renpy-{version}-sdkarm"
    (sdk / "renpy").mkdir(parents=True)
    (sdk / "renpy/__init__.py").write_text("# renpy\n", encoding="utf-8")
    (sdk / "renpy/versions.py").write_text(
        f'version = "{version}"\n',
        encoding="utf-8",
    )
    (sdk / "renpy.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    _write_elf(sdk / "lib/py3-linux-aarch64/python")
    return sdk


def _make_sdkarm_archive(path: Path, version: str = "8.5.3") -> str:
    source_root = path.parent / "sdk-source"
    sdk = _fake_sdkarm(source_root, version)
    with tarfile.open(path, "w:bz2") as tar:
        tar.add(sdk, arcname=sdk.name)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_normalizes_exact_renpy_version() -> None:
    assert _normalize_version("8.5.3") == "8.5.3"
    assert _normalize_version("8.5.3.26051504") == "8.5.3"
    with pytest.raises(RenpyRuntimeError):
        _normalize_version("8.5")


def test_checksum_parser_reads_official_style_line() -> None:
    digest = "a" * 64
    text = f"{digest}  renpy-8.5.3-sdkarm.tar.bz2\n"
    assert _checksum_from_text(text, "renpy-8.5.3-sdkarm.tar.bz2") == digest


def test_resolve_release_prefers_exact_sdkarm_asset_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filename = "renpy-8.5.3-sdkarm.tar.bz2"
    digest = "b" * 64
    pages = [
        [
            {
                "tag_name": "8.5.4.26070000",
                "draft": False,
                "prerelease": False,
                "assets": [
                    {
                        "name": "renpy-8.5.4-sdkarm.tar.bz2",
                        "browser_download_url": "https://example.invalid/8.5.4",
                        "digest": "sha256:" + ("c" * 64),
                    }
                ],
            },
            {
                "tag_name": "8.5.3.26051504",
                "draft": False,
                "prerelease": False,
                "assets": [
                    {
                        "name": filename,
                        "browser_download_url": "https://example.invalid/8.5.3",
                        "digest": "sha256:" + digest,
                    }
                ],
            },
        ]
    ]

    monkeypatch.setattr(
        renpy_runtime,
        "_request_json",
        lambda url: pages[0] if "page=1" in url else [],
    )

    manager = RenpyRuntimeManager(cache_dir=tmp_path)
    url, expected, tag = manager._resolve_release("8.5.3")

    assert url == "https://example.invalid/8.5.3"
    assert expected == digest
    assert tag == "8.5.3.26051504"


def test_resolve_release_uses_checksums_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filename = "renpy-7.8.7-sdkarm.tar.bz2"
    digest = "d" * 64
    release = {
        "tag_name": "7.8.7.25031702",
        "draft": False,
        "prerelease": False,
        "assets": [
            {
                "name": filename,
                "browser_download_url": "https://example.invalid/sdkarm",
                "digest": None,
            },
            {
                "name": "checksums.txt",
                "browser_download_url": "https://example.invalid/checksums",
            },
        ],
    }
    monkeypatch.setattr(
        renpy_runtime,
        "_request_json",
        lambda url: [release] if "page=1" in url else [],
    )
    monkeypatch.setattr(
        renpy_runtime,
        "_download_text",
        lambda url: f"{digest}  {filename}\n",
    )

    manager = RenpyRuntimeManager(cache_dir=tmp_path)
    url, expected, tag = manager._resolve_release("7.8.7")

    assert url == "https://example.invalid/sdkarm"
    assert expected == digest
    assert tag == "7.8.7.25031702"


def test_ensure_runtime_downloads_extracts_validates_and_caches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_archive = tmp_path / "fixture.tar.bz2"
    digest = _make_sdkarm_archive(source_archive)

    manager = RenpyRuntimeManager(cache_dir=tmp_path / "cache")
    monkeypatch.setattr(
        manager,
        "_resolve_release",
        lambda version: ("https://example.invalid/sdkarm", digest, "8.5.3.test"),
    )

    downloads = {"count": 0}

    def fake_download(url: str, destination: Path) -> None:
        downloads["count"] += 1
        destination.write_bytes(source_archive.read_bytes())

    monkeypatch.setattr(renpy_runtime, "_download", fake_download)

    first = manager.ensure_runtime("8.5.3")
    second = manager.ensure_runtime("8.5.3")

    assert first == second
    assert downloads["count"] == 1
    assert (first / "renpy.sh").is_file()
    assert (first / "lib/py3-linux-aarch64/python").is_file()
