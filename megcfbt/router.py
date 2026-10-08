"""Detect a game's engine and route conversion to the correct backend."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

from renframe.builder import BuildError as RenFrameBuildError
from renframe.builder import build_game as build_renpy_game
from renframe.inspect_service import inspect_game as inspect_renpy_game
from renframe.models import Compatibility as RenpyCompatibility
from rpgmframe.builder import BuildError as RPGMFrameBuildError
from rpgmframe.builder import build_game as build_rpgm_game
from rpgmframe.detector import inspect_game as inspect_rpgm_game
from rpgmframe.godot_custom_runtime import (
    automatic_recipe_for,
    host_can_build_automatic_runtime,
)
from rpgmframe.packaging import PackagingError, create_tar_gz
from rpgmframe.runtime import DEFAULT_NWJS_VERSION
from rpgmframe.source import SourceError, prepare_source

from megcfbt.models import UnifiedBuildResult, UnifiedInspection
from megcfbt import sts2


class ConversionError(RuntimeError):
    """Raised when the umbrella framework cannot inspect or convert a source."""


def source_base_name(source: Path | str) -> str:
    path = Path(source).expanduser()
    return path.stem if path.suffix.lower() == ".zip" else path.name


def output_path_for_source(source: Path | str, output_dir: Path | str) -> Path:
    return Path(output_dir).expanduser() / f"{source_base_name(source)}-frame"


def _single_directory_child(root: Path) -> Path | None:
    try:
        entries = [
            p
            for p in root.iterdir()
            if p.name not in {".DS_Store", "__MACOSX"} and not p.name.startswith("._")
        ]
    except OSError:
        return None
    directories = [p for p in entries if p.is_dir()]
    files = [p for p in entries if p.is_file()]
    if len(directories) == 1 and not files:
        return directories[0]
    return None


def _candidate_roots(root: Path, *, max_depth: int = 8) -> Iterator[Path]:
    """Yield root plus an unambiguous single-directory wrapper chain."""
    current = root
    yield current
    for _ in range(max_depth):
        child = _single_directory_child(current)
        if child is None:
            return
        current = child
        yield current


def _renpy_summary(root: Path) -> UnifiedInspection | None:
    result = inspect_renpy_game(root)
    if not result.is_renpy:
        return None

    compatibility = result.compatibility.value
    buildable = result.compatibility in {
        RenpyCompatibility.LIKELY_COMPATIBLE,
        RenpyCompatibility.NEEDS_TESTING,
    }
    evidence = tuple(
        f"{hint.source}: {hint.version or 'generation ' + str(hint.generation)}"
        for hint in result.version_hints
    )
    warnings = tuple(result.warnings + [
        issue for issue in result.potential_issues if issue != "none"
    ])

    return UnifiedInspection(
        source_path=root,
        backend="renframe",
        engine="renpy",
        engine_label="Ren'Py",
        engine_version=result.renpy_version,
        game_name=result.game_name,
        compatibility=compatibility,
        confidence=(result.version_hints[0].confidence if result.version_hints else "low"),
        runtime_kind=(
            f"official Ren'Py {result.renpy_version} sdkarm platform (automatic)"
            if result.renpy_version
            else "Ren'Py ARM64 runtime (manual override required)"
        ),
        buildable=buildable,
        warnings=warnings,
        evidence=evidence,
    )


def _rpgm_summary(root: Path) -> UnifiedInspection | None:
    result = inspect_rpgm_game(root)
    if not result.recognized:
        return None

    if result.engine.value == "godot":
        label = "Godot"
    else:
        label = f"RPG Maker {result.engine.value.upper()}"

    return UnifiedInspection(
        source_path=root,
        backend="rpgmframe",
        engine=result.engine.value,
        engine_label=label,
        engine_version=result.engine_version,
        game_name=result.game_name,
        compatibility=result.compatibility.value,
        confidence=result.confidence.value,
        runtime_kind=result.runtime,
        buildable=result.compatibility.value in {"supported", "needs_testing"},
        warnings=tuple(result.warnings),
        evidence=tuple(result.evidence),
    )


def _inspect_prepared(root: Path) -> UnifiedInspection:
    # Ren'Py needs explicit wrapper-chain handling. RPGMFrame also benefits from
    # seeing each candidate, but its own detector remains the authority for its engines.
    candidates = list(_candidate_roots(root))

    for candidate in candidates:
        summary = sts2.summary(candidate)
        if summary is not None:
            return summary

    for candidate in candidates:
        summary = _renpy_summary(candidate)
        if summary is not None:
            return summary

    for candidate in candidates:
        summary = _rpgm_summary(candidate)
        if summary is not None:
            return summary

    return UnifiedInspection(
        source_path=root,
        backend=None,
        engine="unknown",
        engine_label="Unknown",
        engine_version=None,
        game_name=root.name,
        compatibility="unknown",
        confidence="low",
        runtime_kind=None,
        buildable=False,
        warnings=(),
        evidence=(),
    )


def automatic_custom_godot_runtime_available(
    inspection: UnifiedInspection,
) -> bool:
    """Whether this host can build the narrow custom GodotSteam recipe."""
    if (
        inspection.backend != "rpgmframe"
        or inspection.engine != "godot"
        or inspection.runtime_kind != "godot-custom"
    ):
        return False

    godotsteam = any("godotsteam" in item.casefold() for item in inspection.evidence)
    recipe = automatic_recipe_for(
        inspection.engine_version,
        custom_build=True,
        godotsteam=godotsteam,
    )
    return recipe is not None and host_can_build_automatic_runtime()


def inspect_source(source: Path | str) -> UnifiedInspection:
    path = Path(source).expanduser().resolve()
    try:
        with prepare_source(path) as prepared:
            result = _inspect_prepared(prepared.root)
            return UnifiedInspection(
                source_path=path,
                backend=result.backend,
                engine=result.engine,
                engine_label=result.engine_label,
                engine_version=result.engine_version,
                game_name=result.game_name,
                compatibility=result.compatibility,
                confidence=result.confidence,
                runtime_kind=result.runtime_kind,
                buildable=result.buildable,
                warnings=result.warnings,
                evidence=result.evidence,
            )
    except SourceError as exc:
        raise ConversionError(str(exc)) from exc


def build_source(
    source: Path | str,
    *,
    output: Path | str | None = None,
    renpy_runtime: Path | str | None = None,
    backend_runtime: Path | str | None = None,
    runtime_version: str = DEFAULT_NWJS_VERSION,
    force: bool = False,
    archive: bool = True,
    allow_renpy_version_mismatch: bool = False,
    progress: Callable[[str], None] | None = None,
    stage_progress: Callable[[float, str], None] | None = None,
    sts2_sdk: Path | str | None = None,
    acknowledge_licenses: bool = False,
) -> UnifiedBuildResult:
    def stage(value: float, message: str) -> None:
        if stage_progress:
            stage_progress(max(0.0, min(1.0, value)), message)

    path = Path(source).expanduser().resolve()
    stage(0.03, "Inspecting source")
    inspection = inspect_source(path)
    stage(0.12, f"Detected {inspection.engine_label}")
    custom_godot_override = bool(
        inspection.backend == "rpgmframe"
        and inspection.engine == "godot"
        and inspection.runtime_kind == "godot-custom"
        and backend_runtime is not None
    )
    custom_godot_auto = automatic_custom_godot_runtime_available(inspection)
    sts2_ready = bool(inspection.backend == "sts2"
                      and inspection.compatibility == "needs_testing"
                      and sts2.available(sts2_sdk or backend_runtime))
    if (
        not inspection.buildable
        and not custom_godot_override
        and not custom_godot_auto
        and not sts2_ready
    ) or inspection.backend is None:
        extra = (
            " Supply a matching custom ARM64 runtime to continue. "
            "The automatic GodotSteam recipe is available only on a compatible "
            "Linux ARM64 host with the Frame Steam API and build toolchain."
            if inspection.runtime_kind == "godot-custom"
            else ""
        )
        raise ConversionError(
            f"Detected {inspection.engine_label}, but compatibility is "
            f"{inspection.compatibility}; refusing automatic conversion.{extra}"
            + (" " + " ".join(inspection.warnings) if inspection.backend == "sts2" else "")
        )

    output_path = (
        Path(output).expanduser().resolve()
        if output is not None
        else path.parent / f"{source_base_name(path)}-frame"
    )

    try:
        stage(0.20, "Building ARM64 package")
        if inspection.backend == "sts2":
            with prepare_source(path) as prepared:
                selected = _inspect_prepared(prepared.root)
                if selected.backend != "sts2":
                    raise ConversionError("STS2 source disappeared after extraction")
                try:
                    report = sts2.build(selected.source_path, output_path,
                                        sdk=sts2_sdk or backend_runtime,
                                        authorized=acknowledge_licenses, progress=progress)
                except (OSError, RuntimeError) as exc:
                    raise ConversionError(str(exc)) from exc
            launcher_path = output_path / "launch.sh"
            warnings = tuple(report.get("limitations", []))
            game_name = inspection.game_name
            engine_version = inspection.engine_version
        elif inspection.backend == "renframe":
            with prepare_source(path) as prepared:
                prepared_inspection = _inspect_prepared(prepared.root)
                if prepared_inspection.backend != "renframe":
                    raise ConversionError("Ren'Py source disappeared after extraction.")
                result = build_renpy_game(
                    prepared_inspection.source_path,
                    output=output_path,
                    runtime=renpy_runtime,
                    force=force,
                    allow_version_mismatch=allow_renpy_version_mismatch,
                    progress=progress,
                )
                launcher_path = result.launcher_path
                warnings = tuple(result.warnings)
                game_name = result.display_name or result.game_name
                engine_version = result.source_version
        else:
            def backend_stage(value: float, message: str) -> None:
                stage(0.20 + (0.62 * max(0.0, min(1.0, value))), message)

            result = build_rpgm_game(
                path,
                output=output_path,
                runtime=backend_runtime,
                runtime_version=runtime_version,
                force=force,
                progress=progress,
                stage_progress=backend_stage,
            )
            launcher_path = result.launcher_path
            warnings = tuple(result.warnings)
            game_name = result.game_name
            engine_version = result.engine_version

        stage(0.82, "Game build complete")
        if archive:
            stage(0.88, "Creating transfer archive")
            archive_path = create_tar_gz(output_path, force=force)
        else:
            archive_path = None
        stage(1.0, "Complete")
    except (
        RenFrameBuildError,
        RPGMFrameBuildError,
        PackagingError,
        SourceError,
    ) as exc:
        raise ConversionError(str(exc)) from exc

    return UnifiedBuildResult(
        source_path=path,
        output_path=output_path,
        launcher_path=launcher_path,
        archive_path=archive_path,
        backend=inspection.backend,
        engine=inspection.engine,
        engine_version=engine_version,
        game_name=game_name,
        warnings=warnings,
    )
