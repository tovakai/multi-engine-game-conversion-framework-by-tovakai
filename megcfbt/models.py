"""Unified models shared by the umbrella router, CLI, and GUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class UnifiedInspection:
    source_path: Path
    backend: str | None
    engine: str
    engine_label: str
    engine_version: str | None
    game_name: str | None
    compatibility: str
    confidence: str
    runtime_kind: str | None
    buildable: bool
    warnings: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    renpy_generation: int | None = None
    renpy_ddlc_753_candidate: bool = False
    renpy_legacy_arm64_candidate: bool = False
    renpy_prerelease_853_candidate: bool = False
    renpy_live2d_required: bool = False


@dataclass(frozen=True)
class UnifiedBuildResult:
    source_path: Path
    output_path: Path
    launcher_path: Path | None
    archive_path: Path | None
    backend: str
    engine: str
    engine_version: str | None
    game_name: str | None
    warnings: tuple[str, ...] = field(default_factory=tuple)
    remote_output: str | None = None
    steam_launch_command: str | None = None
    remote_job: str | None = None
    requires_frame_install: bool = False
    target_platform: str = 'linux-aarch64'
