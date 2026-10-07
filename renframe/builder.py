"""Build ARM64-ready Ren'Py game directories from a supplied ARM runtime."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from renframe.inspect_service import inspect_game
from renframe.models import BuildResult, Compatibility, GameInspection, RuntimeInspection
from renframe.runtime import (
    detect_runtime_layout,
    inspect_runtime,
    runtime_architecture_is_clearly_x86,
)
from renframe.utils import (
    is_ancestor,
    is_dangerous_output_path,
    is_path_inside,
    normalize_path,
    paths_conflict,
    sanitize_fs_name,
)


class BuildError(RuntimeError):
    """Raised when a build cannot proceed."""


_COPY_IGNORE_NAMES = frozenset({".git", "__pycache__", ".hg", ".svn", ".DS_Store"})


def default_output_path(source: Path) -> Path:
    """Default output: ``<source-parent>/<source-name>-frame``."""
    source = normalize_path(source)
    return source.parent / f"{source.name}-frame"


def _ignore_dev_junk(directory: str, contents: list[str]) -> list[str]:
    ignored: list[str] = []
    for name in contents:
        if name in _COPY_IGNORE_NAMES:
            ignored.append(name)
        elif name.endswith(".pyc"):
            ignored.append(name)
    return ignored


def validate_output_paths(
    source: Path,
    output: Path,
    runtime: Path,
) -> None:
    """Refuse unsafe or overlapping source/output/runtime combinations."""
    source_r = normalize_path(source)
    output_r = normalize_path(output)
    runtime_r = normalize_path(runtime)

    if is_dangerous_output_path(output_r):
        raise BuildError(f"Refusing dangerous output path: {output_r}")

    if paths_conflict(source_r, output_r):
        raise BuildError(
            f"Output path conflicts with source "
            f"(equal, nested, or parent): output={output_r}, source={source_r}"
        )

    if paths_conflict(runtime_r, output_r):
        raise BuildError(
            f"Output path conflicts with runtime "
            f"(equal, nested, or parent): output={output_r}, runtime={runtime_r}"
        )

    if is_path_inside(runtime_r, source_r) and is_path_inside(output_r, source_r):
        # Already covered by paths_conflict for source/output; keep explicit.
        pass


def validate_force_delete_target(
    target: Path,
    *,
    source: Path,
    runtime: Path,
) -> None:
    """Extra safety checks before deleting an existing output directory."""
    target_r = normalize_path(target)
    source_r = normalize_path(source)
    runtime_r = normalize_path(runtime)

    if is_dangerous_output_path(target_r):
        raise BuildError(f"Refusing to delete dangerous path: {target_r}")
    if target_r == source_r:
        raise BuildError("Refusing to delete the source directory")
    if target_r == runtime_r:
        raise BuildError("Refusing to delete the runtime directory")
    if is_ancestor(target_r, source_r):
        raise BuildError(
            f"Refusing to delete an ancestor of the source: {target_r}"
        )
    if is_ancestor(target_r, runtime_r):
        raise BuildError(
            f"Refusing to delete an ancestor of the runtime: {target_r}"
        )


def _validate_source_inspection(
    inspection: GameInspection,
    *,
    allow_version_mismatch: bool,
) -> list[str]:
    """Raise BuildError for hard source blockers; return soft warnings."""
    warnings: list[str] = []

    if not inspection.is_renpy or inspection.compatibility == Compatibility.NOT_A_RENPY_GAME:
        raise BuildError(
            f"Source is not a Ren'Py game: {inspection.source_path}"
        )

    if inspection.compatibility == Compatibility.INCOMPATIBLE_NATIVE_CODE:
        detail = "; ".join(inspection.potential_issues) or "game-owned native code"
        raise BuildError(
            f"Source is incompatible with ARM64 runtime replacement "
            f"({Compatibility.INCOMPATIBLE_NATIVE_CODE.value}): {detail}"
        )

    if inspection.compatibility == Compatibility.UNKNOWN_RENPY_VERSION:
        message = (
            "Could not determine the source game's Ren'Py version/generation"
        )
        if not allow_version_mismatch:
            raise BuildError(
                message
                + ". Refusing to build without a reliable match. "
                "Use --allow-version-mismatch only after manual review."
            )
        warnings.append(
            message + " (proceeding because --allow-version-mismatch was set)"
        )

    if inspection.compatibility == Compatibility.NEEDS_TESTING:
        warnings.append(
            "Source compatibility is NEEDS_TESTING; build will proceed but "
            "runtime validation on device is required"
        )

    if not (inspection.source_path / "game").is_dir():
        raise BuildError(
            f"Source game is missing a game/ directory: {inspection.source_path}"
        )

    return warnings


def _validate_runtime_inspection(inspection: RuntimeInspection) -> list[str]:
    """Raise BuildError for bad runtimes; return soft warnings."""
    if not inspection.is_renpy_runtime:
        detail = "; ".join(inspection.warnings) or "unrecognized layout"
        raise BuildError(
            f"Supplied --runtime does not look like a Ren'Py runtime: "
            f"{inspection.path} ({detail})"
        )

    if runtime_architecture_is_clearly_x86(inspection):
        arches = ", ".join(inspection.lib_architectures) or inspection.architecture
        raise BuildError(
            f"Supplied runtime appears to be x86-only ({arches}); "
            f"need an ARM64/aarch64 Ren'Py runtime: {inspection.path}"
        )

    return list(inspection.warnings)


def check_version_compatibility(
    game: GameInspection,
    runtime: RuntimeInspection,
    *,
    allow_mismatch: bool,
) -> list[str]:
    """
    Compare Ren'Py generation/version conservatively.

    Generation mismatches fail unless ``allow_mismatch`` is set.
    Same-generation minor differences warn only.
    """
    warnings: list[str] = []

    if game.generation is not None and runtime.generation is not None:
        if game.generation != runtime.generation:
            message = (
                f"Ren'Py generation mismatch: game appears to be "
                f"{game.generation}.x"
                + (f" ({game.renpy_version})" if game.renpy_version else "")
                + f", runtime appears to be {runtime.generation}.x"
                + (f" ({runtime.version})" if runtime.version else "")
                + ". A Ren'Py 7 game needs a Ren'Py 7 runtime (and vice versa for 8)."
            )
            if not allow_mismatch:
                raise BuildError(
                    message + " Use --allow-version-mismatch to override."
                )
            warnings.append(
                message + " Proceeding because --allow-version-mismatch was set."
            )
    elif game.generation is not None and runtime.generation is None:
        message = (
            f"Game Ren'Py generation is {game.generation}.x but runtime "
            f"generation could not be determined"
        )
        if not allow_mismatch:
            raise BuildError(
                message + ". Use --allow-version-mismatch to override."
            )
        warnings.append(message + " (overridden with --allow-version-mismatch)")

    if (
        game.renpy_version
        and runtime.version
        and game.renpy_version != runtime.version
        and game.generation == runtime.generation
    ):
        warnings.append(
            f"Game appears to use Ren'Py {game.renpy_version} but runtime is "
            f"{runtime.version}. Proceeding, but compatibility is not guaranteed."
        )

    return warnings


def _resolve_names(inspection: GameInspection, source: Path) -> tuple[str, str]:
    """Return (display_name, filesystem_name)."""
    display = inspection.game_name or source.name or "Game"
    fs_name = sanitize_fs_name(display, fallback=sanitize_fs_name(source.name))
    return display, fs_name


def _launcher_script_body(layout_root_relative_launcher: str | None,
                          python_rel: str | None,
                          renpy_py_rel: str | None) -> str:
    """
    Generate a POSIX bash launcher.

    Prefer the runtime's ``renpy.sh`` (project dir as argv). Fall back to
    ``python`` + ``renpy.py`` when that is how the tree is meant to boot.
    """
    if layout_root_relative_launcher:
        launch = f'exec "$ROOT/{layout_root_relative_launcher}" "$ROOT" "$@"'
    elif python_rel and renpy_py_rel:
        launch = (
            f'exec "$ROOT/{python_rel}" "$ROOT/{renpy_py_rel}" "$ROOT" "$@"'
        )
    else:
        raise BuildError(
            "Runtime has no usable launcher (expected renpy.sh, or "
            "ARM lib python + renpy.py)"
        )

    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "\n"
        'ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        "\n"
        f"{launch}\n"
    )


def generate_launcher(output_root: Path, launcher_name: str) -> Path:
    """Write an executable game launcher into *output_root*."""
    layout = detect_runtime_layout(output_root)
    body = _launcher_script_body(
        layout.launcher_relative,
        layout.python_bin_relative,
        layout.renpy_py_relative,
    )
    launcher_path = output_root / f"{launcher_name}.sh"
    launcher_path.write_text(body, encoding="utf-8", newline="\n")
    try:
        mode = launcher_path.stat().st_mode
        launcher_path.chmod(mode | 0o755)
    except OSError:
        # Windows may not honor Unix execute bits; content still valid for Frame.
        pass
    return launcher_path


def _staging_dir_for(output: Path) -> Path:
    token = uuid.uuid4().hex[:8]
    return output.parent / f".{output.name}.tmp-{token}"


def _replace_output(staging: Path, output: Path, *, force: bool) -> None:
    """Move staging into output, replacing an existing tree only when forced."""
    output_r = normalize_path(output)
    if output_r.exists():
        if not force:
            raise BuildError(
                f"Output already exists: {output_r}. Pass --force to replace it."
            )
        backup = output.parent / f".{output.name}.old-{uuid.uuid4().hex[:8]}"
        try:
            output_r.rename(backup)
        except OSError as exc:
            raise BuildError(
                f"Failed to move existing output aside for replacement: {exc}"
            ) from exc
        try:
            staging.rename(output_r)
        except OSError as exc:
            try:
                backup.rename(output_r)
            except OSError:
                pass
            raise BuildError(
                f"Failed to move staged build into output: {exc}"
            ) from exc
        shutil.rmtree(backup, ignore_errors=True)
        return

    try:
        staging.rename(output_r)
    except OSError:
        # Cross-device rename fallback.
        shutil.move(str(staging), str(output_r))


def _copy_runtime_and_game(
    *,
    runtime: Path,
    source: Path,
    staging: Path,
    launcher_fs_name: str,
) -> Path:
    """Populate staging from runtime + source game/; return launcher path."""
    shutil.copytree(
        runtime,
        staging,
        symlinks=True,
        ignore=_ignore_dev_junk,
        dirs_exist_ok=False,
        ignore_dangling_symlinks=True,
    )

    staging_game = staging / "game"
    if staging_game.exists():
        if staging_game.is_dir():
            shutil.rmtree(staging_game)
        else:
            staging_game.unlink()

    source_game = source / "game"
    shutil.copytree(
        source_game,
        staging_game,
        symlinks=True,
        ignore=_ignore_dev_junk,
        ignore_dangling_symlinks=True,
    )

    # Never ship the source game's x86 lib/renpy into the Frame build.
    # Runtime copy already provided those; source payload is game/ only.

    return generate_launcher(staging, launcher_fs_name)


def build_game(
    source: Path | str,
    *,
    output: Path | str | None = None,
    runtime: Path | str | None = None,
    force: bool = False,
    dry_run: bool = False,
    allow_version_mismatch: bool = False,
) -> BuildResult:
    """
    Create a self-contained ARM64 Ren'Py game directory.

    Strategy: copy the supplied ARM runtime/template, replace its ``game/``
    with the source project's ``game/``, and generate a launcher. The original
    source tree is never modified.
    """
    if runtime is None:
        raise BuildError(
            "--runtime is required. Automatic runtime download is not "
            "implemented yet; pass a local ARM64 Ren'Py SDK/runtime path."
        )

    source_path = normalize_path(source)
    runtime_path = normalize_path(runtime)
    output_path = (
        normalize_path(output) if output is not None else default_output_path(source_path)
    )

    if not source_path.exists() or not source_path.is_dir():
        raise BuildError(f"Source path is not a directory: {source_path}")
    if not runtime_path.exists() or not runtime_path.is_dir():
        raise BuildError(f"Runtime path is not a directory: {runtime_path}")

    warnings: list[str] = []

    game_inspection = inspect_game(source_path)
    warnings.extend(
        _validate_source_inspection(
            game_inspection,
            allow_version_mismatch=allow_version_mismatch,
        )
    )
    warnings.extend(game_inspection.warnings)

    runtime_inspection = inspect_runtime(runtime_path)
    warnings.extend(_validate_runtime_inspection(runtime_inspection))

    warnings.extend(
        check_version_compatibility(
            game_inspection,
            runtime_inspection,
            allow_mismatch=allow_version_mismatch,
        )
    )

    # Ensure the runtime tree is launchable before we copy anything.
    layout = detect_runtime_layout(runtime_path)
    if layout.launcher is None and not (
        layout.python_bin is not None and layout.renpy_py is not None
    ):
        raise BuildError(
            "Runtime has no usable launcher entrypoint "
            "(need renpy.sh, or ARM lib/python + renpy.py)"
        )

    validate_output_paths(source_path, output_path, runtime_path)

    display_name, fs_name = _resolve_names(game_inspection, source_path)
    launcher_path = output_path / f"{fs_name}.sh"

    if output_path.exists() and not force and not dry_run:
        raise BuildError(
            f"Output already exists: {output_path}. Pass --force to replace it."
        )

    if output_path.exists() and force:
        validate_force_delete_target(
            output_path, source=source_path, runtime=runtime_path
        )

    result = BuildResult(
        success=True,
        output_path=output_path,
        launcher_path=launcher_path,
        source_version=game_inspection.renpy_version,
        runtime_version=runtime_inspection.version,
        game_name=fs_name,
        display_name=display_name,
        source_path=source_path,
        runtime_path=runtime_path,
        runtime_architecture=runtime_inspection.architecture,
        warnings=_dedupe_warnings(warnings),
        dry_run=dry_run,
    )

    if dry_run:
        return result

    staging = _staging_dir_for(output_path)
    if staging.exists():
        shutil.rmtree(staging)

    try:
        built_launcher = _copy_runtime_and_game(
            runtime=runtime_path,
            source=source_path,
            staging=staging,
            launcher_fs_name=fs_name,
        )
        _replace_output(staging, output_path, force=force)
        # Launcher path after rename matches the planned location.
        result.launcher_path = output_path / built_launcher.name
    except BuildError:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise
    except Exception as exc:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise BuildError(f"Build failed: {exc}") from exc
    finally:
        # If rename succeeded, staging is gone; if not, cleaned above.
        if staging.exists() and not output_path.exists():
            shutil.rmtree(staging, ignore_errors=True)

    return result


def _dedupe_warnings(warnings: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in warnings:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out
