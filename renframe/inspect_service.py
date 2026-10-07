"""Orchestrate a full game inspection."""

from __future__ import annotations

from pathlib import Path

from renframe.detector import (
    collect_version_hints,
    detect_game_name,
    detect_layout_flags,
    detect_runtime_architectures,
    looks_like_renpy_game,
    select_best_version,
)
from renframe.models import GameInspection, Ownership
from renframe.scanner import classify_compatibility, scan_native_dependencies
from renframe.utils import normalize_path


def inspect_game(path: Path | str) -> GameInspection:
    """Inspect a directory and return a structured compatibility report."""
    source = normalize_path(path)
    warnings: list[str] = []

    if not source.exists():
        return GameInspection(
            source_path=source,
            is_renpy=False,
            game_name=source.name or None,
            warnings=[f"Path does not exist: {source}"],
            potential_issues=[f"Path does not exist: {source}"],
        )

    if not source.is_dir():
        return GameInspection(
            source_path=source,
            is_renpy=False,
            game_name=source.name or None,
            warnings=[f"Path is not a directory: {source}"],
            potential_issues=[f"Path is not a directory: {source}"],
        )

    is_renpy = looks_like_renpy_game(source)
    layout = detect_layout_flags(source)
    arches = detect_runtime_architectures(source)
    hints = collect_version_hints(source) if is_renpy else []
    best = select_best_version(hints) if hints else None

    natives = scan_native_dependencies(source) if is_renpy else []
    windows_execs = sorted(
        {
            str(d.path)
            for d in natives
            if d.kind in {"windows_executable", "windows_dll"}
        }
    )

    # Runtime-owned x86 libs are expected and not treated as failures.
    runtime_x86 = [
        d
        for d in natives
        if d.ownership == Ownership.RUNTIME
        and (d.architecture or "").lower() in {"x86_64", "x86"}
    ]
    if runtime_x86 and "x86_64" not in arches and "x86" not in arches:
        arches = sorted(set(arches) | {"x86_64"})

    if is_renpy and not layout["has_renpy_dir"]:
        warnings.append("Missing renpy/ directory; detection relied on game scripts")

    if is_renpy and best and best.generation == 7:
        warnings.append(
            "Ren'Py 7.x games need a matching Python 2 / Ren'Py 7 ARM runtime; "
            "do not assume a Ren'Py 8 ARM SDK will work"
        )

    compatibility, issues = classify_compatibility(
        is_renpy=is_renpy,
        renpy_version=best.version if best else None,
        generation=best.generation if best else None,
        native_dependencies=natives,
        warnings=[],  # keep soft warnings separate from hard issues
    )

    # Attach soft warnings into NEEDS_TESTING only when otherwise likely ok.
    potential_issues = [i for i in issues if i != "none"]
    if compatibility.value == "LIKELY_COMPATIBLE" and warnings:
        from renframe.models import Compatibility as Compat

        compatibility = Compat.NEEDS_TESTING
        potential_issues = list(warnings)

    if not potential_issues:
        potential_issues = ["none"]

    return GameInspection(
        source_path=source,
        is_renpy=is_renpy,
        game_name=detect_game_name(source) if is_renpy else source.name,
        renpy_version=best.version if best else None,
        generation=best.generation if best else None,
        version_source=best.source if best else None,
        detected_architectures=arches,
        has_game_dir=layout["has_game_dir"],
        has_renpy_dir=layout["has_renpy_dir"],
        has_lib_dir=layout["has_lib_dir"],
        native_dependencies=natives,
        windows_executables=windows_execs,
        warnings=warnings,
        potential_issues=potential_issues,
        version_hints=hints,
        compatibility=compatibility,
    )
