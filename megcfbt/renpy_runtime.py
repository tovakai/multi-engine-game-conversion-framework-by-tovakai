"""Resolve official Ren'Py ARM64 SDK runtimes by exact detected version."""

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

from renframe.runtime import inspect_runtime

ProgressCallback = Callable[[str], None]

_GITHUB_RELEASES = "https://api.github.com/repos/renpy/renpy/releases"
_HEADERS = {
    "User-Agent": (
        "Multi-Engine-Game-Conversion-Framework-by-Tovakai/0.1 "
        "(+https://github.com/tovakai/"
        "multi-engine-game-conversion-framework-by-tovakai)"
    ),
    "Accept": "application/vnd.github+json",
}


class RenpyRuntimeError(RuntimeError):
    """Raised when an exact official Ren'Py ARM64 runtime cannot be resolved."""


def _normalize_version(version: str) -> str:
    value = version.strip()
    parts = value.split(".")
    if len(parts) not in {3, 4} or not all(part.isdigit() for part in parts):
        raise RenpyRuntimeError(
            "Automatic Ren'Py runtime resolution requires an exact numeric "
            f"version such as 8.5.3 or 8.5.3.26051504; got {version!r}"
        )
    # Official sdkarm asset names use the semantic X.Y.Z portion. When a
    # detector exposes Ren'Py's build suffix too, keep the release matching
    # conservative but use the official semantic asset name.
    return ".".join(parts[:3])


def _archive_name(version: str) -> str:
    return f"renpy-{_normalize_version(version)}-sdkarm.tar.bz2"


def _hash(path: Path, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _request_json(url: str) -> object:
    request = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
    except (OSError, urllib.error.URLError) as exc:
        raise RenpyRuntimeError(f"Could not query Ren'Py release metadata: {exc}") from exc

    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RenpyRuntimeError("Ren'Py release metadata was not valid JSON") from exc


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            with destination.open("wb") as handle:
                shutil.copyfileobj(response, handle, length=1024 * 1024)
    except (OSError, urllib.error.URLError) as exc:
        raise RenpyRuntimeError(f"Failed to download Ren'Py ARM64 runtime: {exc}") from exc


def _download_text(url: str) -> str:
    request = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
    except (OSError, urllib.error.URLError) as exc:
        raise RenpyRuntimeError(f"Failed to download Ren'Py checksum metadata: {exc}") from exc
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RenpyRuntimeError("Ren'Py checksum metadata was not UTF-8") from exc


def _checksum_from_text(text: str, filename: str) -> str:
    for raw in text.splitlines():
        parts = raw.strip().split()
        if len(parts) < 2:
            continue
        digest = parts[0].casefold()
        candidate = parts[-1].lstrip("*")
        if (
            candidate == filename
            and len(digest) == 64
            and all(ch in "0123456789abcdef" for ch in digest)
        ):
            return digest
    raise RenpyRuntimeError(
        f"Official Ren'Py checksums.txt has no SHA256 entry for {filename}"
    )


def _inside(root: Path, candidate: Path) -> bool:
    return candidate == root or root in candidate.parents


def _safe_extract_tar_bz2(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()

    with tarfile.open(archive, "r:bz2") as tar:
        for member in tar.getmembers():
            target = (destination / member.name).resolve()
            if not _inside(root, target):
                raise RenpyRuntimeError(
                    f"Refusing unsafe path in Ren'Py runtime archive: {member.name}"
                )

            if member.issym():
                link_target = (target.parent / member.linkname).resolve()
                if not _inside(root, link_target):
                    raise RenpyRuntimeError(
                        "Refusing unsafe symlink in Ren'Py runtime archive: "
                        f"{member.name} -> {member.linkname}"
                    )
            elif member.islnk():
                link_target = (destination / member.linkname).resolve()
                if not _inside(root, link_target):
                    raise RenpyRuntimeError(
                        "Refusing unsafe hardlink in Ren'Py runtime archive: "
                        f"{member.name} -> {member.linkname}"
                    )

        tar.extractall(destination)


def _release_asset(release: dict, filename: str) -> dict | None:
    assets = release.get("assets")
    if not isinstance(assets, list):
        return None
    for asset in assets:
        if isinstance(asset, dict) and asset.get("name") == filename:
            return asset
    return None


def _checksum_asset(release: dict) -> dict | None:
    assets = release.get("assets")
    if not isinstance(assets, list):
        return None
    for asset in assets:
        if isinstance(asset, dict) and asset.get("name") == "checksums.txt":
            return asset
    return None


def _find_runtime_root(extracted: Path) -> Path:
    candidates: list[Path] = []
    seen: set[Path] = set()

    possible = [extracted]
    try:
        possible.extend(path for path in extracted.iterdir() if path.is_dir())
    except OSError:
        pass
    possible.extend(
        path.parent
        for path in extracted.rglob("renpy")
        if path.is_dir() and path.parent not in seen
    )

    for candidate in possible:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        inspection = inspect_runtime(candidate)
        if (
            inspection.is_renpy_runtime
            and inspection.architecture in {"aarch64", "arm64"}
        ):
            candidates.append(candidate)

    if not candidates:
        raise RenpyRuntimeError(
            "Official Ren'Py sdkarm archive did not contain a recognizable "
            "ARM64 Ren'Py runtime"
        )

    candidates.sort(key=lambda path: (len(path.parts), str(path)))
    return candidates[0]


class RenpyRuntimeManager:
    """Download, verify, and cache official Ren'Py sdkarm releases."""

    def __init__(self, cache_dir: Path | str | None = None) -> None:
        configured = os.environ.get("TOVAKAI_CACHE_DIR")
        if cache_dir is not None:
            root = Path(cache_dir)
        elif configured:
            root = Path(configured)
        else:
            root = (
                Path.home()
                / ".cache"
                / "multi-engine-game-conversion-framework-by-tovakai"
            )
        self.cache_dir = root.expanduser().resolve() / "runtimes" / "renpy"

    def runtime_path(self, version: str) -> Path:
        return self.cache_dir / _normalize_version(version)

    def _validate_cached(self, path: Path, version: str) -> bool:
        if not path.is_dir():
            return False
        inspection = inspect_runtime(path)
        if not (
            inspection.is_renpy_runtime
            and inspection.architecture in {"aarch64", "arm64"}
        ):
            return False
        normalized = _normalize_version(version)
        if inspection.version and inspection.version != normalized:
            return False
        return True

    def _resolve_release(self, version: str) -> tuple[str, str, str]:
        normalized = _normalize_version(version)
        filename = _archive_name(normalized)

        for page in range(1, 7):
            value = _request_json(f"{_GITHUB_RELEASES}?per_page=100&page={page}")
            if not isinstance(value, list):
                raise RenpyRuntimeError(
                    "Ren'Py release metadata had an unexpected shape"
                )
            if not value:
                break

            for release in value:
                if (
                    not isinstance(release, dict)
                    or release.get("draft")
                    or release.get("prerelease")
                ):
                    continue

                asset = _release_asset(release, filename)
                if asset is None:
                    continue

                url = asset.get("browser_download_url")
                digest = asset.get("digest")
                if not isinstance(url, str):
                    raise RenpyRuntimeError(
                        f"Official Ren'Py {normalized} sdkarm asset has no download URL"
                    )

                if isinstance(digest, str) and digest.startswith("sha256:"):
                    expected = digest.split(":", 1)[1].casefold()
                    if len(expected) == 64:
                        return url, expected, str(release.get("tag_name") or normalized)

                sums = _checksum_asset(release)
                sums_url = sums.get("browser_download_url") if sums else None
                if not isinstance(sums_url, str):
                    raise RenpyRuntimeError(
                        f"Official Ren'Py {normalized} release has no published "
                        "checksum metadata for sdkarm"
                    )
                expected = _checksum_from_text(_download_text(sums_url), filename)
                return url, expected, str(release.get("tag_name") or normalized)

        raise RenpyRuntimeError(
            f"No official stable Ren'Py {normalized} release with "
            f"{filename} was found. Supply --renpy-runtime to override manually."
        )

    def ensure_runtime(
        self,
        version: str,
        *,
        progress: ProgressCallback | None = None,
    ) -> Path:
        normalized = _normalize_version(version)
        final = self.runtime_path(normalized)

        if self._validate_cached(final, normalized):
            if progress:
                progress(f"Using cached Ren'Py {normalized} ARM64 runtime: {final}")
            return final

        url, expected, tag = self._resolve_release(normalized)
        final.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(
            prefix=".download-",
            dir=final.parent,
        ) as temporary:
            temp_root = Path(temporary)
            archive = temp_root / _archive_name(normalized)

            if progress:
                progress(
                    f"Downloading official Ren'Py {normalized} ARM64 SDK "
                    f"({tag})"
                )
            _download(url, archive)

            actual = _hash(archive)
            if actual != expected:
                raise RenpyRuntimeError(
                    "SHA256 mismatch for Ren'Py ARM64 runtime: "
                    f"expected {expected}, got {actual}"
                )
            if progress:
                progress(f"Verified SHA256 for {_archive_name(normalized)}")

            extracted = temp_root / "extracted"
            _safe_extract_tar_bz2(archive, extracted)
            candidate = _find_runtime_root(extracted)

            if final.exists():
                shutil.rmtree(final, ignore_errors=True)
            shutil.copytree(candidate, final, symlinks=True)

        if not self._validate_cached(final, normalized):
            shutil.rmtree(final, ignore_errors=True)
            raise RenpyRuntimeError(
                f"Cached Ren'Py {normalized} runtime failed ARM64 validation"
            )

        if progress:
            progress(f"Cached Ren'Py {normalized} ARM64 runtime: {final}")
        return final
