"""Build ARM64-ready Ren'Py game directories from a supplied ARM runtime."""

from __future__ import annotations

import re
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path

from renframe.inspect_service import inspect_game
from renframe.models import BuildResult, Compatibility, GameInspection, RuntimeInspection
from renframe.runtime import (
    RuntimeDownloadError,
    RuntimeManager,
    detect_runtime_layout,
    inspect_runtime,
    normalize_release_version,
    python_tag_for_generation,
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


# Ren'Py distributions often ship bytecode-only standard libraries and engine modules.
# Do not exclude .pyc or __pycache__: either may contain required runtime code.
_COPY_IGNORE_NAMES = frozenset({".git", ".hg", ".svn", ".DS_Store"})


def default_output_path(source: Path) -> Path:
    """Default output: ``<source-parent>/<source-name>-frame``."""
    source = normalize_path(source)
    return source.parent / f"{source.name}-frame"


def _ignore_dev_junk(directory: str, contents: list[str]) -> list[str]:
    ignored: list[str] = []
    for name in contents:
        if name in _COPY_IGNORE_NAMES:
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


def _find_source_launcher(root: Path) -> Path | None:
    """Find an existing distributed Ren'Py shell launcher when one is present."""
    ignored = {
        "launch.sh",
        "launch-steam.sh",
        "add-to-steam.sh",
        "make-linux-arm.sh",
    }
    preferred: list[Path] = []
    fallback: list[Path] = []
    for path in sorted(root.glob("*.sh")):
        if path.name in ignored:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "RENPY_PLATFORM" in text or "lib/" in text:
            preferred.append(path)
        else:
            fallback.append(path)
    return (preferred or fallback or [None])[0]


def _patch_source_launcher_for_arm(path: Path) -> bool:
    """Teach older distributed Ren'Py launchers about Linux AArch64."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False

    if "linux-aarch64" in text:
        return True

    pattern = re.compile(r"(?m)^(?P<indent>[ \t]*)Linux-\*\)[ \t]*\n")
    match = pattern.search(text)
    if match is None:
        # Newer launchers may already derive linux-$(uname -m) generically.
        return "linux-$(uname -m)" in text

    indent = match.group("indent")
    snippet = (
        f'{indent}*-aarch64|*-arm64)\n'
        f'{indent}    RENPY_PLATFORM="linux-aarch64"\n'
        f'{indent}    ;;\n'
    )
    path.write_text(
        text[: match.start()] + snippet + text[match.start() :],
        encoding="utf-8",
        newline="\n",
    )
    return True


def _write_grafted_launcher(
    root: Path,
    *,
    source_launcher: Path | None,
    platform_name: str,
) -> Path:
    launcher = root / "launch.sh"
    if source_launcher is not None and _patch_source_launcher_for_arm(source_launcher):
        relative = source_launcher.relative_to(root).as_posix()
        command = f'exec bash "$ROOT/{relative}" "$ROOT" "$@"'
    else:
        command = (
            f'RUNTIME="$ROOT/lib/{platform_name}"\n'
            'if [[ -x "$RUNTIME/renpy" ]]; then\n'
            '    exec "$RUNTIME/renpy" "$ROOT" "$@"\n'
            'elif [[ -x "$RUNTIME/python" && -f "$ROOT/renpy.py" ]]; then\n'
            '    exec "$RUNTIME/python" "$ROOT/renpy.py" "$ROOT" "$@"\n'
            'fi\n'
            'echo "No usable Ren\\x27Py ARM64 runtime entrypoint found." >&2\n'
            'exit 126'
        )

    launcher.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n\n"
        'ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'export RENPY_PLATFORM="linux-aarch64"\n\n'
        '# Files transferred through Windows may lose executable permissions.\n'
        '# Restore them for the selected ARM64 runtime before launching.\n'
        'RUNTIME_DIR="$ROOT/lib/py3-linux-aarch64"\n'
        '[[ -d "$RUNTIME_DIR" ]] || RUNTIME_DIR="$ROOT/lib/py2-linux-aarch64"\n'
        'if [[ -d "$RUNTIME_DIR" ]]; then\n'
        '    for binary in "$RUNTIME_DIR"/*; do\n'
        '        [[ -f "$binary" && ! -L "$binary" && -x "$binary" ]] && continue\n'
        '        [[ -f "$binary" && ! -L "$binary" ]] || continue\n'
        '        chmod u+x "$binary" 2>/dev/null || true\n'
        '    done\n'
        'fi\n\n'
        + command
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    try:
        launcher.chmod(launcher.stat().st_mode | 0o755)
    except OSError:
        pass
    return launcher


def _copy_source_and_arm_platform(
    *,
    source: Path,
    platform: Path,
    staging: Path,
) -> Path:
    """Preserve the distributed game and graft in only the ARM64 platform slice."""
    shutil.copytree(
        source,
        staging,
        symlinks=True,
        ignore=_ignore_dev_junk,
        dirs_exist_ok=False,
        ignore_dangling_symlinks=True,
    )

    destination = staging / "lib" / platform.name
    if destination.exists():
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(platform, destination, symlinks=True)

    for child in destination.iterdir():
        if child.is_file() and not child.is_symlink():
            try:
                child.chmod(child.stat().st_mode | 0o755)
            except OSError:
                pass

    source_launcher = _find_source_launcher(staging)
    if source_launcher is not None:
        runtime_entry = next(
            (
                candidate
                for candidate in (destination / "renpy", destination / "python")
                if candidate.is_file()
            ),
            None,
        )
        if runtime_entry is not None:
            game_entry = destination / source_launcher.stem
            if game_entry != runtime_entry:
                shutil.copy2(runtime_entry, game_entry)
                try:
                    game_entry.chmod(game_entry.stat().st_mode | 0o755)
                except OSError:
                    pass

    return _write_grafted_launcher(
        staging,
        source_launcher=source_launcher,
        platform_name=platform.name,
    )


def build_game(
    source: Path | str,
    *,
    output: Path | str | None = None,
    runtime: Path | str | None = None,
    force: bool = False,
    dry_run: bool = False,
    allow_version_mismatch: bool = False,
    progress: Callable[[str], None] | None = None,
    runtime_manager: RuntimeManager | None = None,
) -> BuildResult:
    """
    Create a self-contained Linux ARM64 Ren'Py game directory.

    Automatic mode preserves the distributed game tree and grafts the exact
    official sdkarm AArch64 platform slice into it. A manually supplied runtime
    keeps the older full-runtime replacement path as an escape hatch.
    """
    source_path = normalize_path(source)
    output_path = (
        normalize_path(output) if output is not None else default_output_path(source_path)
    )

    if not source_path.exists() or not source_path.is_dir():
        raise BuildError(f"Source path is not a directory: {source_path}")

    warnings: list[str] = []
    game_inspection = inspect_game(source_path)
    warnings.extend(
        _validate_source_inspection(
            game_inspection,
            allow_version_mismatch=allow_version_mismatch,
        )
    )
    warnings.extend(game_inspection.warnings)

    automatic_runtime = runtime is None
    runtime_inspection: RuntimeInspection | None = None

    if automatic_runtime:
        if not game_inspection.renpy_version:
            raise BuildError(
                "Could not determine an exact Ren'Py release for automatic ARM64 "
                "runtime acquisition. Supply --renpy-runtime after manual review."
            )
        try:
            release = normalize_release_version(game_inspection.renpy_version)
            python_tag = python_tag_for_generation(game_inspection.generation)
            manager = runtime_manager or RuntimeManager()
            runtime_path = manager.platform_path(release, python_tag)
            if not dry_run:
                runtime_path = manager.ensure_platform(
                    release,
                    python_tag,
                    progress=progress,
                )
        except RuntimeDownloadError as exc:
            raise BuildError(str(exc)) from exc

        runtime_version = release
        runtime_architecture = "aarch64"
        warnings.append(
            f"Automatically resolved official Ren'Py {release} "
            f"{python_tag}-linux-aarch64 runtime"
        )
    else:
        runtime_path = normalize_path(runtime)
        if not runtime_path.exists() or not runtime_path.is_dir():
            raise BuildError(f"Runtime path is not a directory: {runtime_path}")

        runtime_inspection = inspect_runtime(runtime_path)
        warnings.extend(_validate_runtime_inspection(runtime_inspection))
        warnings.extend(
            check_version_compatibility(
                game_inspection,
                runtime_inspection,
                allow_mismatch=allow_version_mismatch,
            )
        )

        layout = detect_runtime_layout(runtime_path)
        if layout.launcher is None and not (
            layout.python_bin is not None and layout.renpy_py is not None
        ):
            raise BuildError(
                "Runtime has no usable launcher entrypoint "
                "(need renpy.sh, or ARM lib/python + renpy.py)"
            )
        runtime_version = runtime_inspection.version
        runtime_architecture = runtime_inspection.architecture

    validate_output_paths(source_path, output_path, runtime_path)

    display_name, fs_name = _resolve_names(game_inspection, source_path)
    launcher_path = (
        output_path / "launch.sh"
        if automatic_runtime
        else output_path / f"{fs_name}.sh"
    )

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
        runtime_version=runtime_version,
        game_name=fs_name,
        display_name=display_name,
        source_path=source_path,
        runtime_path=runtime_path,
        runtime_architecture=runtime_architecture,
        warnings=_dedupe_warnings(warnings),
        dry_run=dry_run,
    )

    if dry_run:
        return result

    staging = _staging_dir_for(output_path)
    if staging.exists():
        shutil.rmtree(staging)

    try:
        if automatic_runtime:
            built_launcher = _copy_source_and_arm_platform(
                source=source_path,
                platform=runtime_path,
                staging=staging,
            )
        else:
            built_launcher = _copy_runtime_and_game(
                runtime=runtime_path,
                source=source_path,
                staging=staging,
                launcher_fs_name=fs_name,
            )
        _replace_output(staging, output_path, force=force)
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
