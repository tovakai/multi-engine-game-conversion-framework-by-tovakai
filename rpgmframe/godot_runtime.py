"""Download, verify, and cache matching official Godot Linux ARM64 builds."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

from rpgmframe.elf import read_elf_architecture


ProgressCallback = Callable[[str], None]
_GITHUB_API = "https://api.github.com/repos/godotengine/godot/releases/tags"
_HEADERS = {
    "User-Agent": "RPGMFrame/0.0.1 (+https://github.com/AZumD/RPGMFrame)",
    "Accept": "application/vnd.github+json",
}


class GodotRuntimeError(RuntimeError):
    """Raised when a matching official Godot ARM64 runtime cannot be resolved."""


def _hash(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _request_json(url: str) -> dict:
    request = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
    except (OSError, urllib.error.URLError) as exc:
        raise GodotRuntimeError(f"Could not query Godot release metadata: {exc}") from exc
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GodotRuntimeError("Godot release metadata was not valid JSON") from exc
    if not isinstance(value, dict):
        raise GodotRuntimeError("Godot release metadata had an unexpected shape")
    return value


def _download_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except (OSError, urllib.error.URLError) as exc:
        raise GodotRuntimeError(f"Failed to download Godot checksum metadata: {exc}") from exc


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            with destination.open("wb") as handle:
                shutil.copyfileobj(response, handle, length=1024 * 1024)
    except (OSError, urllib.error.URLError) as exc:
        raise GodotRuntimeError(f"Failed to download Godot ARM64 runtime: {exc}") from exc


def _inside(root: Path, candidate: Path) -> bool:
    return candidate == root or root in candidate.parents


def _safe_extract_zip(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as zipped:
        for info in zipped.infolist():
            target = (destination / info.filename).resolve()
            if not _inside(root, target):
                raise GodotRuntimeError(
                    f"Refusing unsafe path in Godot runtime archive: {info.filename}"
                )
            unix_mode = (info.external_attr >> 16) & 0o177777
            if stat.S_ISLNK(unix_mode):
                raise GodotRuntimeError(
                    f"Refusing symlink in Godot runtime archive: {info.filename}"
                )
        zipped.extractall(destination)


def _parse_version(version: str) -> tuple[int, int, int]:
    parts = version.strip().split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise GodotRuntimeError(f"Invalid Godot version from PCK: {version!r}")
    return tuple(int(part) for part in parts)  # type: ignore[return-value]


def _candidate_tags(version: str) -> list[str]:
    major, minor, patch = _parse_version(version)
    tags = [f"{major}.{minor}.{patch}-stable"]
    if patch == 0:
        tags.insert(0, f"{major}.{minor}-stable")
    return tags


class GodotRuntimeManager:
    """Resolve the exact Godot release declared by a PCK header."""

    def __init__(self, cache_dir: Path | str | None = None) -> None:
        configured = os.environ.get("RPGMFRAME_CACHE_DIR")
        if cache_dir is not None:
            root = Path(cache_dir)
        elif configured:
            root = Path(configured)
        else:
            root = Path.home() / ".cache" / "rpgmframe"
        self.cache_dir = root.expanduser().resolve() / "runtimes" / "godot"

    def runtime_path(self, version: str) -> Path:
        return self.cache_dir / version

    def _validate_cached(self, path: Path) -> bool:
        binary = path / "godot.arm64"
        return binary.is_file() and read_elf_architecture(binary) == "aarch64"

    def _resolve_release(self, version: str) -> tuple[str, str, str, str]:
        last_error: Exception | None = None
        for tag in _candidate_tags(version):
            try:
                release = _request_json(f"{_GITHUB_API}/{tag}")
            except GodotRuntimeError as exc:
                last_error = exc
                continue

            expected_name = f"Godot_v{tag}_linux.arm64.zip"
            assets = release.get("assets")
            if not isinstance(assets, list):
                continue
            asset = next(
                (
                    item for item in assets
                    if isinstance(item, dict) and item.get("name") == expected_name
                ),
                None,
            )
            if asset is None:
                raise GodotRuntimeError(
                    f"Godot {tag} has no official Linux ARM64 binary. "
                    "This export is recognized, but cannot be converted automatically."
                )
            url = asset.get("browser_download_url")
            digest = asset.get("digest")
            if not isinstance(url, str):
                raise GodotRuntimeError(f"Godot {tag} ARM64 asset has no download URL")
            if isinstance(digest, str) and digest.startswith("sha256:"):
                return tag, url, "sha256", digest.split(":", 1)[1].casefold()

            sums = next(
                (
                    item for item in assets
                    if isinstance(item, dict) and item.get("name") == "SHA512-SUMS.txt"
                ),
                None,
            )
            sums_url = sums.get("browser_download_url") if sums else None
            if not isinstance(sums_url, str):
                raise GodotRuntimeError(
                    f"Godot {tag} ARM64 asset has no published checksum metadata"
                )
            try:
                lines = _download_bytes(sums_url).decode("utf-8").splitlines()
            except UnicodeDecodeError as exc:
                raise GodotRuntimeError("Godot SHA512 checksum file was not UTF-8") from exc
            expected = None
            for line in lines:
                parts = line.strip().split()
                if len(parts) >= 2 and parts[-1].lstrip("*") == expected_name:
                    expected = parts[0].casefold()
                    break
            if expected is None or len(expected) != 128:
                raise GodotRuntimeError(
                    f"Godot {tag} SHA512 file has no checksum for {expected_name}"
                )
            return tag, url, "sha512", expected

        raise GodotRuntimeError(
            f"No stable Godot release matching PCK version {version} was found"
            + (f": {last_error}" if last_error else "")
        )

    def ensure_godot(
        self,
        version: str,
        *,
        progress: ProgressCallback | None = None,
    ) -> Path:
        final = self.runtime_path(version)
        if self._validate_cached(final):
            if progress:
                progress(f"Using cached Godot {version} ARM64: {final}")
            return final

        tag, url, algorithm, expected = self._resolve_release(version)
        final.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix=".download-", dir=final.parent) as temporary:
            temp_root = Path(temporary)
            archive = temp_root / "godot-linux-arm64.zip"

            if progress:
                progress(f"Downloading official Godot {tag} Linux ARM64 runtime")
            _download(url, archive)
            actual = _hash(archive, algorithm)
            if actual != expected:
                raise GodotRuntimeError(
                    f"{algorithm.upper()} mismatch for Godot ARM64 runtime: "
                    f"expected {expected}, got {actual}"
                )
            if progress:
                progress(f"Verified {algorithm.upper()} for Godot ARM64 runtime")

            extracted = temp_root / "extracted"
            _safe_extract_zip(archive, extracted)
            binaries = [
                path
                for path in extracted.rglob("*")
                if path.is_file()
                and "linux.arm64" in path.name.casefold()
                and read_elf_architecture(path) == "aarch64"
            ]
            if len(binaries) != 1:
                raise GodotRuntimeError(
                    "Godot ARM64 archive did not contain one unambiguous AArch64 binary"
                )

            final.mkdir(parents=True, exist_ok=True)
            target = final / "godot.arm64"
            shutil.copy2(binaries[0], target)
            target.chmod(target.stat().st_mode | 0o755)

        if progress:
            progress(f"Cached Godot {version} ARM64: {final}")
        return final
