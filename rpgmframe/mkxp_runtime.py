"""Resolve a pinned Linux ARM64 mkxp-z runtime for RGSS games."""

from __future__ import annotations

import hashlib
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


DEFAULT_MKXPZ_REVISION = "37a04d1"
DEFAULT_MKXPZ_ARTIFACT_ID = 11271950906
DEFAULT_MKXPZ_ARTIFACT_SHA256 = (
    "3e0f3d6ed6486b672ed8988c180d2e6fd361622b5015cc245ce9c004ae5e3135"
)
DEFAULT_MKXPZ_DOWNLOAD_URL = (
    "https://nightly.link/mkxp-z/mkxp-z/actions/artifacts/"
    f"{DEFAULT_MKXPZ_ARTIFACT_ID}.zip"
)

ProgressCallback = Callable[[str], None]

_HTTP_HEADERS = {
    "User-Agent": "RPGMFrame/0.0.1 (+https://github.com/AZumD/RPGMFrame)",
    "Accept": "*/*",
}


class MkxpRuntimeError(RuntimeError):
    """Raised when the mkxp-z ARM64 runtime cannot be resolved safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inside(root: Path, candidate: Path) -> bool:
    return candidate == root or root in candidate.parents


def _safe_extract_zip(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    try:
        zipped = zipfile.ZipFile(archive)
    except (OSError, zipfile.BadZipFile) as exc:
        raise MkxpRuntimeError(f"Could not open mkxp-z artifact {archive}: {exc}") from exc

    with zipped:
        for info in zipped.infolist():
            target = (destination / info.filename).resolve()
            if not _inside(root, target):
                raise MkxpRuntimeError(
                    f"Refusing unsafe path in mkxp-z artifact: {info.filename}"
                )
            unix_mode = (info.external_attr >> 16) & 0o177777
            if stat.S_ISLNK(unix_mode):
                raise MkxpRuntimeError(
                    f"Refusing symlink in mkxp-z artifact: {info.filename}"
                )
        zipped.extractall(destination)


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers=_HTTP_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            with destination.open("wb") as handle:
                shutil.copyfileobj(response, handle, length=1024 * 1024)
    except (OSError, urllib.error.URLError) as exc:
        raise MkxpRuntimeError(
            "Failed to download the pinned mkxp-z ARM64 artifact. "
            "Retry later or supply an extracted runtime with --runtime. "
            f"URL: {url}: {exc}"
        ) from exc


class MkxpRuntimeManager:
    """Resolve the pinned upstream mkxp-z Linux ARM64 CI artifact."""

    def __init__(
        self,
        cache_dir: Path | str | None = None,
        *,
        revision: str = DEFAULT_MKXPZ_REVISION,
        download_url: str = DEFAULT_MKXPZ_DOWNLOAD_URL,
        expected_sha256: str = DEFAULT_MKXPZ_ARTIFACT_SHA256,
    ) -> None:
        configured = os.environ.get("RPGMFRAME_CACHE_DIR")
        if cache_dir is not None:
            root = Path(cache_dir)
        elif configured:
            root = Path(configured)
        else:
            root = Path.home() / ".cache" / "rpgmframe"

        self.cache_dir = root.expanduser().resolve() / "runtimes" / "mkxp-z"
        self.revision = revision
        self.download_url = download_url
        self.expected_sha256 = expected_sha256.casefold()

    def runtime_path(self) -> Path:
        return self.cache_dir / self.revision

    def _validate_cached(self, path: Path) -> bool:
        executable = path / "mkxp-z.aarch64"
        return (
            executable.is_file()
            and read_elf_architecture(executable) == "aarch64"
            and (path / "stdlib").is_dir()
            and (path / "scripts").is_dir()
            and (path / "LICENSE.txt").is_file()
        )

    def ensure_mkxpz(
        self,
        *,
        progress: ProgressCallback | None = None,
    ) -> Path:
        final = self.runtime_path()
        if self._validate_cached(final):
            if progress:
                progress(f"Using cached mkxp-z {self.revision}: {final}")
            return final

        final.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".download-",
            dir=final.parent,
        ) as temporary:
            temp_root = Path(temporary)
            archive = temp_root / "mkxp-z-linux-arm64.zip"

            if progress:
                progress(
                    "mkxp-z ARM64 is not cached; downloading pinned upstream "
                    f"artifact {self.revision}"
                )
            _download(self.download_url, archive)

            actual = _sha256(archive)
            if actual != self.expected_sha256:
                raise MkxpRuntimeError(
                    "SHA256 mismatch for mkxp-z artifact: "
                    f"expected {self.expected_sha256}, got {actual}"
                )
            if progress:
                progress("Verified SHA256 for pinned mkxp-z ARM64 artifact")

            extracted = temp_root / "extracted"
            _safe_extract_zip(archive, extracted)
            if not self._validate_cached(extracted):
                executable = extracted / "mkxp-z.aarch64"
                architecture = (
                    read_elf_architecture(executable)
                    if executable.is_file()
                    else None
                )
                raise MkxpRuntimeError(
                    "mkxp-z artifact did not contain the expected self-contained "
                    f"ARM64 runtime (binary architecture: {architecture or 'missing'})"
                )

            executable = extracted / "mkxp-z.aarch64"
            executable.chmod(executable.stat().st_mode | 0o755)

            if final.exists():
                shutil.rmtree(final)
            extracted.rename(final)

        if progress:
            progress(f"Cached mkxp-z {self.revision}: {final}")
        return final
