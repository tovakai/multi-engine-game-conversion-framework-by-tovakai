"""Tests for safe published GodotSteam runtime resolution."""
from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from rpgmframe import godot_runtime_download as download
from rpgmframe.godot_custom_runtime import RECIPE_ID


def _write_index(tmp_path: Path, monkeypatch, *, data: dict) -> None:
    index = tmp_path / "index.json"
    index.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(download, "INDEX_PATH", index)


def test_no_published_recipe_by_default(tmp_path, monkeypatch):
    _write_index(tmp_path, monkeypatch, data={"recipes": {}})
    assert not download.downloadable(RECIPE_ID)


def test_rejects_untrusted_host(tmp_path, monkeypatch):
    _write_index(
        tmp_path, monkeypatch,
        data={"recipes": {RECIPE_ID: {
            "url": "https://example.org/untrusted.tar.gz",
            "sha256": "0" * 64,
        }}},
    )
    assert not download.downloadable(RECIPE_ID)


def test_download_verifies_archive_and_reuses_cache(tmp_path, monkeypatch):
    # Minimal ELF header sufficient for read_elf_architecture.
    elf = bytearray(64)
    elf[:4] = b"\x7fELF"
    elf[4] = 2
    elf[5] = 1
    elf[18:20] = (183).to_bytes(2, "little")
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as tar:
        for name, content in {
            "godot.arm64": bytes(elf),
            "runtime.json": json.dumps({"recipe_id": RECIPE_ID}).encode(),
        }.items():
            item = tarfile.TarInfo(name)
            item.size = len(content)
            tar.addfile(item, io.BytesIO(content))
    archive = payload.getvalue()
    digest = hashlib.sha256(archive).hexdigest()
    _write_index(
        tmp_path, monkeypatch,
        data={"recipes": {RECIPE_ID: {
            "url": "https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/releases/download/test/runtime.tar.gz",
            "sha256": digest,
        }}},
    )
    monkeypatch.setattr(download, "_cache_root", lambda: tmp_path / "cache")

    class Response(io.BytesIO):
        headers = {"Content-Length": str(len(archive))}
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.close()

    calls = []
    monkeypatch.setattr(
        download.urllib.request, "urlopen",
        lambda url, timeout: (calls.append(url), Response(archive))[1],
    )
    progress = []
    first = download.ensure_downloaded_runtime(
        RECIPE_ID, download_progress=lambda got, total: progress.append((got, total))
    )
    assert (first / "godot.arm64").is_file()
    assert progress[-1] == (len(archive), len(archive))
    assert download.ensure_downloaded_runtime(RECIPE_ID) == first
    assert len(calls) == 1


def test_rejects_wrong_digest(tmp_path, monkeypatch):
    _write_index(
        tmp_path, monkeypatch,
        data={"recipes": {RECIPE_ID: {
            "url": "https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/releases/download/test/runtime.tar.gz",
            "sha256": "0" * 64,
        }}},
    )
    monkeypatch.setattr(download, "_cache_root", lambda: tmp_path / "cache")
    class Response(io.BytesIO):
        headers = {"Content-Length": "3"}
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.close()
    monkeypatch.setattr(download.urllib.request, "urlopen", lambda url, timeout: Response(b"abc"))
    with pytest.raises(download.RuntimeDownloadError, match="SHA-256 mismatch"):
        download.ensure_downloaded_runtime(RECIPE_ID)
