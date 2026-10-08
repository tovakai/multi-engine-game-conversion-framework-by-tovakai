"""Verified, cached GitHub Release runtime downloads.

Only recipes explicitly listed in the shipped runtime index are eligible.
Never download an arbitrary executable based on a game's untrusted metadata.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from rpgmframe.elf import read_elf_architecture
from rpgmframe.godot_custom_runtime import RECIPE_ID

INDEX_PATH = Path(__file__).resolve().parent / "godot_runtime_index.json"
BUILTIN_RECIPES = {
    RECIPE_ID: {
        "url": (
            "https://github.com/tovakai/"
            "multi-engine-game-conversion-framework-by-tovakai/releases/download/"
            "runtime-godot-3.7-dev1-godotsteam-3.30-arm64-v1/"
            "godot-3.7-dev1-godotsteam-3.30-frame-arm64-v1.tar.gz"
        ),
        "sha256": "f87130aa44fae591a098eb03df8a419f84b47d25100756f04bb645e44102e34a",
        "status": "validated",
    }
}
DownloadProgress = Callable[[int, int | None], None]


class RuntimeDownloadError(RuntimeError):
    pass


def recipe_entry(recipe_id: str) -> dict | None:
    if recipe_id != RECIPE_ID:
        return None
    try:
        index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        index = {"recipes": BUILTIN_RECIPES}
    try:
        entry = index["recipes"][recipe_id]
    except (KeyError, TypeError):
        return None
    if not isinstance(entry, dict):
        return None
    url, digest = entry.get("url"), entry.get("sha256")
    if not isinstance(url, str) or not url.startswith(
        "https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/releases/download/"
    ):
        return None
    if not isinstance(digest, str) or len(digest) != 64:
        return None
    try:
        int(digest, 16)
    except ValueError:
        return None
    return entry


def downloadable(recipe_id: str) -> bool:
    return recipe_entry(recipe_id) is not None


def _validate(path: Path, recipe_id: str) -> bool:
    binary = path / "godot.arm64"
    manifest = path / "runtime.json"
    if not binary.is_file() or not manifest.is_file():
        return False
    if read_elf_architecture(binary) != "aarch64":
        return False
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return (
        isinstance(data, dict)
        and (data.get("recipe_id") == recipe_id
             or data.get("recipe") == "godot-3.7-dev1-godotsteam-3.30-arm64")
    )


def _cache_root() -> Path:
    configured = os.environ.get("RPGMFRAME_CACHE_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "tovakai" / "cache"
    return Path.home() / ".cache" / "tovakai"


def ensure_downloaded_runtime(
    recipe_id: str,
    *,
    progress: Callable[[str], None] | None = None,
    download_progress: DownloadProgress | None = None,
) -> Path:
    entry = recipe_entry(recipe_id)
    if entry is None:
        raise RuntimeDownloadError(f"No published runtime for recipe {recipe_id}")

    target = _cache_root() / "runtimes" / "godot-custom" / recipe_id
    if _validate(target, recipe_id):
        if progress:
            progress("Using cached custom GodotSteam ARM64 runtime")
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".godotsteam-", dir=target.parent) as temp:
        tmp = Path(temp)
        archive = tmp / "runtime.tar.gz"
        digest = hashlib.sha256()
        count = 0
        if progress:
            progress("Downloading custom GodotSteam ARM64 runtime…")
        try:
            with urllib.request.urlopen(entry["url"], timeout=45) as response:
                length_header = response.headers.get("Content-Length")
                total = int(length_header) if length_header and length_header.isdigit() else None
                with archive.open("wb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        count += len(chunk)
                        if count > 2 * 1024**3:
                            raise RuntimeDownloadError("Runtime download exceeds 2 GiB limit")
                        digest.update(chunk)
                        output.write(chunk)
                        if download_progress:
                            download_progress(count, total)
        except (OSError, urllib.error.URLError) as exc:
            raise RuntimeDownloadError(f"Could not download custom runtime: {exc}") from exc

        if progress:
            progress("Verifying downloaded runtime SHA-256…")
        if digest.hexdigest().lower() != entry["sha256"].lower():
            raise RuntimeDownloadError("Runtime download SHA-256 mismatch; refusing to use it")

        extracted = tmp / "extracted"
        extracted.mkdir()
        with tarfile.open(archive, "r:gz") as tar:
            members = tar.getmembers()
            for member in members:
                # Release archive must have flat regular files only. Never
                # extract symlinks, absolute paths, or parent traversal.
                if not member.isfile() or member.name not in {
                    "godot.arm64", "runtime.json"
                }:
                    raise RuntimeDownloadError(
                        f"Unsafe or unexpected runtime archive member: {member.name}"
                    )
                source = tar.extractfile(member)
                if source is None:
                    raise RuntimeDownloadError("Unreadable runtime archive member")
                with source, (extracted / member.name).open("wb") as dest:
                    shutil.copyfileobj(source, dest)
        if not _validate(extracted, recipe_id):
            raise RuntimeDownloadError("Downloaded runtime failed ARM64/recipe validation")
        (extracted / "godot.arm64").chmod(0o755)
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(extracted), str(target))
    if progress:
        progress("Custom GodotSteam runtime cached. Continuing conversion…")
    return target
