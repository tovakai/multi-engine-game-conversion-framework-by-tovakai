"""Godot Windows-export to Linux ARM64 backend."""

from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path

from rpgmframe.elf import read_elf_architecture
from rpgmframe.godot import (
    find_godot_pack,
    inspect_godot_executable,
    is_csharp_export,
    materialize_pack,
)
from rpgmframe.godot_runtime import GodotRuntimeError, GodotRuntimeManager
from rpgmframe.launchers import godot_launcher_body
from rpgmframe.models import BuildResult, EngineVariant, GameInspection


class GodotBuildError(RuntimeError):
    """Raised when a Godot export cannot be converted safely."""


_IGNORE_NAMES = frozenset({".git", "__pycache__", ".DS_Store"})


def _normalize(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _ignore_windows_export(directory: str, contents: list[str]) -> list[str]:
    del directory
    ignored: list[str] = []
    for name in contents:
        lower = name.casefold()
        if name in _IGNORE_NAMES or lower.endswith(".pyc"):
            ignored.append(name)
        elif lower.endswith(".exe") or lower.endswith(".pdb"):
            ignored.append(name)
    return ignored


def _copy_runtime_bundle(runtime_path: Path, staging: Path) -> list[str]:
    """Copy the ARM64 Godot entrypoint and portable sibling shared libraries."""
    copied: list[str] = []

    binary = runtime_path / "godot.arm64"
    shutil.copy2(binary, staging / "godot.arm64")
    (staging / "godot.arm64").chmod(
        (staging / "godot.arm64").stat().st_mode | 0o755
    )
    copied.append("godot.arm64")

    for companion in sorted(runtime_path.glob("*.so*"), key=lambda path: path.name):
        if not companion.is_file():
            continue
        architecture = read_elf_architecture(companion)
        if architecture is not None and architecture != "aarch64":
            raise GodotBuildError(
                f"Runtime companion is {architecture}, not aarch64: {companion}"
            )
        shutil.copy2(companion, staging / companion.name)
        copied.append(companion.name)

    manifest = runtime_path / "runtime.json"
    if manifest.is_file():
        shutil.copy2(manifest, staging / "runtime.json")
        copied.append("runtime.json")

    return copied

def _staging_path(output: Path) -> Path:
    return output.parent / f".{output.name}.tmp-{uuid.uuid4().hex[:8]}"


def _install(staging: Path, output: Path, *, force: bool) -> None:
    if not output.exists():
        staging.rename(output)
        return
    if not force:
        raise GodotBuildError(
            f"Output already exists: {output}. Pass --force to replace it."
        )
    backup = output.parent / f".{output.name}.old-{uuid.uuid4().hex[:8]}"
    output.rename(backup)
    try:
        staging.rename(output)
    except Exception:
        backup.rename(output)
        raise
    else:
        shutil.rmtree(backup, ignore_errors=True)


def build_godot_game(
    *,
    source_path: Path,
    output_path: Path,
    inspection: GameInspection,
    runtime: Path | str | None,
    force: bool,
    archive_type: str | None,
    progress: Callable[[str], None] | None,
    stage_progress: Callable[[float, str], None] | None = None,
) -> BuildResult:
    def stage(value: float, message: str) -> None:
        if stage_progress:
            stage_progress(max(0.0, min(1.0, value)), message)

    stage(0.05, "Validating Godot payload")
    if inspection.engine is not EngineVariant.GODOT:
        raise GodotBuildError("Godot backend received a non-Godot game")
    if inspection.game_root is None or inspection.engine_version is None:
        raise GodotBuildError("Godot export is missing payload root or engine version")
    if is_csharp_export(inspection.game_root):
        raise GodotBuildError(
            "Godot C#/.NET exports are recognized but not automatically portable "
            "yet; use a GDScript/native export for the current backend."
        )

    pack = find_godot_pack(inspection.game_root)
    if pack is None:
        raise GodotBuildError("Could not select one unambiguous Godot PCK")

    fingerprint = inspect_godot_executable(inspection.game_root, pack)
    # Opt-in runtime bundle produced by the tested GodotSteam ARM64 recipe.
    # Never silently substitute it for unrelated custom Godot exports.
    if (
        runtime is None
        and fingerprint is not None
        and fingerprint.custom_build
        and fingerprint.godotsteam
    ):
        configured = os.environ.get("TOVAKAI_GODOTSTEAM_ARM64_RUNTIME")
        if configured:
            candidate = _normalize(configured)
            manifest = candidate / "runtime.json"
            try:
                import json
                metadata = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                metadata = None
            if not isinstance(metadata, dict) or metadata.get("recipe") != "godot-3.7-dev1-godotsteam-3.30-arm64":
                raise GodotBuildError(
                    "Configured GodotSteam runtime has no matching recipe manifest: "
                    f"{manifest}"
                )
            runtime = candidate
            if progress:
                progress(f"Using opt-in GodotSteam ARM64 runtime: {candidate}")

    if runtime is None and fingerprint is not None and fingerprint.custom_build:
        details = "custom Godot development build"
        if fingerprint.godotsteam:
            details += " with built-in GodotSteam"
        raise GodotBuildError(
            f"Detected {details} in {fingerprint.path.name}. "
            "The official stable-runtime resolver cannot safely substitute this "
            "engine. Supply a matching Linux ARM64 custom runtime instead."
        )

    if runtime is None:
        stage(0.15, f"Resolving Godot {inspection.engine_version} ARM64 runtime")
        try:
            runtime_path = GodotRuntimeManager().ensure_godot(
                inspection.engine_version,
                progress=progress,
            )
        except GodotRuntimeError as exc:
            raise GodotBuildError(str(exc)) from exc
    else:
        runtime_path = _normalize(runtime)
        binary = runtime_path / "godot.arm64"
        if not binary.is_file():
            raise GodotBuildError(
                f"Supplied Godot runtime must contain godot.arm64: {runtime_path}"
            )
        if read_elf_architecture(binary) != "aarch64":
            raise GodotBuildError(f"Supplied Godot runtime is not AArch64: {binary}")

    stage(0.35, "Godot ARM64 runtime ready")

    if output_path.exists() and not force:
        raise GodotBuildError(
            f"Output already exists: {output_path}. Pass --force to replace it."
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = _staging_path(output_path)
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)

    warnings = list(inspection.warnings)
    if archive_type:
        warnings.insert(0, f"Built directly from {archive_type.upper()} input")

    try:
        stage(0.45, "Preparing build staging area")
        staging.mkdir()
        runtime_files = _copy_runtime_bundle(runtime_path, staging)
        if progress:
            progress("Runtime bundle: " + ", ".join(runtime_files))

        stage(0.55, "Copying Godot game payload")
        if progress:
            progress("Copying Godot game payload into ARM64 build")
        game_dir = staging / "game"
        shutil.copytree(
            inspection.game_root,
            game_dir,
            ignore=_ignore_windows_export,
            symlinks=True,
            ignore_dangling_symlinks=True,
        )

        pck_name = pack.path.with_suffix(".pck").name
        pck_target = game_dir / pck_name
        if pack.embedded:
            materialize_pack(pack, pck_target)
        elif not pck_target.is_file():
            shutil.copy2(pack.path, pck_target)

        # Some GodotSteam exports locate steam_data.json beside the native
        # executable, not inside the game directory. Keep the original copy
        # and install a companion beside godot.arm64.
        steam_data = inspection.game_root / "steam_data.json"
        if steam_data.is_file() and (runtime_path / "runtime.json").is_file():
            import json
            try:
                metadata = json.loads((runtime_path / "runtime.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                metadata = {}
            if metadata.get("recipe") == "godot-3.7-dev1-godotsteam-3.30-arm64":
                shutil.copy2(steam_data, staging / "steam_data.json")
                if progress:
                    progress("Preserved GodotSteam steam_data.json beside runtime")

        stage(0.78, "Checking native Windows dependencies")
        dlls = list(inspection.game_root.rglob("*.dll"))
        if dlls:
            warnings.append(
                f"Found {len(dlls)} Windows DLL file(s). If the game uses native "
                "GDExtension/GDNative plugins, Linux ARM64 equivalents will be required."
            )

        stage(0.90, "Writing ARM64 launcher")
        launcher = staging / "launch.sh"
        launcher.write_text(
            godot_launcher_body(f"game/{pck_name}"),
            encoding="utf-8",
            newline="\n",
        )
        launcher.chmod(launcher.stat().st_mode | 0o755)
        _install(staging, output_path, force=force)
        stage(1.0, "Godot ARM64 package complete")
    except GodotBuildError:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise GodotBuildError(f"Godot build failed: {exc}") from exc

    return BuildResult(
        success=True,
        source_path=source_path,
        output_path=output_path,
        runtime_path=runtime_path,
        launcher_path=output_path / "launch.sh",
        engine=EngineVariant.GODOT,
        engine_version=inspection.engine_version,
        game_name=inspection.game_name,
        runtime_architecture="aarch64",
        warnings=warnings,
    )
