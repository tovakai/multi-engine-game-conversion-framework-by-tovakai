"""ARM64 Ren'Py runtime inspection plus verified automatic sdkarm acquisition."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from renframe.detector import (
    collect_version_hints,
    detect_runtime_architectures,
    select_best_version,
)
from renframe.elf import is_elf_file, read_elf_architecture
from renframe.models import GameInspection, RuntimeInspection
from renframe.utils import normalize_path

_X86_ARCHES = frozenset({"x86_64", "x86", "amd64", "i386", "i686"})
_ARM_ARCHES = frozenset({"aarch64", "arm64", "arm"})
_RELEASE_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:\.\d+)?$")
_DEFAULT_BASE_URL = "https://www.renpy.org/dl"
_SDK_753_SHA256 = "6e5da3388b083d05f9d43991310776ff394b04bbb5541ee6216484ebd3d5a567"
_SDK_SHA256 = {
    "7.5.0": "33e1fcab5a9c80c0850a245e0ce634c098dcea27d8f58a523c80014ed27b94d0",
    "7.5.3": _SDK_753_SHA256,
}


class RuntimeDownloadError(RuntimeError):
    """Raised when an official Ren'Py ARM64 runtime cannot be acquired safely."""


def normalize_release_version(version: str) -> str:
    """Normalize Ren'Py release/build strings to the public x.y.z release."""
    match = _RELEASE_VERSION_RE.match(version.strip())
    if not match:
        raise RuntimeDownloadError(
            f"Ren'Py version must be an exact release such as 8.5.3; got {version!r}"
        )
    return ".".join(match.groups())



def requires_pre_sdkarm_override(version: str | None, generation: int | None) -> bool:
    """Whether the official matching ARM64 runtime predates Ren'Py 7.5."""
    if generation is not None and generation < 7:
        return True
    if generation != 7 or not version:
        return False
    try:
        major, minor, _patch = map(int, normalize_release_version(version).split("."))
    except RuntimeDownloadError:
        return False
    return major == 7 and minor < 5


def experimental_arm64_fallback(version: str | None, generation: int | None,
                                *, inspection: GameInspection | None = None) -> str | None:
    """Offer Python 2 fallback for 7.4.x and authoritative exact 7.3.5.

    Ren'Py 7.5.0 is the first official sdkarm release. This is an opt-in,
    cross-minor experiment, not evidence that every 7.4 game will run.
    Never infer a Python generation from the version alone.
    """
    if generation != 7 or not version:
        return None
    try:
        release = normalize_release_version(version)
    except RuntimeDownloadError:
        return None
    if release.startswith("7.4."):
        return "7.5.0"
    if release != "7.3.5" or inspection is None:
        return None
    root = inspection.source_path
    hints = [h for h in inspection.version_hints
             if h.version and h.source in {"renpy/__init__.py", "renpy/vc_version.py", "renpy/versions.py"}]
    if (not inspection.is_renpy or inspection.renpy_version != release
            or inspection.generation != 7 or not hints
            or not any(h.confidence == "high" and h.generation == 7 for h in hints)
            or any(h.version != release or h.generation != 7 for h in hints)
            or not (root / "game").is_dir()
            or not (root / "renpy/__init__.py").is_file()):
        return None
    # A renamed/fake engine directory, or a Python 3 distribution with a
    # stale version marker, must not enable the new migration.
    lib = root / "lib"
    if not lib.is_dir():
        return None
    names = [p.name.casefold() for p in lib.iterdir() if p.is_dir()]
    if (not any(n.startswith(("py2-", "python2.", "pythonlib2.")) for n in names)
            or any(n.startswith(("py3-", "python3.", "pythonlib3.")) for n in names)):
        return None
    return "7.5.0"


def python_tag_for_generation(generation: int | None) -> str:
    if generation == 8:
        return "py3"
    if generation == 7:
        return "py2"
    raise RuntimeDownloadError(
        "Automatic Linux ARM64 runtime acquisition currently supports "
        "Ren'Py 7.x (Python 2) and 8.x (Python 3) releases."
    )


@dataclass
class RuntimeLayout:
    """
    Detected layout of a Ren'Py runtime / SDK tree.

    Paths are absolute. Relative launcher invocation should be derived from
    ``root`` so generated scripts stay portable.
    """

    root: Path
    game_dir: Path
    launcher: Path | None
    renpy_py: Path | None
    python_bin: Path | None
    arm_lib_dir: Path | None

    @property
    def launcher_relative(self) -> str | None:
        if self.launcher is None:
            return None
        return self.launcher.relative_to(self.root).as_posix()

    @property
    def renpy_py_relative(self) -> str | None:
        if self.renpy_py is None:
            return None
        return self.renpy_py.relative_to(self.root).as_posix()

    @property
    def python_bin_relative(self) -> str | None:
        if self.python_bin is None:
            return None
        return self.python_bin.relative_to(self.root).as_posix()


def looks_like_renpy_runtime(path: Path) -> bool:
    """
    Return True if the directory looks like a Ren'Py SDK or distributed runtime.
    """
    if not path.is_dir():
        return False
    renpy_dir = path / "renpy"
    has_renpy = renpy_dir.is_dir() and (renpy_dir / "__init__.py").is_file()
    if not has_renpy:
        return False
    has_launcher = (path / "renpy.sh").is_file() or (path / "renpy.py").is_file()
    has_lib = (path / "lib").is_dir()
    return has_launcher or has_lib


def _elf_arches_under_lib(lib: Path, *, limit: int = 40) -> set[str]:
    """Sample ELF architectures under lib/ without a full tree walk explosion."""
    found: set[str] = set()
    if not lib.is_dir():
        return found
    checked = 0
    for path in lib.rglob("*"):
        if checked >= limit:
            break
        if not path.is_file():
            continue
        name = path.name.lower()
        if not (
            name == "python"
            or name == "python3"
            or name.endswith(".so")
            or ".so." in name
            or name.startswith("librenpy")
        ):
            continue
        checked += 1
        if not is_elf_file(path):
            continue
        arch = read_elf_architecture(path)
        if arch:
            found.add(arch)
    return found


def _normalize_arch_label(arches: set[str]) -> str | None:
    """Pick a primary architecture label from a set of detected arches."""
    lowered = {a.lower() for a in arches}
    if "aarch64" in lowered or "arm64" in lowered:
        return "aarch64"
    if "arm" in lowered:
        return "arm"
    if "x86_64" in lowered or "amd64" in lowered:
        return "x86_64"
    if "x86" in lowered or "i386" in lowered or "i686" in lowered:
        return "x86"
    if len(arches) == 1:
        return next(iter(arches))
    return None


def inspect_runtime(path: Path | str) -> RuntimeInspection:
    """
    Inspect a user-supplied Ren'Py runtime / SDK directory.

    Reuses game version strategies and ELF parsing; does not download anything.
    """
    root = normalize_path(path)
    warnings: list[str] = []

    if not root.exists():
        return RuntimeInspection(
            path=root,
            is_renpy_runtime=False,
            warnings=[f"Runtime path does not exist: {root}"],
        )
    if not root.is_dir():
        return RuntimeInspection(
            path=root,
            is_renpy_runtime=False,
            warnings=[f"Runtime path is not a directory: {root}"],
        )

    is_runtime = looks_like_renpy_runtime(root)
    has_renpy_sh = (root / "renpy.sh").is_file()
    has_renpy_py = (root / "renpy.py").is_file()

    lib_name_arches = set(detect_runtime_architectures(root))
    elf_arches = _elf_arches_under_lib(root / "lib")
    all_arches = lib_name_arches | elf_arches
    architecture = _normalize_arch_label(all_arches)

    hints = collect_version_hints(root) if is_runtime else []
    best = select_best_version(hints) if hints else None

    if is_runtime and architecture is None:
        warnings.append(
            "Could not determine runtime CPU architecture from lib/ names or ELF "
            "headers; layout may be unusual"
        )
    if is_runtime and not has_renpy_sh and not has_renpy_py:
        warnings.append("Runtime has no renpy.sh or renpy.py launcher entrypoint")

    return RuntimeInspection(
        path=root,
        is_renpy_runtime=is_runtime,
        architecture=architecture,
        version=best.version if best else None,
        generation=best.generation if best else None,
        warnings=warnings,
        has_renpy_sh=has_renpy_sh,
        has_renpy_py=has_renpy_py,
        lib_architectures=sorted(all_arches),
    )


def detect_runtime_layout(path: Path | str) -> RuntimeLayout:
    """
    Derive launch paths from a runtime tree.

    Prefers ``renpy.sh`` when present; otherwise falls back to
    ``python`` + ``renpy.py`` under an ARM lib directory.
    """
    root = normalize_path(path)
    game_dir = root / "game"
    launcher = root / "renpy.sh" if (root / "renpy.sh").is_file() else None
    renpy_py = root / "renpy.py" if (root / "renpy.py").is_file() else None

    arm_lib_dir: Path | None = None
    python_bin: Path | None = None
    lib = root / "lib"
    if lib.is_dir():
        candidates: list[Path] = []
        for child in sorted(lib.iterdir()):
            if not child.is_dir():
                continue
            lower = child.name.lower()
            if any(token in lower for token in ("aarch64", "arm64")):
                candidates.append(child)
        if candidates:
            arm_lib_dir = candidates[0]
            for name in ("python", "python3"):
                candidate = arm_lib_dir / name
                if candidate.is_file():
                    python_bin = candidate
                    break

    return RuntimeLayout(
        root=root,
        game_dir=game_dir,
        launcher=launcher,
        renpy_py=renpy_py,
        python_bin=python_bin,
        arm_lib_dir=arm_lib_dir,
    )


def runtime_architecture_is_clearly_x86(inspection: RuntimeInspection) -> bool:
    """True when detected arches are x86-only (no ARM signal)."""
    arches = {a.lower() for a in inspection.lib_architectures}
    if inspection.architecture:
        arches.add(inspection.architecture.lower())
    if not arches:
        return False
    has_arm = bool(arches & _ARM_ARCHES) or "aarch64" in arches
    has_x86 = bool(arches & _X86_ARCHES)
    return has_x86 and not has_arm


def _default_cache_dir() -> Path:
    override = os.environ.get("MEGCFBT_CACHE_DIR")
    if override:
        return Path(override).expanduser() / "runtimes" / "renpy"
    legacy = os.environ.get("RENFRAME_CACHE_DIR")
    if legacy:
        return Path(legacy).expanduser()
    return (
        Path.home()
        / ".cache"
        / "multi-engine-game-conversion-framework-by-tovakai"
        / "runtimes"
        / "renpy"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_sha256(checksums: str, filename: str) -> str:
    section: str | None = None
    for raw in checksums.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.lower().startswith("# sha256"):
            section = "sha256"
            continue
        if line.startswith("#"):
            section = line[1:].strip().lower()
            continue
        if section != "sha256":
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == filename:
            digest = parts[0].lower()
            if re.fullmatch(r"[0-9a-f]{64}", digest):
                return digest
    raise RuntimeDownloadError(
        f"Official checksums.txt does not contain a SHA256 for {filename}"
    )


def _safe_tar_members(
    archive: tarfile.TarFile,
    platform_name: str,
) -> list[tarfile.TarInfo]:
    members: list[tarfile.TarInfo] = []
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise RuntimeDownloadError(
                f"Refusing unsafe path in official Ren'Py archive: {member.name}"
            )
        parts = path.parts
        matched = any(
            parts[i] == "lib" and parts[i + 1] == platform_name
            for i in range(max(0, len(parts) - 1))
        )
        if not matched:
            continue
        if member.issym() or member.islnk():
            target = PurePosixPath(member.linkname)
            if target.is_absolute() or ".." in target.parts:
                raise RuntimeDownloadError(
                    f"Refusing unsafe link in official Ren'Py archive: "
                    f"{member.name} -> {member.linkname}"
                )
        members.append(member)
    return members



def _safe_full_sdk_members(
    archive: tarfile.TarFile,
    release: str,
    python_tag: str,
) -> tuple[list[tarfile.TarInfo], str]:
    """Select a complete matching Ren'Py engine and Python 2 ARM64 runtime.

    Archive contents are never extracted wholesale; SDK examples, other CPU
    architectures, and unrelated editor files are intentionally excluded.
    """
    selected: list[tarfile.TarInfo] = []
    prefixes: set[str] = set()
    platform = f"{python_tag}-linux-aarch64"
    seen: set[str] = set()
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or "\\" in member.name or ":" in member.name:
            raise RuntimeDownloadError(
                f"Refusing unsafe path in official Ren'Py archive: {member.name}"
            )
        parts = path.parts
        if len(parts) < 2 or parts[0] not in {f"renpy-{release}-sdk", f"renpy-{release}-sdkarm"}:
            continue
        relative = parts[1:]
        wanted = (
            relative[0] == "renpy"
            or relative == ("renpy.py",)
            or relative == ("renpy.sh",)
            or relative == ("LICENSE.txt",)
            or relative == ("doc", "license.html")
            or (len(relative) >= 2 and relative[:2] == ("lib", platform))
            or (len(relative) >= 2 and relative[:2] == ("lib", "python2.7"))
            or relative in {("lib", "python2.7.zip"), ("lib", "python27.zip")}
        )
        if not wanted:
            continue
        canonical = path.as_posix().casefold()
        if canonical in seen:
            raise RuntimeDownloadError(f"Duplicate/colliding SDK path: {member.name}")
        seen.add(canonical)
        if member.issym() or member.islnk():
            link = PurePosixPath(member.linkname)
            if link.is_absolute() or ".." in link.parts or "\\" in member.linkname or ":" in member.linkname:
                raise RuntimeDownloadError(
                    f"Refusing unsafe link in official Ren'Py archive: "
                    f"{member.name} -> {member.linkname}"
                )
        prefixes.add(parts[0])
        selected.append(member)
    if len(prefixes) != 1:
        raise RuntimeDownloadError(
            f"Expected one Ren'Py {release} SDK root, found {sorted(prefixes)}"
        )
    selected_names = {member.name for member in selected}
    for member in selected:
        if member.issym() or member.islnk():
            target = (PurePosixPath(member.name).parent / member.linkname).as_posix() if member.issym() else member.linkname
            if target not in selected_names:
                raise RuntimeDownloadError(f"SDK link target is outside selected runtime: {member.name}")
    return selected, next(iter(prefixes))


def _sdk_manifest(path: Path) -> dict[str, str]:
    manifest = {}
    for p in sorted(path.rglob("*")):
        if p.is_symlink() or getattr(p, "is_junction", lambda: False)():
            raise RuntimeDownloadError("Verified SDK cache cannot contain links/junctions")
        relative = p.relative_to(path).as_posix()
        if p.is_file() and relative != ".verified-sdk.json":
            manifest[relative] = _sha256(p)
    return manifest


def _validate_matched_py2_sdk(path: Path, release: str) -> None:
    _validate_full_sdk(path, "py2-linux-aarch64")
    inspection = inspect_runtime(path)
    if inspection.version != release or inspection.generation != 7:
        raise RuntimeDownloadError(f"Official SDK engine must identify as Ren'Py {release} Python 2")
    if not (path / "lib/python2.7").is_dir() or not any((path / "lib/python2.7").rglob("*.py*")):
        raise RuntimeDownloadError("Official SDK is missing the Python 2.7 standard library")
    if not (path / "LICENSE.txt").is_file():
        raise RuntimeDownloadError("Official SDK is missing its license notices")


def _validate_full_sdk(path: Path, platform: str) -> None:
    if not (path / "renpy" / "__init__.py").is_file():
        raise RuntimeDownloadError("Official Ren'Py SDK is missing its Python engine")
    if not (path / "renpy.py").is_file():
        raise RuntimeDownloadError("Official Ren'Py SDK is missing renpy.py")
    if not (path / "renpy.sh").is_file():
        raise RuntimeDownloadError("Official Ren'Py SDK is missing renpy.sh")
    _validate_platform_dir(path / "lib" / platform)


def _extract_selected_members(
    archive: tarfile.TarFile,
    members: list[tarfile.TarInfo],
    destination: Path,
) -> None:
    """Extract selected tar members without requiring symlink privileges."""
    root = destination.resolve()
    for member in members:
        relative = PurePosixPath(member.name)
        target = destination.joinpath(*relative.parts)
        resolved = target.resolve()
        if resolved != root and root not in resolved.parents:
            raise RuntimeDownloadError(
                f"Refusing unsafe path in official Ren'Py archive: {member.name}"
            )

        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
            continue

        if not (member.isfile() or member.issym() or member.islnk()):
            raise RuntimeDownloadError(
                f"Refusing special file in official Ren'Py archive: {member.name}"
            )

        source = archive.extractfile(member)
        if source is None:
            raise RuntimeDownloadError(
                f"Could not read file from official Ren'Py archive: {member.name}"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        with source, target.open("wb") as output:
            shutil.copyfileobj(source, output)
        try:
            target.chmod(member.mode)
        except OSError:
            pass


def _validate_platform_dir(path: Path) -> None:
    if not path.is_dir():
        raise RuntimeDownloadError(f"Extracted Ren'Py platform is missing: {path}")

    candidates = [path / "renpy", path / "python", path / "python3"]
    architectures = {
        read_elf_architecture(candidate)
        for candidate in candidates
        if candidate.is_file()
    }
    architectures.discard(None)
    if "aarch64" not in architectures:
        raise RuntimeDownloadError(
            "Downloaded Ren'Py sdkarm platform did not contain a readable "
            f"AArch64 launcher/runtime in {path}"
        )


class RuntimeManager:
    """Download, verify, extract, and cache official Ren'Py sdkarm slices."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        *,
        base_url: str = _DEFAULT_BASE_URL,
    ) -> None:
        self.cache_dir = (cache_dir or _default_cache_dir()).expanduser()
        self.base_url = base_url.rstrip("/")

    def platform_path(self, version: str, python_tag: str) -> Path:
        release = normalize_release_version(version)
        return self.cache_dir / release / f"{python_tag}-linux-aarch64"

    def full_sdk_path(self, version: str, python_tag: str) -> Path:
        release = normalize_release_version(version)
        return self.cache_dir / release / f"{python_tag}-arm64-compat-sdk"

    def ensure_full_sdk(
        self,
        version: str,
        python_tag: str,
        *,
        progress: Callable[[str], None] | None = None,
    ) -> Path:
        """Cache matched Python 2 engines for the explicit 7.5.0/7.5.3 migrations.

        Official runtime archive and checksum come from renpy.org. Only the
        selected engine, entrypoint, Python 2 support, and ARM64 platform are
        extracted. Builds use this SDK as a complete replacement engine.
        """
        release = normalize_release_version(version)
        if release not in {"7.5.0", "7.5.3"} or python_tag != "py2":
            raise RuntimeDownloadError(
                "Full engine fallback is only available for Ren'Py 7.5.0 or 7.5.3 Python 2."
            )
        destination = self.full_sdk_path(release, python_tag)
        try:
            _validate_full_sdk(destination, "py2-linux-aarch64")
            if release in {"7.5.0", "7.5.3"}:
                _validate_matched_py2_sdk(destination, release)
                try:
                    manifest = json.loads((destination / ".verified-sdk.json").read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    raise RuntimeDownloadError("Missing verified SDK cache manifest") from exc
                if not isinstance(manifest, dict) or manifest.get("files") != _sdk_manifest(destination):
                    raise RuntimeDownloadError("SDK cache content changed since checksum verification")
                if self.base_url == _DEFAULT_BASE_URL and manifest.get("archive_sha256") != _SDK_SHA256[release]:
                    raise RuntimeDownloadError("SDK cache provenance does not match the official archive")
            if progress:
                progress(f"Using cached complete Ren'Py {release} Python 2 ARM64 engine")
            return destination
        except (RuntimeDownloadError, OSError):
            pass

        filename = f"renpy-{release}-sdkarm.tar.bz2"
        url = f"{self.base_url}/{release}"
        if progress:
            progress(f"Resolving official Ren'Py {release} full ARM64 SDK")
        expected = _parse_sha256(
            self._read_url(f"{url}/checksums.txt"), filename
        )
        if self.base_url == _DEFAULT_BASE_URL and expected != _SDK_SHA256[release]:
            raise RuntimeDownloadError(f"Official {release} checksum differs from independently verified SHA256")
        archive_path = self.cache_dir / "downloads" / filename
        if not archive_path.is_file() or _sha256(archive_path) != expected:
            self._download(f"{url}/{filename}", archive_path, progress=progress)
        if _sha256(archive_path) != expected:
            archive_path.unlink(missing_ok=True)
            raise RuntimeDownloadError(
                f"SHA256 verification failed for official {filename}"
            )
        if progress:
            progress(f"Ren'Py {release} full SDK checksum verified")

        release_root = destination.parent
        release_root.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".sdk-", dir=str(release_root)))
        try:
            with tarfile.open(archive_path, "r:bz2") as archive:
                members, prefix = _safe_full_sdk_members(archive, release, python_tag)
                if not members:
                    raise RuntimeDownloadError(
                        f"Official {filename} has no selected engine/runtime files"
                    )
                extracted = temporary / "extracted"
                _extract_selected_members(archive, members, extracted)
            staged = extracted / prefix
            _validate_full_sdk(staged, "py2-linux-aarch64")
            if release in {"7.5.0", "7.5.3"}:
                _validate_matched_py2_sdk(staged, release)
                (staged / ".verified-sdk.json").write_text(json.dumps({
                    "archive_sha256": expected, "files": _sdk_manifest(staged),
                }, sort_keys=True), encoding="utf-8")
            if destination.exists():
                backup = temporary / "previous-sdk"
                destination.replace(backup)
                try:
                    staged.replace(destination)
                except OSError:
                    backup.replace(destination)
                    raise
            else:
                staged.replace(destination)
        except (tarfile.TarError, OSError, KeyError, RecursionError) as exc:
            raise RuntimeDownloadError(f"Could not safely extract official {filename}: {exc}") from exc
        finally:
            shutil.rmtree(temporary, ignore_errors=True)

        if progress:
            progress(f"Cached complete Ren'Py {release} engine and Python 2 ARM64 runtime")
        return destination

    def find_platform(self, version: str, python_tag: str) -> Path | None:
        path = self.platform_path(version, python_tag)
        try:
            _validate_platform_dir(path)
        except RuntimeDownloadError:
            return None
        return path

    def _read_url(self, url: str) -> str:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Multi-Engine-Game-Conversion-Framework-by-Tovakai"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read().decode("utf-8", errors="replace")
        except (OSError, urllib.error.URLError) as exc:
            raise RuntimeDownloadError(f"Could not download {url}: {exc}") from exc

    def _download(
        self,
        url: str,
        destination: Path,
        *,
        progress: Callable[[str], None] | None,
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + ".partial")
        partial.unlink(missing_ok=True)

        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Multi-Engine-Game-Conversion-Framework-by-Tovakai"},
        )
        if progress:
            progress(f"Downloading official Ren'Py ARM64 SDK: {url}")
        try:
            with urllib.request.urlopen(request, timeout=60) as response, partial.open(
                "wb"
            ) as output:
                total = 0
                next_report = 16 * 1024 * 1024
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    total += len(chunk)
                    if progress and total >= next_report:
                        progress(f"Downloaded {total // (1024 * 1024)} MiB…")
                        next_report += 16 * 1024 * 1024
        except (OSError, urllib.error.URLError) as exc:
            partial.unlink(missing_ok=True)
            raise RuntimeDownloadError(f"Could not download {url}: {exc}") from exc

        partial.replace(destination)

    def ensure_platform(
        self,
        version: str,
        python_tag: str,
        *,
        progress: Callable[[str], None] | None = None,
        force: bool = False,
    ) -> Path:
        release = normalize_release_version(version)
        if python_tag not in {"py2", "py3"}:
            raise RuntimeDownloadError(f"Unsupported Ren'Py Python tag: {python_tag}")

        major, minor, _patch = (int(part) for part in release.split("."))
        if major < 7 or (major == 7 and minor < 5):
            raise RuntimeDownloadError(
                f"Ren'Py {release} predates official Linux AArch64 support. "
                "Automatic conversion needs an official sdkarm release or a "
                "manually supplied compatible runtime."
            )

        destination = self.platform_path(release, python_tag)
        if not force:
            found = self.find_platform(release, python_tag)
            if found is not None:
                if progress:
                    progress(f"Using cached Ren'Py {release} ARM64 runtime")
                return found

        filename = f"renpy-{release}-sdkarm.tar.bz2"
        release_url = f"{self.base_url}/{release}"
        checksums_url = f"{release_url}/checksums.txt"
        archive_url = f"{release_url}/{filename}"

        if progress:
            progress(f"Resolving official Ren'Py {release} sdkarm runtime")
        checksums = self._read_url(checksums_url)
        expected = _parse_sha256(checksums, filename)

        downloads = self.cache_dir / "downloads"
        archive_path = downloads / filename
        if force or not archive_path.is_file() or _sha256(archive_path) != expected:
            self._download(archive_url, archive_path, progress=progress)

        actual = _sha256(archive_path)
        if actual != expected:
            archive_path.unlink(missing_ok=True)
            raise RuntimeDownloadError(
                f"SHA256 mismatch for {filename}: expected {expected}, got {actual}"
            )
        if progress:
            progress("Ren'Py sdkarm checksum OK")

        version_root = self.cache_dir / release
        version_root.mkdir(parents=True, exist_ok=True)
        temporary_parent = Path(
            tempfile.mkdtemp(prefix=f".{release}-", dir=str(version_root))
        )
        extracted_root = temporary_parent / "extract"
        extracted_root.mkdir()

        try:
            with tarfile.open(archive_path, "r:bz2") as archive:
                members = _safe_tar_members(archive, destination.name)
                if not members:
                    raise RuntimeDownloadError(
                        f"Ren'Py {release} sdkarm does not contain "
                        f"lib/{destination.name}"
                    )
                _extract_selected_members(archive, members, extracted_root)

            found = [
                path
                for path in extracted_root.rglob(destination.name)
                if path.is_dir()
            ]
            if len(found) != 1:
                raise RuntimeDownloadError(
                    f"Expected exactly one {destination.name} directory in "
                    f"Ren'Py {release} sdkarm, found {len(found)}"
                )

            staged = temporary_parent / destination.name
            shutil.copytree(found[0], staged, symlinks=True)
            _validate_platform_dir(staged)

            if destination.exists():
                shutil.rmtree(destination)
            staged.replace(destination)
        finally:
            shutil.rmtree(temporary_parent, ignore_errors=True)

        if progress:
            progress(
                f"Cached Ren'Py {release} {destination.name} runtime at {destination}"
            )
        return destination

    def find_runtime(self, version: str | None = None) -> Path | None:
        if not self.cache_dir.is_dir():
            return None
        if version is not None:
            root = self.cache_dir / normalize_release_version(version)
            return root if root.is_dir() else None
        versions = sorted(
            path for path in self.cache_dir.iterdir()
            if path.is_dir() and path.name != "downloads"
        )
        return versions[0] if versions else None

    def install_runtime(self, source: Path, *, name: str | None = None) -> Path:
        source = normalize_path(source)
        if not source.is_dir():
            raise RuntimeDownloadError(f"Runtime path is not a directory: {source}")
        inspection = inspect_runtime(source)
        if not inspection.is_renpy_runtime:
            raise RuntimeDownloadError(f"Not a Ren'Py runtime: {source}")
        target = self.cache_dir / (name or source.name)
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target, symlinks=True)
        return target

    def list_cached_runtimes(self) -> list[Path]:
        if not self.cache_dir.is_dir():
            return []
        return sorted(
            path for path in self.cache_dir.iterdir()
            if path.is_dir() and path.name != "downloads"
        )
