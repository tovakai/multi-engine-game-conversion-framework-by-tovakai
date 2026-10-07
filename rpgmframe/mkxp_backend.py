"""RPG Maker XP/VX/VX Ace backend using Linux ARM64 mkxp-z."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path

from rpgmframe.elf import read_elf_architecture
from rpgmframe.launchers import mkxp_launcher_body
from rpgmframe.mkxp_runtime import MkxpRuntimeError, MkxpRuntimeManager
from rpgmframe.models import BuildResult, EngineVariant, GameInspection
from rpgmframe.rgss import choose_rgss_ini, rgss_version_for_engine


class MkxpBuildError(RuntimeError):
    """Raised when an RGSS game cannot be packaged around mkxp-z."""


_LEGACY_ENGINES = {EngineVariant.XP, EngineVariant.VX, EngineVariant.VX_ACE}
_IGNORE_NAMES = frozenset({".git", "__pycache__", ".DS_Store"})

_LEGACY_BOOL_KEYS = frozenset(
    {
        "fullscreen",
        "winResizable",
        "anyAltToggleFS",
        "vsync",
        "subImageFix",
        "enableBlitting",
        "fixedAspectRatio",
        "enableReset",
        "enableSettings",
        "allowSymlinks",
        "pathCache",
        "frameSkip",
        "syncToRefreshrate",
    }
)
_LEGACY_INTEGER_KEYS = frozenset(
    {
        "smoothScaling",
        "smoothScalingDown",
        "bitmapSmoothScaling",
        "bitmapSmoothScalingDown",
        "fontHinting",
        "fontHeightReporting",
    }
)
_LEGACY_STRING_KEYS = frozenset(
    {
        "dataPathOrg",
        "dataPathApp",
        "execName",
        "windowTitle",
        "midiSoundFont",
        "iconPath",
    }
)
_LEGACY_LIST_KEYS = frozenset(
    {
        "RTP",
        "fontSub",
        "preloadScript",
        "postloadScript",
        "patches",
        "rubyLoadpath",
        "solidFonts",
    }
)


def _normalize_path(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _paths_overlap(a: Path, b: Path) -> bool:
    return a == b or a in b.parents or b in a.parents


def _ignore_junk(directory: str, contents: list[str]) -> list[str]:
    del directory
    return [name for name in contents if name in _IGNORE_NAMES or name.endswith(".pyc")]


def _staging_path(output: Path) -> Path:
    return output.parent / f".{output.name}.tmp-{uuid.uuid4().hex[:8]}"


def _install_staging(staging: Path, output: Path, *, force: bool) -> None:
    if not output.exists():
        staging.rename(output)
        return
    if not force:
        raise MkxpBuildError(
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


def _validate_runtime(runtime: Path) -> str:
    executable = runtime / "mkxp-z.aarch64"
    if not executable.is_file():
        raise MkxpBuildError(
            f"mkxp-z runtime is missing mkxp-z.aarch64: {executable}"
        )
    architecture = read_elf_architecture(executable)
    if architecture != "aarch64":
        raise MkxpBuildError(
            "mkxp-z runtime architecture is "
            f"{architecture or 'unknown'}, not aarch64: {executable}"
        )
    return architecture


def _write_launcher(root: Path) -> Path:
    launcher = root / "launch.sh"
    launcher.write_text(mkxp_launcher_body(), encoding="utf-8", newline="\n")
    launcher.chmod(launcher.stat().st_mode | 0o755)
    return launcher


def _strip_legacy_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _legacy_bool(value: str) -> bool | None:
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _read_legacy_mkxp_conf(game_root: Path) -> tuple[dict[str, object], Path | None]:
    try:
        candidates = [
            path
            for path in game_root.iterdir()
            if path.is_file() and path.name.casefold() == "mkxp.conf"
        ]
    except OSError:
        return {}, None

    if len(candidates) != 1:
        return {}, None
    path = candidates[0]

    try:
        data = path.read_bytes()
    except OSError:
        return {}, path

    text: str | None = None
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return {}, path

    config: dict[str, object] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")) or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        value = _strip_legacy_value(raw_value)
        if not key:
            continue

        if key in _LEGACY_BOOL_KEYS:
            parsed = _legacy_bool(value)
            if parsed is not None:
                config[key] = parsed
        elif key in _LEGACY_INTEGER_KEYS:
            parsed_bool = _legacy_bool(value)
            if parsed_bool is not None:
                config[key] = int(parsed_bool)
            else:
                try:
                    config[key] = int(value)
                except ValueError:
                    pass
        elif key in _LEGACY_STRING_KEYS:
            config[key] = value
        elif key in _LEGACY_LIST_KEYS:
            items = config.setdefault(key, [])
            if isinstance(items, list) and value:
                items.append(value)

    return config, path


def _looks_like_legacy_mkxp_distribution(game_root: Path, legacy_conf: Path | None) -> bool:
    if legacy_conf is None:
        return False
    try:
        return any(
            path.is_file()
            and path.suffix.casefold() == ".exe"
            and path.stem.casefold().startswith("mkxp")
            for path in game_root.iterdir()
        )
    except OSError:
        return False


def _migration_preloads(
    game_root: Path,
    runtime_root: Path,
    legacy_conf: Path | None,
    configured: object,
) -> list[str]:
    preloads: list[str] = []

    def add(path: str) -> None:
        if path not in preloads:
            preloads.append(path)

    for name in ("ruby_classic_wrap.rb", "mkxp_wrap.rb"):
        if (runtime_root / "scripts" / "preload" / name).is_file():
            add(f"../scripts/preload/{name}")

    configured_items = configured if isinstance(configured, list) else []
    for item in configured_items:
        if isinstance(item, str) and item.strip():
            add(item.strip())

    bundled_win32 = False
    if _looks_like_legacy_mkxp_distribution(game_root, legacy_conf):
        preload_dir = game_root / "preload"
        if preload_dir.is_dir():
            for path in sorted(preload_dir.glob("*.rb"), key=lambda p: p.name.casefold()):
                add(f"preload/{path.name}")
                if path.name.casefold() == "win32_wrap.rb":
                    bundled_win32 = True

    runtime_win32 = runtime_root / "scripts" / "preload" / "win32_wrap.rb"
    if not bundled_win32 and runtime_win32.is_file():
        add("../scripts/preload/win32_wrap.rb")

    return preloads


def _write_mkxp_config(
    destination: Path,
    *,
    game_root: Path,
    runtime_root: Path,
    engine: EngineVariant,
) -> tuple[str | None, tuple[str, ...], bool]:
    ini = choose_rgss_ini(game_root, engine)
    legacy, legacy_path = _read_legacy_mkxp_conf(game_root)

    config: dict[str, object] = {
        "winResizable": True,
        "fixedAspectRatio": True,
    }
    config.update(legacy)

    # Required portable/backend settings win over legacy values.
    config["gameFolder"] = "."
    config["rgssVersion"] = rgss_version_for_engine(engine)
    config["pathCache"] = True

    if "execName" not in config and ini is not None:
        config["execName"] = ini.exec_name

    preloads = _migration_preloads(
        game_root,
        runtime_root,
        legacy_path,
        config.get("preloadScript"),
    )
    if preloads:
        config["preloadScript"] = preloads

    destination.write_text(
        json.dumps(config, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )
    exec_name = config.get("execName")
    return (
        exec_name if isinstance(exec_name, str) else None,
        ini.rtps if ini else (),
        legacy_path is not None,
    )


def _has_wma(root: Path) -> bool:
    for _directory, _dirnames, filenames in os.walk(root):
        if any(name.casefold().endswith(".wma") for name in filenames):
            return True
    return False


def build_mkxp_game(
    *,
    source_path: Path,
    output_path: Path,
    inspection: GameInspection,
    runtime: Path | str | None,
    force: bool,
    archive_type: str | None,
    progress: Callable[[str], None] | None,
) -> BuildResult:
    if inspection.engine not in _LEGACY_ENGINES:
        raise MkxpBuildError(f"Unsupported mkxp-z engine: {inspection.engine.value}")
    if inspection.game_root is None:
        raise MkxpBuildError("Detected RGSS game has no payload root")

    if runtime is None:
        try:
            runtime_path = MkxpRuntimeManager().ensure_mkxpz(progress=progress)
        except MkxpRuntimeError as exc:
            raise MkxpBuildError(str(exc)) from exc
    else:
        runtime_path = _normalize_path(runtime)
        if not runtime_path.is_dir():
            raise MkxpBuildError(f"Runtime path is not a directory: {runtime_path}")
        if progress:
            progress(f"Using supplied mkxp-z runtime: {runtime_path}")

    architecture = _validate_runtime(runtime_path)

    if source_path.is_dir() and _paths_overlap(source_path, output_path):
        raise MkxpBuildError(
            f"Output path must not overlap the source: source={source_path}, "
            f"output={output_path}"
        )
    if _paths_overlap(runtime_path, output_path):
        raise MkxpBuildError(
            f"Output path must not overlap the runtime: runtime={runtime_path}, "
            f"output={output_path}"
        )
    if output_path.exists() and not force:
        raise MkxpBuildError(
            f"Output already exists: {output_path}. Pass --force to replace it."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = _staging_path(output_path)
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)

    warnings = list(inspection.warnings)
    if archive_type:
        warnings.insert(0, f"Built directly from {archive_type.upper()} input")
    warnings.append(
        f"{inspection.engine.value.upper()} is running through mkxp-z on Linux "
        "ARM64 rather than the original Windows RGSS player; test scripts, "
        "fonts, media, saves, and input."
    )

    try:
        shutil.copytree(
            runtime_path,
            staging,
            symlinks=True,
            ignore=_ignore_junk,
            ignore_dangling_symlinks=True,
        )
        game_destination = staging / "game"
        shutil.copytree(
            inspection.game_root,
            game_destination,
            symlinks=True,
            ignore=_ignore_junk,
            ignore_dangling_symlinks=True,
        )

        exec_name, rtps, migrated_legacy_conf = _write_mkxp_config(
            game_destination / "mkxp.json",
            game_root=inspection.game_root,
            runtime_root=staging,
            engine=inspection.engine,
        )
        if exec_name:
            warnings.append(f"Configured mkxp-z executable/archive stem: {exec_name}")
        if migrated_legacy_conf:
            warnings.append(
                "Migrated compatible settings from the game's legacy mkxp.conf"
            )
        if rtps:
            warnings.append(
                "Game declares RPG Maker RTP dependencies "
                f"({', '.join(rtps)}). Bundled assets may be sufficient, but "
                "missing RTP resources will need to be supplied explicitly."
            )
        if _has_wma(inspection.game_root):
            warnings.append(
                "Game contains WMA audio. mkxp-z documents WMA playback as "
                "unsupported; affected tracks may need transcoding."
            )

        executable = staging / "mkxp-z.aarch64"
        executable.chmod(executable.stat().st_mode | 0o755)
        launcher = _write_launcher(staging)
        _install_staging(staging, output_path, force=force)
    except MkxpBuildError:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise
    except Exception as exc:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise MkxpBuildError(f"mkxp-z build failed: {exc}") from exc

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
