"""Detect a game's engine and route conversion to the correct backend."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

from renframe.runtime import experimental_arm64_fallback, requires_pre_sdkarm_override
from renframe.ddlc import original_ddlc_candidate
from renframe.builder import BuildError as RenFrameBuildError
from renframe.builder import build_game as build_renpy_game
from renframe.inspect_service import inspect_game as inspect_renpy_game
from renframe.models import Compatibility as RenpyCompatibility
from rpgmframe.builder import BuildError as RPGMFrameBuildError
from rpgmframe.builder import build_game as build_rpgm_game
from rpgmframe.detector import inspect_game as inspect_rpgm_game
from rpgmframe.godot_runtime_download import downloadable
from rpgmframe.godot_custom_runtime import (
    automatic_recipe_for,
    host_can_build_automatic_runtime,
)
from megcfbt.artwork import complete_frame_artwork
from megcfbt.frame_package import (
    FramePackageError,
    create_frame_zip,
    embed_steam_cover,
    write_frame_metadata,
    load_frame_metadata,
    default_zip_path,
)
from rpgmframe.runtime import DEFAULT_NWJS_VERSION
from rpgmframe.source import SourceError, prepare_source, PreparedSource

from megcfbt.models import UnifiedBuildResult, UnifiedInspection
from megcfbt import sts2
from renframe.live2d import required as requires_live2d
from renframe.utils import sanitize_fs_name
from renframe.detector import looks_like_renpy_game
from megcfbt.native_backend import NativeBuildError
from megcfbt.steam_context import steam_app_id_for_source
from megcfbt.native_runtime import automatic_runtime_available


def automatic_native_runtime_available(inspection: UnifiedInspection) -> bool:
    if inspection.backend == 'celesteframe':
        from celesteframe.runtime import automatic_runtime_available as celeste_available
        return inspection.buildable and celeste_available()
    if inspection.backend == 'unityframe':
        return inspection.buildable
    if inspection.backend=='monoframe':
        from monoframe.runtime import automatic_runtime_available as mono_available
        return inspection.buildable and mono_available()
    engine={'gamemakerframe':'gamemaker','loveframe':'love','agsframe':'ags'}.get(inspection.backend)
    if inspection.engine=='rpg2k':engine='easyrpg'
    if engine is None or not inspection.buildable:return False
    if engine=='love' and inspection.engine_version and not inspection.engine_version.startswith('11.'):return False
    return automatic_runtime_available(engine)


def _native_backends():
    from gamemakerframe import backend as gamemaker
    from loveframe import backend as love
    from agsframe import backend as ags
    from constructframe import backend as construct
    from monoframe import backend as mono
    from unityframe import backend as unity
    from celesteframe import backend as celeste
    return {'gamemakerframe': gamemaker, 'loveframe': love,
            'agsframe': ags, 'constructframe': construct, 'monoframe':mono, 'unityframe':unity,
            'celesteframe': celeste}


class ConversionError(RuntimeError):
    """Raised when the umbrella framework cannot inspect or convert a source."""


def source_base_name(source: Path | str) -> str:
    path = Path(source).expanduser()
    return path.stem if path.suffix.lower() == ".zip" else path.name


def output_path_for_source(
    source: Path | str,
    output_dir: Path | str,
    game_name: str | None = None,
) -> Path:
    fallback = source_base_name(source)
    base = sanitize_fs_name(game_name or fallback, fallback=fallback)
    return Path(output_dir).expanduser() / f"{base}-frame"


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


def _renpy_root_candidates(root: Path, *, max_depth: int = 8) -> list[Path]:
    """Find shallow Ren'Py exports, including macOS Resources and mixed wrappers."""
    level = [root]
    visited = 0
    skip = {"game", "renpy", "lib", ".git", "__macosx", "node_modules", "steam_settings"}
    for _ in range(max_depth + 1):
        matches, children = [], []
        for candidate in level:
            visited += 1
            if visited > 4096:
                return []
            if looks_like_renpy_game(candidate):
                matches.append(candidate)
                continue
            try:
                children.extend(path for path in candidate.iterdir() if path.is_dir()
                                and not path.is_symlink()
                                and not getattr(path, "is_junction", lambda: False)()
                                and path.name.casefold() not in skip)
            except OSError:
                continue
        if matches:
            return matches
        level = children
    return []


def _renpy_summary(root: Path) -> UnifiedInspection | None:
    from renframe.profiles import detect_profile, detect_legacy_version
    profile = detect_profile(root)
    if profile is not None:
        return UnifiedInspection(
            source_path=root, backend="renframe", engine="renpy", engine_label="Ren'Py",
            engine_version=detect_legacy_version(root), game_name=root.name,
            compatibility="NEEDS_TESTING", confidence="high",
            runtime_kind=f"Katawa Shoujo {profile.variant} compatibility migration to Ren'Py {profile.profile.target_version}",
            buildable=True, warnings=("Experimental legacy profile; verify gameplay and HD UI.",),
            evidence=(f"compatibility profile: {profile.profile.id} ({profile.variant})",),
        )
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

    fallback = experimental_arm64_fallback(result.renpy_version, result.generation, inspection=result)
    ddlc_candidate = original_ddlc_candidate(result)
    from renframe.prerelease import prerelease_853_candidate
    prerelease = prerelease_853_candidate(root)
    if prerelease:
        runtime_kind = "experimental Ren'Py 8.4/8.5 nightly to matched 8.5.3 full-engine migration"
    elif ddlc_candidate:
        runtime_kind = "experimental original DDLC 1.1.1 Ren'Py 7.5.3 full-engine migration (requires user approval; menu/launch tested on Frame; story unverified)"
    elif fallback:
        runtime_kind = (
            f"experimental Ren'Py {fallback} Python 2 ARM64 full-engine migration "
            "(requires user approval)"
        )
    elif requires_pre_sdkarm_override(result.renpy_version, result.generation):
        runtime_kind = "manual compatible ARM64 runtime required (no matching sdkarm)"
    elif result.renpy_version:
        runtime_kind = f"official Ren'Py {result.renpy_version} sdkarm platform (automatic)"
    else:
        runtime_kind = "Ren'Py ARM64 runtime (manual override required)"

    return UnifiedInspection(
        source_path=root,
        backend="renframe",
        engine="renpy",
        engine_label="Ren'Py",
        engine_version=result.renpy_version,
        game_name=result.game_name,
        compatibility=compatibility,
        confidence=(result.version_hints[0].confidence if result.version_hints else "low"),
        runtime_kind=runtime_kind,
        buildable=buildable,
        warnings=warnings,
        evidence=evidence,
        renpy_generation=result.generation,
        renpy_ddlc_753_candidate=ddlc_candidate,
        renpy_legacy_arm64_candidate=bool(fallback),
        renpy_prerelease_853_candidate=prerelease,
        renpy_live2d_required=requires_live2d(root),
    )


def _rpgm_summary(root: Path) -> UnifiedInspection | None:
    result = inspect_rpgm_game(root)
    if not result.recognized:
        return None

    if result.engine.value == "godot":
        label = "Godot"
    elif result.engine.value in {"construct2", "construct3"}:
        label = "Construct " + result.engine.value[-1]
    elif result.engine.value == "rpg2k":
        label = "RPG Maker 2000/2003"
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

    renpy_roots = _renpy_root_candidates(root)
    if len(renpy_roots) > 1:
        return UnifiedInspection(source_path=root, backend=None, engine="renpy",
                                 engine_label="Ren'Py", engine_version=None, game_name=root.name,
                                 compatibility="ambiguous", confidence="high", runtime_kind=None,
                                 buildable=False, evidence=tuple(str(p.relative_to(root)) for p in renpy_roots),
                                 warnings=("Multiple Ren'Py game roots found; select the intended game directory.",))
    for candidate in renpy_roots:
        summary = _renpy_summary(candidate)
        if summary is not None:
            return summary

    for candidate in candidates:
        for backend in _native_backends().values():
            summary = backend.inspect_game(candidate)
            if summary is not None:
                return summary
        summary = _rpgm_summary(candidate)
        if summary is not None:
            return summary

    # Native exports may have sibling manuals or Steam metadata alongside
    # their platform directory, so a single-directory wrapper chain is not
    # sufficient. Only inspect shallow exports and require one candidate.
    level = [root]
    skip = {'game','lib','renpy','assets','audio','data','graphics','www','node_modules','.git'}
    for _ in range(3):
        children = []
        for parent in level:
            try:
                children.extend(p for p in parent.iterdir() if p.is_dir() and not p.is_symlink()
                                and not getattr(p,'is_junction',lambda:False)()
                                and p.name.casefold() not in skip)
            except OSError:
                continue
        if len(children) > 4096:
            break
        matches = [result for candidate in children for backend in _native_backends().values()
                   if (result := backend.inspect_game(candidate)) is not None]
        if len(matches) == 1:
            return matches[0]
        if matches:
            return UnifiedInspection(root,None,'unknown','Multiple native engine exports',None,root.name,
                                     'ambiguous','high',None,False,
                                     ('Select one native game export directory.',),
                                     tuple(str(result.source_path.relative_to(root)) for result in matches))
        level = children

    for candidate in candidates:
        from megcfbt.unity import inspect_game as inspect_unity_game
        unity_summary = inspect_unity_game(candidate)
        if unity_summary is not None:
            return unity_summary
        names = {p.name.casefold(): p for p in candidate.iterdir() if p.is_file()}
        if "data.wolf" in names:
            return UnifiedInspection(source_path=root, backend=None, engine="wolf",
                                     engine_label="WOLF RPG Editor", engine_version=None, game_name=candidate.name,
                                     compatibility="unsupported", confidence="high", runtime_kind=None, buildable=False,
                                     evidence=("Data.wolf",),
                                     warnings=("WOLF RPG Editor is not supported by the native ARM64 backends; its data is incompatible with RPG Maker/EasyRPG.",))
        if any((app/'Contents/MacOS/librenpython.dylib').is_file() for app in candidate.glob('*.app')):
            return UnifiedInspection(root,'renframe','renpy',"Ren'Py",None,candidate.name,
                                     'incomplete_export','high',None,False,
                                     ('Ren\'Py macOS runtime found, but complete game/ and renpy/ resources are missing. Restore the original distribution before converting.',),
                                     ('macOS librenpython.dylib',))

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
    """Whether a supported recipe can be downloaded or built on this host."""
    if (
        inspection.backend != "rpgmframe"
        or inspection.engine != "godot"
        or inspection.runtime_kind != "godot-custom"
    ):
        return False

    godotsteam = any("godotsteam" in item.casefold() for item in inspection.evidence)
    modules = [item.casefold().split(': built-in module ', 1)[1].strip()
               for item in inspection.evidence if ': built-in module ' in item.casefold()]
    if any(module != 'godotsteam' for module in modules):
        return False
    recipe = automatic_recipe_for(
        inspection.engine_version,
        custom_build=True,
        godotsteam=godotsteam,
    )
    return recipe is not None and (downloadable(recipe) or host_can_build_automatic_runtime())


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
                renpy_generation=result.renpy_generation,
                renpy_ddlc_753_candidate=result.renpy_ddlc_753_candidate,
                renpy_legacy_arm64_candidate=result.renpy_legacy_arm64_candidate,
                renpy_prerelease_853_candidate=result.renpy_prerelease_853_candidate,
                renpy_live2d_required=result.renpy_live2d_required,
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
    renpy_legacy_arm64_fallback: bool = False,
    renpy_ddlc_753_migration: bool = False,
    renpy_prerelease_853_migration: bool = False,
    dry_run: bool = False,
    steam_cover: Path | str | None = None,
    steamgriddb_game_id: int | None = None,
    progress: Callable[[str], None] | None = None,
    stage_progress: Callable[[float, str], None] | None = None,
    download_progress: Callable[[int, int | None], None] | None = None,
    sts2_sdk: Path | str | None = None,
    celeste_sdk: Path | str | None = None,
    until_then_sdk: Path | str | None = None,
    sts2_frame=None,
    sts2_retry: bool = False,
    sts2_handoff: bool | None = None,
    _prepared_source: PreparedSource | None = None,
) -> UnifiedBuildResult:
    options = locals().copy()
    options.pop('source')
    def stage(value: float, message: str) -> None:
        if stage_progress:
            stage_progress(max(0.0, min(1.0, value)), message)

    path = Path(source).expanduser().resolve()
    if output is not None:
        output_path = Path(output).expanduser().resolve()
        if output_path == path or output_path in path.parents or (path.is_dir() and path in output_path.parents):
            raise ConversionError("Output must be separate from the original source, including source archives.")
        if archive and default_zip_path(output_path).resolve() == path:
            raise ConversionError('Generated ZIP would replace the original source archive; choose another output name.')
    stage(0.03, "Inspecting source")
    if path.is_file() and path.suffix.casefold() == '.zip' and _prepared_source is None:
        try:
            with prepare_source(path, progress=progress) as prepared:
                options['_prepared_source'] = prepared
                return build_source(path, **options)
        except SourceError as exc:
            raise ConversionError(str(exc)) from exc
    inspection = _inspect_prepared(_prepared_source.root) if _prepared_source else inspect_source(path)
    if renpy_ddlc_753_migration and (
        inspection.backend != "renframe" or not inspection.renpy_ddlc_753_candidate
    ):
        raise ConversionError("Experimental DDLC 7.5.3 migration requires original DDLC 1.1.1 / Ren'Py 6.99.12 layout evidence.")
    stage(0.12, f"Detected {inspection.engine_label}")
    custom_godot_override = bool(
        inspection.backend == "rpgmframe"
        and inspection.engine == "godot"
        and inspection.runtime_kind in {"godot-custom", "godot-encrypted", "godot-native-extensions"}
        and backend_runtime is not None
    )
    custom_godot_auto = automatic_custom_godot_runtime_available(inspection)
    handoff = sts2_handoff if sts2_handoff is not None else sts2.platform.system() == 'Windows'
    sts2_ready = bool(inspection.backend == 'sts2' and inspection.compatibility == 'needs_testing'
                      and (handoff or sts2_frame is not None or sts2.available(sts2_sdk or backend_runtime)))
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
            + (" " + " ".join(inspection.warnings) if inspection.warnings else "")
        )

    output_path = (
        Path(output).expanduser().resolve()
        if output is not None
        else output_path_for_source(path, path.parent, inspection.game_name)
    )
    target_platform = 'windows-arm64-proton' if inspection.backend == 'unityframe' else 'linux-aarch64'
    if archive and default_zip_path(output_path, target_platform=target_platform).resolve() == path:
        raise ConversionError('Generated ZIP would replace the original source archive; choose another output name.')
    if dry_run and inspection.backend != "renframe":
        raise ConversionError("--dry-run currently supports Ren'Py builds only.")

    try:
        stage(0.20, "Building ARM64 package")
        if inspection.backend == "sts2":
            if handoff and sts2_frame is None:
                with prepare_source(_prepared_source.root if _prepared_source else path) as prepared:
                    selected = _inspect_prepared(prepared.root)
                    try:
                        report = sts2.prepare_transfer(selected.source_path, output_path,
                            sdk=sts2_sdk or backend_runtime, archive=archive, progress=progress, stage=stage)
                    except (OSError, ValueError, RuntimeError) as exc:
                        raise ConversionError(str(exc)) from exc
                return UnifiedBuildResult(source_path=path, output_path=output_path,
                    launcher_path=output_path/'install.sh', archive_path=Path(report['archive']) if report.get('archive') else None,
                    backend='sts2', engine='godot', engine_version=inspection.engine_version,
                    game_name=inspection.game_name, warnings=tuple(report['limitations']), requires_frame_install=True)
            if sts2_frame is not None:
                from megcfbt.sts2_remote import RemoteBuild, RemoteError
                try:
                    with prepare_source(_prepared_source.root if _prepared_source else path) as prepared:
                        selected=_inspect_prepared(prepared.root)
                        service=RemoteBuild(sts2_frame,progress,stage)
                        retry=service.last_retry_job(output_path,selected.source_path) if sts2_retry else None
                        report=service.build(selected.source_path,output_path,archive=archive,resume_job=retry)
                    return UnifiedBuildResult(source_path=path,output_path=output_path,
                        launcher_path=None,archive_path=Path(report['local_archive']) if report.get('local_archive') else None,
                        backend='sts2',engine='godot',engine_version=inspection.engine_version,game_name=inspection.game_name,
                        warnings=('STS2 remote conversion is experimental; Steam launch and gameplay acceptance are required.',),
                        remote_output=report['output'],steam_launch_command=report['launch_command'],remote_job=report['job'])
                except (RemoteError,OSError,ValueError) as e: raise ConversionError(str(e)) from e
            with prepare_source(_prepared_source.root if _prepared_source else path) as prepared:
                selected = _inspect_prepared(prepared.root)
                if selected.backend != "sts2":
                    raise ConversionError("STS2 source disappeared after extraction")
                try:
                    report = sts2.build(selected.source_path, output_path,
                                        sdk=sts2_sdk or backend_runtime,
                                        progress=progress)
                except (OSError, RuntimeError) as exc:
                    raise ConversionError(str(exc)) from exc
            launcher_path = output_path / "launch.sh"
            warnings = tuple(report.get("limitations", []))
            game_name = inspection.game_name
            engine_version = inspection.engine_version
            return UnifiedBuildResult(source_path=path, output_path=output_path,
                launcher_path=launcher_path,
                archive_path=Path(report['archive']) if report.get('archive') else None,
                backend='sts2', engine='godot', engine_version=engine_version,
                game_name=game_name, warnings=warnings)
        elif inspection.backend == "renframe":
            with prepare_source(_prepared_source.root if _prepared_source else path) as prepared:
                prepared_inspection = _inspect_prepared(prepared.root)
                if prepared_inspection.backend != "renframe":
                    raise ConversionError("Ren'Py source disappeared after extraction.")
                result = build_renpy_game(
                    prepared_inspection.source_path,
                    output=output_path,
                    runtime=renpy_runtime,
                    force=force,
                    allow_version_mismatch=allow_renpy_version_mismatch,
                    legacy_arm64_fallback=renpy_legacy_arm64_fallback,
                    ddlc_753_migration=renpy_ddlc_753_migration,
                    prerelease_853_migration=renpy_prerelease_853_migration,
                    dry_run=dry_run,
                    progress=progress,
                )
                launcher_path = result.launcher_path
                warnings = tuple(result.warnings)
                game_name = result.display_name or result.game_name
                engine_version = result.source_version
                if dry_run:
                    return UnifiedBuildResult(
                        source_path=path, output_path=output_path,
                        launcher_path=launcher_path, archive_path=None,
                        backend=inspection.backend, engine=inspection.engine,
                        engine_version=engine_version, game_name=game_name,
                        warnings=warnings,
                    )
        elif inspection.backend in _native_backends():
            with prepare_source(_prepared_source.root if _prepared_source else path) as prepared:
                selected = _inspect_prepared(prepared.root)
                try:
                    result = _native_backends()[inspection.backend].build_game(
                        selected.source_path, output=output_path, runtime=backend_runtime,
                        runtime_version=(None if runtime_version == DEFAULT_NWJS_VERSION else runtime_version)
                            if inspection.backend in {'unityframe', 'celesteframe'} else runtime_version,
                        force=force, progress=progress,
                        download_progress=download_progress,
                        steam_app_id=steam_app_id_for_source(_prepared_source.root if _prepared_source else path),
                        **({'fmod_sdk': celeste_sdk} if inspection.backend == 'celesteframe' else {}),
                    )
                except NativeBuildError as exc:
                    raise ConversionError(str(exc)) from exc
            launcher_path = result.launcher_path
            warnings = tuple(result.warnings)
            game_name = result.game_name
            engine_version = result.engine_version
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
                download_progress=download_progress,
                **({'fmod_sdk': until_then_sdk} if inspection.runtime_kind == 'godot-until-then' else {}),
                **({'prepared_source': _prepared_source} if _prepared_source else {}),
            )
            launcher_path = result.launcher_path
            warnings = tuple(result.warnings)
            game_name = result.game_name
            engine_version = result.engine_version

        stage(0.82, "Game build complete")
        existing_metadata = (load_frame_metadata(output_path)
                             if (output_path / '.megcfbt/package.json').is_file() else {})
        write_frame_metadata(
            output_path,
            name=game_name or inspection.game_name or source_base_name(path),
            launcher_path=launcher_path,
            engine=inspection.engine,
            backend=inspection.backend,
            steam_identity=existing_metadata.get('steam_identity'),
            steam_runtime_appid=existing_metadata.get('steam_runtime_appid'),
            conversion=existing_metadata.get('conversion'),
            engine_version=engine_version,
            game_version='1.4.0.0' if inspection.backend == 'celesteframe' else existing_metadata.get('game_version'),
            target_platform=target_platform,
            **({'runtime_engine_version': '6000.0.61f1', 'compatibility_profile': 'hollow-knight-steam-unity-6000.0.61f1-managed-input-v1'}
               if inspection.backend == 'unityframe' else
               {'runtime_engine_version': 'FNA 23.10 / .NET 8.0.31', 'compatibility_profile': 'celeste-steam-xna-1.4.0.0'}
               if inspection.backend == 'celesteframe' else
               {"runtime_engine_version": result.runtime_version,
                "compatibility_profile": "experimental-ddlc-111-renpy-753"}
               if renpy_ddlc_753_migration else
               {"runtime_engine_version": result.runtime_version,
                "compatibility_profile": "experimental-renpy-legacy-750"}
               if renpy_legacy_arm64_fallback else
               {"runtime_engine_version": result.runtime_version,
                "compatibility_profile": "experimental-renpy-prerelease-853"}
               if renpy_prerelease_853_migration else
               {"runtime_engine_version": result.runtime_version,
                "compatibility_profile": "katawa-shoujo-legacy"}
               if inspection.runtime_kind and inspection.runtime_kind.startswith("Katawa Shoujo") else
               {'runtime_engine_version': getattr(result, 'runtime_version', None) or existing_metadata.get('runtime_engine_version'),
                'compatibility_profile': existing_metadata.get('compatibility_profile')}),
        )
        if steam_cover is not None:
            embed_steam_cover(output_path, steam_cover)
        if not renpy_ddlc_753_migration:
            complete_frame_artwork(
                output_path,
                game_name=game_name or inspection.game_name or source_base_name(path),
                progress=progress,
                steamgriddb_game_id=steamgriddb_game_id,
            )
        if archive:
            stage(0.88, "Creating Frame-ready ZIP")
            archive_path = create_frame_zip(
                output_path,
                launcher_path=launcher_path,
                force=force,
                progress=progress,
            )
        else:
            archive_path = None
        stage(1.0, "Complete")
    except (
        RenFrameBuildError,
        RPGMFrameBuildError,
        FramePackageError,
        SourceError,
        NativeBuildError,
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
        target_platform=target_platform,
    )
