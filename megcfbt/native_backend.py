"""Atomic packaging shared by native data-driven engine backends."""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from pathlib import Path
import json
import shlex
import shutil
import tempfile
import uuid

from renframe.elf import read_elf_architecture
from renframe.source_safety import validate_copy_tree
from rpgmframe.launchers import _FRAME_ENV_PREAMBLE
from megcfbt.steam_context import steam_app_id_for_source, write_steam_app_id
from megcfbt.frame_runtime import install_steam_graphics_guard


class NativeBuildError(RuntimeError):
    pass


@contextmanager
def _publication_stage(output: Path):
    # Windows TemporaryDirectory applies a private DACL. Moving its children
    # retains that DACL and can make published packages inaccessible to ordinary
    # tools. Create the package beside the output with inherited permissions.
    stage = output.parent / f'.{output.name}-stage-{uuid.uuid4().hex}'
    stage.mkdir()
    try:
        yield stage
    finally:
        if stage.exists():
            shutil.rmtree(stage)


@dataclass(frozen=True)
class NativeBuildResult:
    output_path: Path
    launcher_path: Path
    game_name: str
    engine_version: str | None
    warnings: tuple[str, ...] = ()
    runtime_version: str | None = None


def validate_runtime(root: Path, executable: str) -> Path:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise NativeBuildError(f"Select a runtime directory containing {executable}.")
    validate_copy_tree(root)
    binary = root / executable
    if read_elf_architecture(binary) != 'aarch64':
        raise NativeBuildError(f"Runtime {binary} must be a Linux ARM64 ELF executable.")
    for library in root.rglob('*.so*'):
        architecture = read_elf_architecture(library)
        if architecture is not None and architecture != 'aarch64':
            raise NativeBuildError(f"Runtime contains an incompatible native library: {library}")
    return root


def build_native(source: Path, *, output: Path, runtime: Path | None,
                 executable: str, engine: str, game_name: str,
                 engine_version: str | None, prepare_game, arguments: list[str],
                 warnings: tuple[str, ...] = (), force: bool = False,
                 progress=None, steam_app_id: str | None = None,
                 runtime_file_arguments: tuple[tuple[str,str], ...] = (),
                 prepare_runtime=None, launcher_environment: str = '',
                 runtime_version: str | None = None, game_version: str | None = None,
                 compatibility_profile: str | None = None) -> NativeBuildResult:
    source, output = source.resolve(), output.expanduser().resolve()
    if output == source or output in source.parents or source in output.parents:
        raise NativeBuildError('Output must be separate from the source directory.')
    if output.exists() and not force:
        raise NativeBuildError(f'Output already exists: {output}. Pass --force to replace it.')
    if runtime is None:
        raise NativeBuildError(f'{engine} requires a Linux ARM64 runtime bundle containing {executable}; select it with --backend-runtime.')
    try:
        from megcfbt.steam_context import verified_source_identity
        app_id = steam_app_id or steam_app_id_for_source(source)
        steam_identity = verified_source_identity(source, app_id)
        validate_copy_tree(source)
        runtime_root = validate_runtime(Path(runtime), executable)
        if runtime_version is None:
            try:
                capabilities = json.loads((runtime_root / 'engine-capabilities.json').read_text(encoding='utf-8'))
                runtime_version = capabilities.get('engine_version')
            except (OSError, ValueError, AttributeError):
                pass
    except (OSError, ValueError) as exc:
        raise NativeBuildError(str(exc)) from exc
    if output == runtime_root or output in runtime_root.parents or runtime_root in output.parents:
        raise NativeBuildError('Output must be separate from the runtime directory.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f'.{output.name}-', dir=output.parent) as temporary, _publication_stage(output) as stage:
        if progress:
            progress(f'Copying {engine} runtime and game data')
        if prepare_runtime is None:
            shutil.copytree(runtime_root, stage / 'runtime', symlinks=False)
        else:
            prepare_runtime(runtime_root, stage / 'runtime')
        try:
            install_steam_graphics_guard(stage)
        except ValueError as exc:
            raise NativeBuildError(str(exc)) from exc
        prepare_game(stage / 'game')
        if app_id:
            write_steam_app_id(app_id, stage, stage/'runtime', stage/'game')
        binary = stage / 'runtime' / executable
        binary.chmod(binary.stat().st_mode | 0o111)
        command = ' '.join(shlex.quote(arg) for arg in arguments)
        for flag,name in runtime_file_arguments:
            if Path(name).name!=name or name in {'.','..'} or not (stage/'runtime'/name).is_file():
                raise NativeBuildError(f'Invalid or missing runtime argument file: {name}')
            command += ' '+shlex.quote(flag)+' "$ROOT/runtime"/'+shlex.quote(name)
        launcher = stage / 'launch.sh'
        launcher.write_text(
            _FRAME_ENV_PREAMBLE +
            'cd "$ROOT/game"\n'
            'export LD_LIBRARY_PATH="$ROOT/runtime:/opt/steamvr/bin/linuxarm64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"\n'
            'export LUA_CPATH="$ROOT/runtime/?.so;${LUA_CPATH:-;;}"\n'
            + launcher_environment +
            f'chmod +x "$ROOT/runtime/{executable}"\n'
            f'exec "$ROOT/runtime/{executable}" {command} "$@"\n',
            encoding='utf-8', newline='\n')
        launcher.chmod(0o755)
        from megcfbt.frame_package import write_frame_metadata
        metadata_path = write_frame_metadata(stage, name=game_name, launcher_path=launcher,
                             engine=engine, engine_version=engine_version,
                             backend={'CelesteFrame': 'celesteframe', 'MonoFrame': 'monoframe',
                                      'GameMaker': 'gamemakerframe', 'LÖVE': 'loveframe',
                                      'AGS': 'agsframe'}.get(engine),
                             runtime_engine_version=runtime_version, game_version=game_version,
                             compatibility_profile=compatibility_profile,
                             steam_identity=steam_identity,
                             steam_runtime_appid=app_id)
        from megcfbt.asset_dedup import record_origins
        if progress and compatibility_profile:
            progress('Recording final asset provenance for optional Steam deduplication')
        record_origins(stage, source, json.loads(metadata_path.read_text(encoding='utf-8')))
        (stage / 'native-runtime.json').write_text(json.dumps({
            'engine': engine, 'source_engine_version': engine_version,
            'architecture': 'aarch64', 'executable': executable,
            'steam_app_id': app_id,
            'warnings': list(warnings)}, indent=2) + '\n', encoding='utf-8')
        backup = None
        if output.exists():
            backup = Path(temporary) / 'previous-output'
            output.rename(backup)
        try:
            stage.rename(output)
        except OSError:
            if backup is not None:
                backup.rename(output)
            raise
    return NativeBuildResult(output, output / 'launch.sh', game_name, engine_version, warnings, runtime_version)
