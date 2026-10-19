"""Download, verify, cache, and resolve Linux ARM64 NW.js runtimes."""

from __future__ import annotations

from megcfbt.tls import failure_message, open_url

import hashlib
import http.client
import os
import shutil
import ssl
import tarfile
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from rpgmframe.elf import read_elf_architecture

DEFAULT_NWJS_VERSION = "0.117.0"
DEFAULT_DOWNLOAD_ROOT = "https://dl.nwjs.io"

ProgressCallback = Callable[[str], None]

_HTTP_HEADERS = {
    "User-Agent": "RPGMFrame/0.0.1 (+https://github.com/AZumD/RPGMFrame)",
    "Accept": "*/*",
}


class RuntimeError(RuntimeError):
    """Raised when an NW.js runtime cannot be resolved safely."""


def _normalize_version(version: str) -> str:
    value = version.strip()
    if value.startswith("v"):
        value = value[1:]
    if not value or any(ch not in "0123456789." for ch in value):
        raise RuntimeError(f"Invalid NW.js version: {version!r}")
    return value


def _archive_name(version: str) -> str:
    return f"nwjs-v{version}-linux-arm64.tar.gz"


def _runtime_dir_name(version: str) -> str:
    return f"nwjs-v{version}-linux-arm64"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _expected_sha256(shasums: str, filename: str) -> str:
    for raw_line in shasums.splitlines():
        parts = raw_line.strip().split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == filename:
            digest = parts[0].lower()
            if len(digest) == 64 and all(c in "0123456789abcdef" for c in digest):
                return digest
    raise RuntimeError(f"Official SHASUMS256.txt has no entry for {filename}")


def _inside(root: Path, candidate: Path) -> bool:
    return candidate == root or root in candidate.parents


def _safe_extract(archive: Path, destination: Path) -> None:
    """Extract a tarball while rejecting path and link traversal."""
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()

    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            target = (destination / member.name).resolve()
            if not _inside(root, target):
                raise RuntimeError(
                    f"Refusing unsafe path in NW.js archive: {member.name}"
                )

            if member.issym():
                link_target = (target.parent / member.linkname).resolve()
                if not _inside(root, link_target):
                    raise RuntimeError(
                        f"Refusing unsafe symlink in NW.js archive: "
                        f"{member.name} -> {member.linkname}"
                    )
            elif member.islnk():
                link_target = (destination / member.linkname).resolve()
                if not _inside(root, link_target):
                    raise RuntimeError(
                        f"Refusing unsafe hardlink in NW.js archive: "
                        f"{member.name} -> {member.linkname}"
                    )

        tar.extractall(destination)


def _request(url: str) -> urllib.request.Request:
    # dl.nwjs.io may reject Python urllib's default User-Agent at the edge.
    # Send an explicit project identity for both checksum and archive requests.
    return urllib.request.Request(url, headers=_HTTP_HEADERS)


def _transfer_failure(url: str, exc: BaseException) -> str:
    if isinstance(exc, (TimeoutError, ssl.SSLError)):
        return failure_message(url, exc)
    if isinstance(exc, http.client.HTTPException):
        return "Interrupted HTTPS transfer; retry when connectivity is restored"
    return str(exc)


def _download(url: str, destination: Path) -> None:
    partial = destination.with_name(destination.name + ".partial")
    try:
        with open_url(_request(url), timeout=60) as response:
            length = response.headers.get("Content-Length")
            expected = int(length) if length and length.isdigit() else None
            received = 0
            with partial.open("wb") as handle:
                while chunk := response.read(1024 * 1024):
                    handle.write(chunk)
                    received += len(chunk)
            if expected is not None and received != expected:
                raise RuntimeError("Interrupted NW.js archive transfer: incomplete Content-Length")
        partial.replace(destination)
    except (OSError, urllib.error.URLError, http.client.HTTPException) as exc:
        raise RuntimeError(f"Failed to download {url}: {_transfer_failure(url, exc)}") from exc
    finally:
        partial.unlink(missing_ok=True)


def _download_text(url: str, *, status_callback=None) -> str:
    try:
        with open_url(_request(url), timeout=30) as response:
            if status_callback is not None:
                status_callback(response.status)
            data = response.read()
    except (OSError, urllib.error.URLError, http.client.HTTPException) as exc:
        raise RuntimeError(f"Failed to download {url}: {_transfer_failure(url, exc)}") from exc

    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"Could not decode checksum file from {url}") from exc


class RuntimeManager:
    """Resolve verified official NW.js Linux ARM64 runtimes."""

    def __init__(
        self,
        cache_dir: Path | str | None = None,
        *,
        download_root: str = DEFAULT_DOWNLOAD_ROOT,
    ) -> None:
        configured = os.environ.get("RPGMFRAME_CACHE_DIR")
        if cache_dir is not None:
            root = Path(cache_dir)
        elif configured:
            root = Path(configured)
        else:
            root = Path.home() / ".cache" / "rpgmframe"

        self.cache_dir = root.expanduser().resolve() / "runtimes" / "nwjs"
        self.download_root = download_root.rstrip("/")

    def runtime_path(self, version: str = DEFAULT_NWJS_VERSION) -> Path:
        normalized = _normalize_version(version)
        return self.cache_dir / f"v{normalized}" / _runtime_dir_name(normalized)

    def _validate_cached(self, path: Path) -> bool:
        nw = path / "nw"
        return (nw.is_file() and read_elf_architecture(nw) == "aarch64"
                and all((path / name).is_file() and (path / name).stat().st_size > 0
                        for name in ("icudtl.dat", "resources.pak")))

    def ensure_nwjs(
        self,
        version: str = DEFAULT_NWJS_VERSION,
        *,
        progress: ProgressCallback | None = None,
    ) -> Path:
        """Return a cached runtime, downloading and verifying it when absent."""
        normalized = _normalize_version(version)
        final = self.runtime_path(normalized)

        if self._validate_cached(final):
            if progress:
                progress(f"Using cached NW.js {normalized}: {final}")
            return final

        version_dir = self.cache_dir / f"v{normalized}"
        version_dir.mkdir(parents=True, exist_ok=True)

        filename = _archive_name(normalized)
        base_url = f"{self.download_root}/v{normalized}"
        sums_url = f"{base_url}/SHASUMS256.txt"
        archive_url = f"{base_url}/{filename}"

        if progress:
            progress(f"NW.js {normalized} ARM64 is not cached; downloading official runtime")

        with tempfile.TemporaryDirectory(
            prefix=".download-",
            dir=version_dir,
        ) as temporary:
            temp_root = Path(temporary)
            archive = temp_root / filename

            shasums = _download_text(sums_url)
            expected = _expected_sha256(shasums, filename)
            _download(archive_url, archive)

            actual = _sha256(archive)
            if actual != expected:
                raise RuntimeError(
                    f"SHA256 mismatch for {filename}: expected {expected}, got {actual}"
                )

            if progress:
                progress(f"Verified SHA256 for {filename}")

            extracted = temp_root / "extracted"
            try:
                _safe_extract(archive, extracted)
            except (tarfile.TarError, OSError, EOFError) as exc:
                raise RuntimeError("Verified NW.js archive is invalid or incomplete") from exc

            candidate = extracted / _runtime_dir_name(normalized)
            if not candidate.is_dir():
                raise RuntimeError(
                    f"NW.js archive did not contain expected directory: "
                    f"{_runtime_dir_name(normalized)}"
                )

            nw = candidate / "nw"
            architecture = read_elf_architecture(nw)
            if architecture != "aarch64":
                raise RuntimeError(
                    f"Downloaded NW.js runtime is {architecture or 'not ELF'}, "
                    "expected aarch64"
                )
            if not self._validate_cached(candidate):
                raise RuntimeError("NW.js archive is incomplete: missing required runtime resources")

            backup = temp_root / "previous"
            if final.exists():
                final.rename(backup)
            try:
                candidate.rename(final)
            except OSError:
                if backup.exists() and not final.exists():
                    backup.rename(final)
                raise

        if progress:
            progress(f"Cached NW.js {normalized}: {final}")
        return final

    def list_cached(self) -> list[Path]:
        """Return cached, valid ARM64 NW.js runtime directories."""
        if not self.cache_dir.is_dir():
            return []

        found: list[Path] = []
        for version_dir in sorted(self.cache_dir.iterdir()):
            if not version_dir.is_dir():
                continue
            for candidate in version_dir.iterdir():
                if candidate.is_dir() and self._validate_cached(candidate):
                    found.append(candidate)
        return found
