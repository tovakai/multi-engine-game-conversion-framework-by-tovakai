"""Godot Windows-export to Linux ARM64 backend."""

from __future__ import annotations

import json
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
    pack_requires_encryption_key,
    pack_native_extensions,
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

def _copy_godotsteam_data(source_root: Path, staging: Path) -> Path | None:
    """Copy steam_data.json beside godot.arm64 when the game ships one."""
    source = source_root / "steam_data.json"
    if not source.is_file():
        return None
    shutil.copy2(source, staging / "steam_data.json")
    return source


def _steam_app_id(steam_data: Path) -> str | None:
    """Read a numeric Steam App ID from a GodotSteam steam_data.json sidecar."""
    try:
        value = json.loads(steam_data.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    app_id = str(value.get("app_id", "")).strip()
    return app_id if app_id.isdigit() else None


def _write_steam_app_id(staging: Path, game_dir: Path, app_id: str) -> None:
    """Prevent SteamAPI_RestartAppIfNecessary from bouncing into x86 Steam."""
    for target in (staging / "steam_appid.txt", game_dir / "steam_appid.txt"):
        target.write_text(app_id + "\n", encoding="ascii")


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
    download_progress: Callable[[int, int | None], None] | None = None,
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
    if runtime is None and pack_requires_encryption_key(pack):
        raise GodotBuildError("Encrypted Godot content requires a matching ARM64 runtime built with the game's encryption key. Stock runtime substitution is unavailable.")
    if runtime is None and pack_native_extensions(pack):
        raise GodotBuildError("Native Godot extensions need matching Linux ARM64 libraries: " + ", ".join(pack_native_extensions(pack)))

    fingerprint = inspect_godot_executable(inspection.game_root, pack)
    if runtime is None and fingerprint is not None and fingerprint.modules:
        raise GodotBuildError("Custom Godot modules require a matching ARM64 runtime: " + ", ".join(fingerprint.modules))

    if runtime is None and fingerprint is not None and (fingerprint.custom_build or fingerprint.godotsteam):
        from rpgmframe.godot_custom_runtime import (
            CustomGodotRuntimeError,
            CustomGodotRuntimeManager,
            automatic_recipe_for,
        )

        recipe = automatic_recipe_for(
            inspection.engine_version,
            custom_build=fingerprint.custom_build,
            godotsteam=fingerprint.godotsteam,
        )
        if recipe is None:
            details = "custom Godot development build"
            if fingerprint.godotsteam:
                details += " with built-in GodotSteam"
            raise GodotBuildError(
                f"Detected {details} in {fingerprint.path.name}. "
                "No automatic ARM64 compatibility recipe matches this engine yet. "
                "Supply a matching Linux ARM64 custom runtime instead."
            )

        stage(0.12, "Resolving custom GodotSteam ARM64 compatibility runtime")
        from rpgmframe.godot_runtime_download import (
            RuntimeDownloadError,
            downloadable,
            ensure_downloaded_runtime,
        )
        if downloadable(recipe):
            try:
                runtime_path = ensure_downloaded_runtime(
                    recipe,
                    progress=progress,
                    download_progress=download_progress,
                )
            except RuntimeDownloadError as exc:
                raise GodotBuildError(str(exc)) from exc
        else:
            configured_cache = os.environ.get("RPGMFRAME_CACHE_DIR")
            cache_root = (
                Path(configured_cache).expanduser()
                if configured_cache
                else output_path.parent / ".tovakai-runtime-cache"
            )
            manager = CustomGodotRuntimeManager(
                cache_dir=cache_root,
                work_dir=output_path.parent / ".tovakai-runtime-work" / recipe,
            )
            try:
                runtime_path = manager.ensure_runtime(progress=progress)
            except CustomGodotRuntimeError as exc:
                raise GodotBuildError(str(exc)) from exc
    elif runtime is None:
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

        # GodotSteam reads steam_data.json relative to the engine executable,
        # not only from the PCK/game working directory. Preserve the original
        # sidecar beside godot.arm64 when present.
        if fingerprint is not None and fingerprint.godotsteam:
            steam_data = _copy_godotsteam_data(inspection.game_root, staging)
            if steam_data is not None:
                app_id = _steam_app_id(steam_data)
                if app_id is not None:
                    _write_steam_app_id(staging, game_dir, app_id)
                    if progress:
                        progress(
                            "Installed Steam app id metadata for direct ARM64 launch: "
                            + app_id
                        )
                else:
                    warnings.append(
                        "GodotSteam steam_data.json did not contain a numeric app_id; "
                        "direct Steam launch metadata was not generated."
                    )
                if progress:
                    progress("Copied GodotSteam steam_data.json beside runtime")
            else:
                warnings.append(
                    "Built-in GodotSteam detected but steam_data.json was not found "
                    "beside the Windows game executable."
                )

        pck_name = pack.path.with_suffix(".pck").name
        pck_target = game_dir / pck_name
        if pack.embedded:
            materialize_pack(pack, pck_target)
        elif not pck_target.is_file():
            shutil.copy2(pack.path, pck_target)

        stage(0.78, "Checking native Windows dependencies")
        dlls = list(inspection.game_root.rglob("*.dll"))
        if fingerprint is not None and fingerprint.godotsteam:
            dlls = [
                dll for dll in dlls
                if dll.name.casefold() not in {"steam_api.dll", "steam_api64.dll"}
            ]
        if dlls:
            warnings.append(
                f"Found {len(dlls)} Windows DLL file(s). If the game uses native "
                "GDExtension/GDNative plugins, Linux ARM64 equivalents will be required."
            )

        stage(0.90, "Writing ARM64 launcher")
        launcher = staging / "launch.sh"
        launcher.write_text(
            godot_launcher_body(
                f"game/{pck_name}",
                force_zink=bool(fingerprint is not None and fingerprint.custom_build),
            ),
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
