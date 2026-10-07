"""Unified build dispatcher."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from renpy_arm.convert import ConvertError, convert_game as convert_renpy
from rpgmframe.builder import BuildError as RPGMBuildError
from rpgmframe.builder import build_game as build_rpgm
from rpgmframe.packaging import PackagingError, create_tar_gz
from rpgmframe.runtime import DEFAULT_NWJS_VERSION

from .detector import inspect_source
from .models import Backend, UnifiedBuildResult
from .source import source_base_name

ProgressFn = Callable[[str, float | None, str | None], None]
LogFn = Callable[[str], None]


class BuildError(RuntimeError):
    pass


def _progress(
    callback: ProgressFn | None,
    stage: str,
    fraction: float | None = None,
    detail: str | None = None,
) -> None:
    if callback:
        callback(stage, fraction, detail)


def default_output_dir(source: Path | str) -> Path:
    return Path(source).expanduser().resolve().parent


def _renpy_output_name(source: Path) -> str:
    return f"{source_base_name(source)}-linux-aarch64.zip"


def _rpgm_output_name(source: Path) -> str:
    return f"{source_base_name(source)}-frame"


def build_game(
    source: Path | str,
    *,
    output_dir: Path | str | None = None,
    force: bool = False,
    archive: bool = True,
    runtime: Path | str | None = None,
    nwjs_runtime_version: str = DEFAULT_NWJS_VERSION,
    renpy_version_override: str | None = None,
    full_renpy_archive: bool = False,
    progress: ProgressFn | None = None,
    log: LogFn | None = None,
) -> UnifiedBuildResult:
    source_path = Path(source).expanduser().resolve()
    inspection = inspect_source(source_path)
    if not inspection.recognized:
        detail = "; ".join(inspection.warnings) or "unrecognized source"
        raise BuildError(f"Could not choose a conversion backend: {detail}")
    if not inspection.buildable:
        raise BuildError(
            f"{inspection.engine} was recognized but is not currently buildable "
            f"({inspection.compatibility})."
        )

    destination = (
        Path(output_dir).expanduser().resolve()
        if output_dir is not None
        else default_output_dir(source_path)
    )
    destination.mkdir(parents=True, exist_ok=True)

    if inspection.backend is Backend.RENPY:
        output_zip = destination / _renpy_output_name(source_path)
        if output_zip.exists():
            if not force:
                raise BuildError(
                    f"Output already exists: {output_zip}. Pass --force to replace it."
                )
            output_zip.unlink()

        warnings = list(inspection.warnings)
        if not archive:
            warnings.append(
                "Ren'Py conversion emits a ZIP as its primary portable artifact; "
                "--no-archive does not suppress it."
            )

        try:
            with tempfile.TemporaryDirectory(prefix="tovakai-renpy-build-") as temporary:
                work = Path(temporary)
                conversion_source = source_path
                if source_path.is_dir():
                    _progress(progress, "Preparing source", None, "Copying Ren'Py game to a safe working tree")
                    conversion_source = work / source_path.name
                    shutil.copytree(
                        source_path,
                        conversion_source,
                        symlinks=True,
                        ignore_dangling_symlinks=True,
                    )

                result = convert_renpy(
                    conversion_source,
                    output_zip=output_zip,
                    version_override=renpy_version_override,
                    force=force,
                    work_dir=work / "work",
                    full_archive=full_renpy_archive,
                    log=log,
                    progress=progress,
                )
        except ConvertError as exc:
            raise BuildError(str(exc)) from exc
        except Exception as exc:
            raise BuildError(f"Ren'Py conversion failed: {exc}") from exc

        launcher = None
        return UnifiedBuildResult(
            success=True,
            source_path=source_path,
            backend=Backend.RENPY,
            family="renpy",
            engine="Ren'Py",
            engine_version=result.version,
            game_name=result.game_name,
            output_path=output_zip,
            archive_path=output_zip,
            launcher_path=launcher,
            warnings=warnings + list(result.messages),
        )

    build_output = destination / _rpgm_output_name(source_path)

    def rpgm_progress(message: str) -> None:
        _progress(progress, "Building", None, message)
        if log:
            log(message)

    try:
        result = build_rpgm(
            source_path,
            runtime=runtime,
            runtime_version=nwjs_runtime_version,
            output=build_output,
            force=force,
            progress=rpgm_progress,
        )
        archive_path = (
            create_tar_gz(result.output_path, force=force)
            if archive
            else None
        )
    except (RPGMBuildError, PackagingError) as exc:
        raise BuildError(str(exc)) from exc
    except Exception as exc:
        raise BuildError(f"{inspection.engine} conversion failed: {exc}") from exc

    _progress(progress, "Done", 1.0, str(archive_path or result.output_path))
    return UnifiedBuildResult(
        success=True,
        source_path=source_path,
        backend=Backend.RPGMFRAME,
        family=inspection.family,
        engine=inspection.engine,
        engine_version=result.engine_version,
        game_name=result.game_name,
        output_path=archive_path or result.output_path,
        build_directory=result.output_path,
        archive_path=archive_path,
        launcher_path=result.launcher_path,
        runtime_path=result.runtime_path,
        runtime_architecture=result.runtime_architecture,
        warnings=list(result.warnings),
    )
