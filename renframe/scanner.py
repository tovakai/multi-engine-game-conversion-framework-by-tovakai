"""Native dependency scanning and compatibility classification."""

from __future__ import annotations

from pathlib import Path

from renframe.elf import read_elf_architecture
from renframe.models import Compatibility, NativeDependency, Ownership
from renframe.utils import is_runtime_owned_path

NATIVE_EXTENSIONS = {
    ".so": "shared_library",
    ".dll": "windows_dll",
    ".exe": "windows_executable",
    ".pyd": "python_extension",
}

# Architectures that cannot run natively on Linux ARM64 Steam Frame.
_INCOMPATIBLE_ARCHES = frozenset({"x86_64", "x86", "amd64", "i386", "i686"})


def classify_ownership(root: Path, absolute: Path) -> Ownership:
    """Classify whether a file is stock runtime or game-specific."""
    try:
        relative = absolute.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return Ownership.UNKNOWN
    if is_runtime_owned_path(relative):
        return Ownership.RUNTIME
    if relative.parts and relative.parts[0].lower() == "game":
        return Ownership.GAME
    # Files outside renpy/lib/game are treated as game/distribution extras.
    return Ownership.GAME


def scan_native_dependencies(root: Path) -> list[NativeDependency]:
    """Recursively find native/binary artifacts under the game tree."""
    results: list[NativeDependency] = []
    root = root.resolve(strict=False)

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        # Also catch versioned .so names like foo.so.1
        kind = NATIVE_EXTENSIONS.get(suffix)
        if kind is None and ".so." in path.name.lower():
            kind = "shared_library"
        if kind is None:
            continue

        ownership = classify_ownership(root, path)
        architecture: str | None = None
        notes = ""

        if kind == "shared_library" or suffix == ".so":
            architecture = read_elf_architecture(path)
            if architecture is None:
                notes = "not a valid ELF or unreadable"
        elif kind in {"windows_dll", "windows_executable", "python_extension"}:
            architecture = "windows"
            notes = "Windows PE binary"

        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path

        results.append(
            NativeDependency(
                path=rel,
                kind=kind,
                architecture=architecture,
                ownership=ownership,
                notes=notes,
            )
        )
    return results


def game_owned_native_problems(deps: list[NativeDependency]) -> list[NativeDependency]:
    """Return game-owned natives that look incompatible with Linux aarch64."""
    problems: list[NativeDependency] = []
    for dep in deps:
        if dep.ownership != Ownership.GAME:
            continue
        arch = (dep.architecture or "").lower()
        if dep.kind in {"windows_dll", "windows_executable", "python_extension"}:
            # Windows-only game extensions are a real problem for native Linux ARM.
            if "game" in str(dep.path).replace("\\", "/").lower():
                problems.append(dep)
            continue
        if arch in _INCOMPATIBLE_ARCHES:
            problems.append(dep)
        elif arch and arch not in {"aarch64", "arm"} and arch.startswith("unknown"):
            problems.append(dep)
    return problems


def classify_compatibility(
    *,
    is_renpy: bool,
    renpy_version: str | None,
    generation: int | None,
    native_dependencies: list[NativeDependency],
    warnings: list[str],
) -> tuple[Compatibility, list[str]]:
    """
    Derive a conservative compatibility verdict and human-readable issues.

    Compatibility is never guaranteed; this only flags obvious blockers.
    """
    issues: list[str] = []

    if not is_renpy:
        return Compatibility.NOT_A_RENPY_GAME, ["Directory does not look like a Ren'Py game"]

    problems = game_owned_native_problems(native_dependencies)
    for dep in problems:
        arch = dep.architecture or "unknown"
        issues.append(
            f"{arch} native code detected (game-owned): {dep.path}"
        )

    if problems:
        return Compatibility.INCOMPATIBLE_NATIVE_CODE, issues

    if renpy_version is None and generation is None:
        issues.append("Could not determine Ren'Py version or generation")
        return Compatibility.UNKNOWN_RENPY_VERSION, issues

    if renpy_version is None and generation is not None:
        issues.append(
            f"Ren'Py generation inferred as {generation}.x but exact version unknown"
        )
        return Compatibility.UNKNOWN_RENPY_VERSION, issues

    if generation not in (7, 8):
        issues.append(
            f"Unusual Ren'Py generation ({generation!r}); runtime matching needs care"
        )
        return Compatibility.NEEDS_TESTING, issues

    # Soft signals that deserve testing even without hard native blockers.
    game_natives = [d for d in native_dependencies if d.ownership == Ownership.GAME]
    if game_natives:
        issues.append(
            "Game-owned binary artifacts present but none clearly x86-incompatible; "
            "needs runtime testing"
        )
        return Compatibility.NEEDS_TESTING, issues

    if warnings:
        issues.extend(warnings)
        return Compatibility.NEEDS_TESTING, issues

    if not issues:
        issues.append("none")

    return Compatibility.LIKELY_COMPATIBLE, issues
