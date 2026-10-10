"""Build Linux ARM64 game packages using engine-specific runtimes."""

from __future__ import annotations

import json
import re
import shutil
import stat
import unicodedata
import uuid
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from contextlib import nullcontext

from rpgmframe.compat import install_compatibility
from rpgmframe.detector import inspect_game
from rpgmframe.elf import read_elf_architecture
from rpgmframe.launchers import nwjs_launcher_body
from rpgmframe.models import BuildResult, EngineVariant
from rpgmframe.runtime import DEFAULT_NWJS_VERSION, RuntimeManager
from rpgmframe.source import SourceError, prepare_source, PreparedSource


class BuildError(RuntimeError):
    """Raised when an RPGMFrame build cannot proceed safely."""


_IGNORE_NAMES = frozenset({".git", "__pycache__", ".DS_Store"})

# Files installed beside www/ by the stock Windows NW.js export. These are
# replaced by the Linux ARM64 runtime and must not leak into the converted root.
_WINDOWS_RUNTIME_ROOT_NAMES = frozenset(
    {
        "d3dcompiler_47.dll",
        "ffmpeg.dll",
        "icudtl.dat",
        "libegl.dll",
        "libglesv2.dll",
        "locales",
        "natives_blob.bin",
        "node.dll",
        "nw.dll",
        "nw_elf.dll",
        "resources.pak",
        "snapshot_blob.bin",
        "v8_context_snapshot.bin",
        "vk_swiftshader_icd.json",
        "swiftshader",
    }
)
_WINDOWS_RUNTIME_ROOT_SUFFIXES = frozenset({".dll", ".exe", ".pdb"})


def _engine_label(engine: EngineVariant) -> str:
    labels = {
        EngineVariant.MV: "RPG Maker MV",
        EngineVariant.MZ: "RPG Maker MZ",
        EngineVariant.CONSTRUCT_2: "Construct 2",
        EngineVariant.CONSTRUCT_3: "Construct 3",
    }
    return labels.get(engine, engine.value.upper())


def _normalize_path(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def default_output_path(source: Path | str) -> Path:
    source_path = _normalize_path(source)
    name = source_path.stem if source_path.suffix.lower() == ".zip" else source_path.name
    return source_path.parent / f"{name}-frame"


def _paths_overlap(a: Path, b: Path) -> bool:
    return a == b or a in b.parents or b in a.parents


def _ignore_junk(directory: str, contents: list[str]) -> list[str]:
    del directory
    return [name for name in contents if name in _IGNORE_NAMES or name.endswith(".pyc")]


def _package_slug(source: Path) -> str:
    source_name = source.stem if source.suffix.lower() == ".zip" else source.name
    ascii_name = (
        unicodedata.normalize("NFKD", source_name)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    ascii_name = re.sub(r"[^a-z0-9._-]+", "-", ascii_name).strip("-._")
    return f"rpgmframe-{ascii_name or 'game'}"


def _load_package(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildError(f"Could not read package.json: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BuildError(f"package.json is not a JSON object: {path}")
    return value


def _write_package(
    destination: Path,
    source_package: Path | None,
    source_path: Path,
    game_root: Path,
) -> None:
    package = _load_package(source_package)
    if not isinstance(package.get("name"), str) or not package["name"].strip():
        package["name"] = _package_slug(source_path)

    package["main"] = "www/index.html"

    # Bare MZ-style deployments keep package.json next to index.html. RPGMFrame
    # relocates that payload under www/, so package-root asset references need
    # the same prefix. Preserve remote/absolute icon URLs unchanged.
    window = package.get("window")
    if (
        source_package is not None
        and source_package.parent == game_root
        and isinstance(window, dict)
    ):
        icon = window.get("icon")
        if isinstance(icon, str) and icon.strip():
            icon_path = Path(icon)
            if (
                not icon_path.is_absolute()
                and "://" not in icon
                and not icon.replace("\\", "/").startswith("www/")
                and (game_root / icon_path).is_file()
            ):
                window["icon"] = f"www/{icon_path.as_posix()}"

    destination.write_text(
        json.dumps(package, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )


def _launcher_body() -> str:
    return nwjs_launcher_body()


def _write_launcher(root: Path) -> Path:
    launcher = root / "launch.sh"
    launcher.write_text(_launcher_body(), encoding="utf-8", newline="\n")
    launcher.chmod(launcher.stat().st_mode | 0o755)
    return launcher


def _validate_runtime(runtime: Path) -> str:
    nw = runtime / "nw"
    if not nw.is_file():
        raise BuildError(f"NW.js runtime is missing its nw executable: {nw}")

    architecture = read_elf_architecture(nw)
    if architecture is None:
        raise BuildError(f"NW.js nw binary is not a readable ELF executable: {nw}")
    if architecture != "aarch64":
        raise BuildError(
            f"NW.js runtime architecture is {architecture}, not aarch64: {nw}"
        )
    return architecture


def _validate_paths(source: Path, runtime: Path, output: Path) -> None:
    if _paths_overlap(source, output):
        raise BuildError(
            f"Output path must not overlap the source: source={source}, output={output}"
        )
    if _paths_overlap(runtime, output):
        raise BuildError(
            f"Output path must not overlap the runtime: runtime={runtime}, output={output}"
        )


def _is_windows_runtime_baggage(path: Path) -> bool:
    name = path.name.lower()
    return (
        name in _WINDOWS_RUNTIME_ROOT_NAMES
        or re.fullmatch(r"nw_\d+_percent\.pak", name) is not None
        or path.suffix.lower() in _WINDOWS_RUNTIME_ROOT_SUFFIXES
    )


def _copy_root_companions(
    source_root: Path,
    game_root: Path,
    destination: Path,
) -> list[str]:
    """
    Preserve game-owned files beside www/ while dropping the old Windows runtime.

    Many MV games use Node's fs APIs against package-root data instead of only
    browser-relative paths below www/. Copying only www/ silently drops those
    companion resources.
    """
    if game_root.parent != source_root or game_root.name.lower() != "www":
        return []

    copied: list[str] = []
    for entry in source_root.iterdir():
        if entry == game_root or entry.name == "package.json":
            continue
        if entry.name in _IGNORE_NAMES or entry.name.endswith(".pyc"):
            continue
        if _is_windows_runtime_baggage(entry):
            continue

        target = destination / entry.name
        if entry.is_dir():
            shutil.copytree(
                entry,
                target,
                symlinks=True,
                ignore=_ignore_junk,
                ignore_dangling_symlinks=True,
            )
        elif entry.is_file():
            shutil.copy2(entry, target, follow_symlinks=False)
        else:
            continue
        copied.append(entry.name)

    return copied


def _safe_extract_package_nw(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()

    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise BuildError(f"Could not open package.nw: {archive_path}: {exc}") from exc

    with archive:
        for info in archive.infolist():
            target = (destination / info.filename).resolve()
            if target != root and root not in target.parents:
                raise BuildError(
                    f"Refusing unsafe path in package.nw: {info.filename}"
                )
            unix_mode = (info.external_attr >> 16) & 0o177777
            if stat.S_ISLNK(unix_mode):
                raise BuildError(
                    f"Refusing symlink in package.nw: {info.filename}"
                )
        try:
            archive.extractall(destination)
        except OSError as exc:
            raise BuildError(
                f"Could not extract package.nw {archive_path}: {exc}"
            ) from exc


def _copy_archive_root_companions(
    source_root: Path,
    payload_archive: Path,
    destination: Path,
) -> list[str]:
    copied: list[str] = []
    for entry in source_root.iterdir():
        if entry == payload_archive or entry.name == "package.json":
            continue
        if entry.name in _IGNORE_NAMES or entry.name.endswith(".pyc"):
            continue
        if _is_windows_runtime_baggage(entry):
            continue

        target = destination / entry.name
        if entry.is_dir():
            shutil.copytree(
                entry,
                target,
                symlinks=True,
                ignore=_ignore_junk,
                ignore_dangling_symlinks=True,
            )
        elif entry.is_file():
            shutil.copy2(entry, target, follow_symlinks=False)
        else:
            continue
        copied.append(entry.name)
    return copied


def _staging_path(output: Path) -> Path:
    return output.parent / f".{output.name}.tmp-{uuid.uuid4().hex[:8]}"


def _install_staging(staging: Path, output: Path, *, force: bool) -> None:
    if not output.exists():
        staging.rename(output)
        return

    if not force:
        raise BuildError(f"Output already exists: {output}. Pass --force to replace it.")

    backup = output.parent / f".{output.name}.old-{uuid.uuid4().hex[:8]}"
    output.rename(backup)
    try:
        staging.rename(output)
    except Exception:
        backup.rename(output)
        raise
    else:
        shutil.rmtree(backup, ignore_errors=True)


def build_game(
    source: Path | str,
    *,
    runtime: Path | str | None = None,
    runtime_version: str = DEFAULT_NWJS_VERSION,
    runtime_manager: RuntimeManager | None = None,
    output: Path | str | None = None,
    force: bool = False,
    progress: Callable[[str], None] | None = None,
    stage_progress: Callable[[float, str], None] | None = None,
    download_progress: Callable[[int, int | None], None] | None = None,
    prepared_source: PreparedSource | None = None,
) -> BuildResult:
    """Create a self-contained Linux ARM64 package for a supported game."""
    source_path = _normalize_path(source)
    output_path = (
        _normalize_path(output) if output is not None else default_output_path(source_path)
    )

    try:
        prepared_context = nullcontext(prepared_source) if prepared_source else prepare_source(source_path, progress=progress)
        prepared = prepared_context.__enter__()
    except SourceError as exc:
        raise BuildError(str(exc)) from exc

    try:
        if progress and prepared.archive_type:
            progress(f"Extracted {prepared.archive_type.upper()} input: {source_path.name}")

        inspection = inspect_game(prepared.root)
        if not inspection.recognized:
            detail = "; ".join(inspection.warnings) or "unrecognized game"
            raise BuildError(f"Could not identify supported game: {detail}")
        if inspection.engine is EngineVariant.RPG_2K:
            from rpgmframe.easyrpg_backend import build_easyrpg_game
            if runtime is not None:
                raise BuildError("EasyRPG packages use native EasyRPG installed on the target; runtime overrides are unavailable.")
            return build_easyrpg_game(source_path=source_path, output_path=output_path,
                                      inspection=inspection, force=force, progress=progress)
        if inspection.engine is EngineVariant.GODOT:
            from rpgmframe.godot_backend import GodotBuildError, build_godot_game

            try:
                return build_godot_game(
                    source_path=source_path,
                    output_path=output_path,
                    inspection=inspection,
                    runtime=runtime,
                    force=force,
                    archive_type=prepared.archive_type,
                    progress=progress,
                    stage_progress=stage_progress,
                    download_progress=download_progress,
                )
            except GodotBuildError as exc:
                raise BuildError(str(exc)) from exc

        if inspection.engine in {
            EngineVariant.XP,
            EngineVariant.VX,
            EngineVariant.VX_ACE,
        }:
            from rpgmframe.mkxp_backend import MkxpBuildError, build_mkxp_game

            try:
                return build_mkxp_game(
                    source_path=source_path,
                    output_path=output_path,
                    inspection=inspection,
                    runtime=runtime,
                    force=force,
                    archive_type=prepared.archive_type,
                    progress=progress,
                )
            except MkxpBuildError as exc:
                raise BuildError(str(exc)) from exc

        web_engines = {
            EngineVariant.MV,
            EngineVariant.MZ,
            EngineVariant.CONSTRUCT_2,
            EngineVariant.CONSTRUCT_3,
        }
        if inspection.engine not in web_engines:
            raise BuildError(
                f"Building {_engine_label(inspection.engine)} is not enabled yet."
            )
        if inspection.game_root is None:
            raise BuildError(
                f"Detected {_engine_label(inspection.engine)} game has no payload root"
            )
        if (
            inspection.payload_archive is None
            and not (inspection.game_root / "index.html").is_file()
        ):
            raise BuildError(
                f"{_engine_label(inspection.engine)} payload is missing index.html: "
                f"{inspection.game_root / 'index.html'}"
            )

        if runtime is None:
            manager = runtime_manager or RuntimeManager()
            try:
                runtime_path = manager.ensure_nwjs(runtime_version, progress=progress)
            except Exception as exc:
                raise BuildError(f"Could not resolve NW.js runtime: {exc}") from exc
        else:
            runtime_path = _normalize_path(runtime)
            if not runtime_path.is_dir():
                raise BuildError(f"Runtime path is not a directory: {runtime_path}")
            if progress:
                progress(f"Using supplied NW.js runtime: {runtime_path}")

        architecture = _validate_runtime(runtime_path)
        _validate_paths(source_path, runtime_path, output_path)

        if output_path.exists() and not force:
            raise BuildError(
                f"Output already exists: {output_path}. Pass --force to replace it."
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        staging = _staging_path(output_path)
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

        warnings = list(inspection.warnings)
        if prepared.archive_type:
            warnings.insert(0, f"Built directly from {prepared.archive_type.upper()} input")
        warnings.append(
            f"{_engine_label(inspection.engine)} is being run on a modern ARM64 NW.js runtime "
            "rather than its original bundled runtime; test game-specific plugins and media."
        )

        try:
            shutil.copytree(
                runtime_path,
                staging,
                symlinks=True,
                ignore=_ignore_junk,
                ignore_dangling_symlinks=True,
            )

            payload_destination = staging / "www"
            if payload_destination.exists():
                if payload_destination.is_dir():
                    shutil.rmtree(payload_destination)
                else:
                    payload_destination.unlink()

            output_package_json = inspection.package_json
            output_game_root = inspection.game_root
            if inspection.payload_archive is not None:
                _safe_extract_package_nw(
                    inspection.payload_archive,
                    payload_destination,
                )
                if not (payload_destination / "index.html").is_file():
                    raise BuildError(
                        f"{_engine_label(inspection.engine)} package.nw is missing index.html"
                    )
                extracted_package = payload_destination / "package.json"
                output_package_json = (
                    extracted_package if extracted_package.is_file() else None
                )
                output_game_root = payload_destination
                companions = _copy_archive_root_companions(
                    inspection.game_root,
                    inspection.payload_archive,
                    staging,
                )
            else:
                shutil.copytree(
                    inspection.game_root,
                    payload_destination,
                    symlinks=True,
                    ignore=_ignore_junk,
                    ignore_dangling_symlinks=True,
                )

                package_root = (
                    inspection.package_json.parent
                    if inspection.package_json is not None
                    else inspection.game_root
                )
                companions = _copy_root_companions(
                    package_root,
                    inspection.game_root,
                    staging,
                )
            if companions:
                preview = ", ".join(sorted(companions)[:8])
                if len(companions) > 8:
                    preview += f", +{len(companions) - 8} more"
                warnings.append(
                    f"Preserved game-owned package-root companion entries: {preview}"
                )

            if inspection.engine in {EngineVariant.MV, EngineVariant.MZ}:
                warnings.extend(
                    install_compatibility(
                        payload_destination,
                        engine=inspection.engine,
                    )
                )

            _write_package(
                staging / "package.json",
                output_package_json,
                source_path,
                output_game_root,
            )
            if inspection.engine is EngineVariant.CONSTRUCT_3:
                from rpgmframe.construct import install_construct3_compatibility
                warnings.extend(install_construct3_compatibility(payload_destination, staging / "package.json"))

            nw_output = staging / "nw"
            nw_output.chmod(nw_output.stat().st_mode | 0o755)
            crashpad = staging / "chrome_crashpad_handler"
            if crashpad.is_file():
                crashpad.chmod(crashpad.stat().st_mode | 0o755)

            launcher = _write_launcher(staging)
            _install_staging(staging, output_path, force=force)
        except BuildError:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            raise
        except Exception as exc:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            raise BuildError(f"Build failed: {exc}") from exc

        return BuildResult(
            success=True,
            source_path=source_path,
            output_path=output_path,
            runtime_path=runtime_path,
            launcher_path=output_path / launcher.name,
            engine=inspection.engine,
            engine_version=inspection.engine_version,
            game_name=inspection.game_name,
            runtime_architecture=architecture,
            warnings=warnings,
        )
    finally:
        prepared_context.__exit__(None, None, None)
