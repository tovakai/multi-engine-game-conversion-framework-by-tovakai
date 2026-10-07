"""Human-readable and JSON inspection / build reports."""

from __future__ import annotations

import json
from typing import Any

from renframe.models import BuildResult, Compatibility, GameInspection, Ownership


def format_human_report(inspection: GameInspection) -> str:
    """Render a compatibility scan as plain text."""
    lines: list[str] = []
    lines.append("RenFrame compatibility scan")
    lines.append("")
    lines.append(f"Game: {inspection.game_name or 'Unknown'}")
    lines.append(
        f"Ren'Py installation detected: {'yes' if inspection.is_renpy else 'no'}"
    )
    lines.append(
        f"Detected Ren'Py version: {inspection.renpy_version or 'unknown'}"
    )
    if inspection.generation is not None:
        lines.append(f"Detected Ren'Py generation: {inspection.generation}.x")
    if inspection.version_source:
        lines.append(f"Version source: {inspection.version_source}")

    arch = ", ".join(inspection.detected_architectures) or "unknown"
    lines.append(f"Detected architecture: {arch}")
    lines.append(
        f"Game directory: {'./game' if inspection.has_game_dir else 'not found'}"
    )
    lines.append("")

    lines.append("Native libraries:")
    game_libs = [
        d
        for d in inspection.native_dependencies
        if d.kind in {"shared_library", "python_extension"}
        and d.ownership == Ownership.GAME
    ]
    if not game_libs:
        lines.append("  none found")
    else:
        for dep in game_libs:
            arch_s = dep.architecture or "unknown"
            lines.append(f"  {arch_s}: {dep.path}")

    lines.append("")
    lines.append("Windows executables:")
    if not inspection.windows_executables:
        lines.append("  none found")
    else:
        for item in inspection.windows_executables:
            lines.append(f"  {item}")

    lines.append("")
    lines.append("Potential issues:")
    issues = inspection.potential_issues or ["none"]
    for issue in issues:
        lines.append(f"  {issue}")

    if inspection.warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in inspection.warnings:
            lines.append(f"  {warning}")

    lines.append("")
    lines.append("Verdict:")
    lines.append(f"  {_verdict_blurb(inspection.compatibility)}")
    lines.append(f"  ({inspection.compatibility.value})")
    return "\n".join(lines) + "\n"


def _verdict_blurb(compatibility: Compatibility) -> str:
    return {
        Compatibility.LIKELY_COMPATIBLE: (
            "likely compatible with ARM runtime replacement"
        ),
        Compatibility.NEEDS_TESTING: (
            "possibly compatible, but needs testing on ARM64"
        ),
        Compatibility.INCOMPATIBLE_NATIVE_CODE: (
            "game-specific native code appears incompatible with ARM64 replacement"
        ),
        Compatibility.UNKNOWN_RENPY_VERSION: (
            "Ren'Py game detected, but version/generation could not be determined"
        ),
        Compatibility.NOT_A_RENPY_GAME: (
            "not recognized as a Ren'Py game"
        ),
    }.get(compatibility, compatibility.value)


def format_json_report(inspection: GameInspection) -> str:
    """Serialize inspection result as indented JSON."""
    payload: dict[str, Any] = inspection.to_dict()
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def format_build_report(result: BuildResult) -> str:
    """Render a successful build (or dry-run) as plain text."""
    lines: list[str] = []
    if result.dry_run:
        lines.append("RenFrame build dry-run")
    else:
        lines.append("RenFrame build complete")
    lines.append("")
    lines.append(f"Game: {result.display_name or result.game_name or 'Unknown'}")
    lines.append(f"Source: {result.source_path}")
    runtime_label_parts: list[str] = []
    if result.runtime_version:
        runtime_label_parts.append(f"Ren'Py {result.runtime_version}")
    else:
        runtime_label_parts.append("Ren'Py (version unknown)")
    if result.runtime_architecture:
        arch = result.runtime_architecture
        if arch == "aarch64":
            arch = "ARM64"
        runtime_label_parts.append(arch.upper() if arch == "arm" else arch)
    lines.append(f"Runtime: {' '.join(runtime_label_parts)}")
    if result.runtime_path:
        lines.append(f"Runtime path: {result.runtime_path}")
    lines.append(f"Output: {result.output_path}")
    lines.append("")
    lines.append("Launcher:")
    if result.launcher_path:
        lines.append(f"  {result.launcher_path}")
    else:
        lines.append("  (none)")
    if result.warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in result.warnings:
            lines.append(f"  {warning}")
    if not result.dry_run and result.launcher_path:
        lines.append("")
        lines.append("Run:")
        lines.append(f"  ./{result.launcher_path.name}")
    elif result.dry_run:
        lines.append("")
        lines.append("Dry-run: no files were copied.")
    return "\n".join(lines) + "\n"


def format_build_json(result: BuildResult) -> str:
    """Serialize a build result as indented JSON."""
    return json.dumps(result.to_dict(), indent=2, sort_keys=False) + "\n"
