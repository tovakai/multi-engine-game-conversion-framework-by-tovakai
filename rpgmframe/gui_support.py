"""Testable support functions used by the RPGMFrame desktop GUI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rpgmframe.builder import build_game
from rpgmframe.models import BuildResult, GameInspection
from rpgmframe.packaging import create_tar_gz
from rpgmframe.runtime import DEFAULT_NWJS_VERSION
from rpgmframe.source import prepare_source


@dataclass(frozen=True)
class InspectionSummary:
    """Stable GUI-facing subset of a game inspection."""

    recognized: bool
    engine: str
    engine_version: str | None
    game_name: str | None
    confidence: str
    compatibility: str
    warnings: tuple[str, ...]
    evidence: tuple[str, ...]

    @classmethod
    def from_inspection(cls, result: GameInspection) -> "InspectionSummary":
        return cls(
            recognized=result.recognized,
            engine=result.engine.value,
            engine_version=result.engine_version,
            game_name=result.game_name,
            confidence=result.confidence.value,
            compatibility=result.compatibility.value,
            warnings=tuple(result.warnings),
            evidence=tuple(result.evidence),
        )


@dataclass(frozen=True)
class GuiBuildOutcome:
    """Completed GUI conversion result."""

    build: BuildResult
    archive_path: Path | None


def source_base_name(source: Path | str) -> str:
    path = Path(source).expanduser()
    if path.suffix.lower() == ".zip":
        return path.stem
    return path.name


def output_path_for_source(source: Path | str, output_dir: Path | str) -> Path:
    return Path(output_dir).expanduser() / f"{source_base_name(source)}-frame"


def inspect_source_summary(source: Path | str) -> InspectionSummary:
    """
    Inspect a directory or ZIP without leaking temporary extraction paths.

    ZIP inspection is useful for the GUI and shares the same safe source
    preparation path as normal builds.
    """
    path = Path(source).expanduser().resolve()
    with prepare_source(path) as prepared:
        from rpgmframe.detector import inspect_game

        return InspectionSummary.from_inspection(inspect_game(prepared.root))


def build_for_gui(
    source: Path | str,
    *,
    output_dir: Path | str,
    runtime_version: str = DEFAULT_NWJS_VERSION,
    force: bool = False,
    archive: bool = True,
    progress=None,
) -> GuiBuildOutcome:
    """Build a Frame-ready directory and optional transfer archive."""
    source_path = Path(source).expanduser().resolve()
    output_path = output_path_for_source(source_path, output_dir).resolve()

    result = build_game(
        source_path,
        runtime_version=runtime_version,
        output=output_path,
        force=force,
        progress=progress,
    )
    archive_path = (
        create_tar_gz(result.output_path, force=force)
        if archive
        else None
    )
    return GuiBuildOutcome(build=result, archive_path=archive_path)


def summary_is_buildable(summary: InspectionSummary) -> bool:
    """Return whether the current backend can convert this inspected game."""
    return (
        summary.recognized
        and summary.engine in {"xp", "vx", "vxace", "mv", "mz", "godot"}
        and summary.compatibility in {"supported", "needs_testing"}
    )
