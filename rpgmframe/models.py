"""Typed inspection and build models shared by RPGMFrame backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class EngineFamily(str, Enum):
    RPG_MAKER = "rpgmaker"
    GODOT = "godot"


class EngineVariant(str, Enum):
    XP = "xp"
    VX = "vx"
    VX_ACE = "vxace"
    MV = "mv"
    MZ = "mz"
    GODOT = "godot"
    UNKNOWN = "unknown"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Compatibility(str, Enum):
    SUPPORTED = "supported"
    NEEDS_TESTING = "needs_testing"
    UNKNOWN = "unknown"


@dataclass
class GameInspection:
    """Result of identifying a supported game directory."""

    source_path: Path
    family: EngineFamily = EngineFamily.RPG_MAKER
    engine: EngineVariant = EngineVariant.UNKNOWN
    runtime: str | None = None
    confidence: Confidence = Confidence.LOW
    game_root: Path | None = None
    game_name: str | None = None
    engine_version: str | None = None
    package_json: Path | None = None
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    compatibility: Compatibility = Compatibility.UNKNOWN

    @property
    def recognized(self) -> bool:
        return self.engine is not EngineVariant.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "family": self.family.value,
            "engine": self.engine.value,
            "runtime": self.runtime,
            "confidence": self.confidence.value,
            "game_root": str(self.game_root) if self.game_root else None,
            "game_name": self.game_name,
            "engine_version": self.engine_version,
            "package_json": str(self.package_json) if self.package_json else None,
            "evidence": list(self.evidence),
            "warnings": list(self.warnings),
            "compatibility": self.compatibility.value,
        }


@dataclass
class BuildResult:
    """Result of producing a Linux ARM64 game directory."""

    success: bool
    source_path: Path
    output_path: Path
    runtime_path: Path
    launcher_path: Path
    engine: EngineVariant
    engine_version: str | None
    game_name: str | None
    runtime_architecture: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "source_path": str(self.source_path),
            "output_path": str(self.output_path),
            "runtime_path": str(self.runtime_path),
            "launcher_path": str(self.launcher_path),
            "engine": self.engine.value,
            "engine_version": self.engine_version,
            "game_name": self.game_name,
            "runtime_architecture": self.runtime_architecture,
            "warnings": list(self.warnings),
        }
