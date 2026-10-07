"""Stable models exposed by the unified application layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Backend(str, Enum):
    RENPY = "renpy"
    RPGMFRAME = "rpgmframe"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class UnifiedInspection:
    source_path: Path
    recognized: bool
    backend: Backend
    family: str
    engine: str
    engine_version: str | None = None
    runtime: str | None = None
    game_name: str | None = None
    confidence: str = "low"
    compatibility: str = "unknown"
    evidence: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def buildable(self) -> bool:
        if not self.recognized or self.backend in {Backend.UNKNOWN, Backend.AMBIGUOUS}:
            return False
        if self.backend is Backend.RENPY:
            return self.compatibility not in {
                "incompatible_native_code",
                "not_a_renpy_game",
            }
        return self.compatibility in {"supported", "needs_testing"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "recognized": self.recognized,
            "backend": self.backend.value,
            "family": self.family,
            "engine": self.engine,
            "engine_version": self.engine_version,
            "runtime": self.runtime,
            "game_name": self.game_name,
            "confidence": self.confidence,
            "compatibility": self.compatibility,
            "buildable": self.buildable,
            "evidence": list(self.evidence),
            "warnings": list(self.warnings),
        }


@dataclass
class UnifiedBuildResult:
    success: bool
    source_path: Path
    backend: Backend
    family: str
    engine: str
    engine_version: str | None
    game_name: str | None
    output_path: Path
    build_directory: Path | None = None
    archive_path: Path | None = None
    launcher_path: Path | None = None
    runtime_path: Path | None = None
    runtime_architecture: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "source_path": str(self.source_path),
            "backend": self.backend.value,
            "family": self.family,
            "engine": self.engine,
            "engine_version": self.engine_version,
            "game_name": self.game_name,
            "output_path": str(self.output_path),
            "build_directory": str(self.build_directory) if self.build_directory else None,
            "archive_path": str(self.archive_path) if self.archive_path else None,
            "launcher_path": str(self.launcher_path) if self.launcher_path else None,
            "runtime_path": str(self.runtime_path) if self.runtime_path else None,
            "runtime_architecture": self.runtime_architecture,
            "warnings": list(self.warnings),
        }
