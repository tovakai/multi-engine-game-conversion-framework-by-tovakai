"""Godot Windows-export to Linux ARM64 backend."""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Callable
from pathlib import Path

from rpgmframe.elf import read_elf_architecture
from rpgmframe.godot import find_godot_pack, is_csharp_export, materialize_pack
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
) -> BuildResult:
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

    if runtime is None:
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
        staging.mkdir()
        shutil.copy2(runtime_path / "godot.arm64", staging / "godot.arm64")
        (staging / "godot.arm64").chmod(
            (staging / "godot.arm64").stat().st_mode | 0o755
        )

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

        dlls = list(inspection.game_root.rglob("*.dll"))
        if dlls:
            warnings.append(
                f"Found {len(dlls)} Windows DLL file(s). If the game uses native "
                "GDExtension/GDNative plugins, Linux ARM64 equivalents will be required."
            )

        launcher = staging / "launch.sh"
        launcher.write_text(
            godot_launcher_body(f"game/{pck_name}"),
            encoding="utf-8",
            newline="\n",
        )
        launcher.chmod(launcher.stat().st_mode | 0o755)
        _install(staging, output_path, force=force)
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
