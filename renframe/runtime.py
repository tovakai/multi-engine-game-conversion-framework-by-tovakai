"""ARM64 Ren'Py runtime inspection, layout detection, and cache stub."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from renframe.detector import (
    collect_version_hints,
    detect_runtime_architectures,
    select_best_version,
)
from renframe.elf import is_elf_file, read_elf_architecture
from renframe.models import RuntimeInspection
from renframe.utils import normalize_path

_X86_ARCHES = frozenset({"x86_64", "x86", "amd64", "i386", "i686"})
_ARM_ARCHES = frozenset({"aarch64", "arm64", "arm"})


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


class RuntimeManager:
    """
    Manage cached ARM64 Ren'Py runtimes.

    Automatic download/install is intentionally not implemented yet. Build
    currently requires an explicit ``--runtime`` path.
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        home = Path.home()
        self.cache_dir = cache_dir or (home / ".cache" / "renframe" / "runtimes")

    def find_runtime(self, version: str | None = None) -> Path | None:
        """Locate a cached runtime directory, optionally matching a version."""
        if not self.cache_dir.is_dir():
            return None
        candidates = sorted(p for p in self.cache_dir.iterdir() if p.is_dir())
        if version:
            version_key = version.lower()
            for path in candidates:
                if version_key in path.name.lower():
                    return path
            return None
        return candidates[0] if candidates else None

    def install_runtime(self, source: Path, *, name: str | None = None) -> Path:
        """Install/copy a user-provided runtime into the cache (not yet implemented)."""
        raise NotImplementedError(
            "Runtime installation is not implemented yet. "
            "Pass --runtime explicitly to `renframe build`."
        )

    def list_cached_runtimes(self) -> list[Path]:
        """List cached runtime directories."""
        if not self.cache_dir.is_dir():
            return []
        return sorted(p for p in self.cache_dir.iterdir() if p.is_dir())
