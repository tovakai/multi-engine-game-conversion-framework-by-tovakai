"""Atomic packaging shared by native data-driven engine backends."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import shlex
import shutil
import tempfile

from renframe.elf import read_elf_architecture
from renframe.source_safety import validate_copy_tree
from rpgmframe.launchers import _FRAME_ENV_PREAMBLE
from megcfbt.steam_context import steam_app_id_for_source, write_steam_app_id
from megcfbt.frame_runtime import install_steam_graphics_guard


class NativeBuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class NativeBuildResult:
    output_path: Path
    launcher_path: Path
    game_name: str
    engine_version: str | None
    warnings: tuple[str, ...] = ()


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
                 progress=None, steam_app_id: str | None = None) -> NativeBuildResult:
    source, output = source.resolve(), output.expanduser().resolve()
    if output == source or output in source.parents or source in output.parents:
        raise NativeBuildError('Output must be separate from the source directory.')
    if output.exists() and not force:
        raise NativeBuildError(f'Output already exists: {output}. Pass --force to replace it.')
    if runtime is None:
        raise NativeBuildError(f'{engine} requires a Linux ARM64 runtime bundle containing {executable}; select it with --backend-runtime.')
    try:
        validate_copy_tree(source)
        runtime_root = validate_runtime(Path(runtime), executable)
    except (OSError, ValueError) as exc:
        raise NativeBuildError(str(exc)) from exc
    if output == runtime_root or output in runtime_root.parents or runtime_root in output.parents:
        raise NativeBuildError('Output must be separate from the runtime directory.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f'.{output.name}-', dir=output.parent) as temporary:
        stage = Path(temporary) / 'package'
        stage.mkdir()
        if progress:
            progress(f'Copying {engine} runtime and game data')
        shutil.copytree(runtime_root, stage / 'runtime', symlinks=False)
        try:
            install_steam_graphics_guard(stage)
        except ValueError as exc:
            raise NativeBuildError(str(exc)) from exc
        prepare_game(stage / 'game')
        app_id = steam_app_id or steam_app_id_for_source(source)
        if app_id:
            write_steam_app_id(app_id, stage, stage/'runtime', stage/'game')
        binary = stage / 'runtime' / executable
        binary.chmod(binary.stat().st_mode | 0o111)
        command = ' '.join(shlex.quote(arg) for arg in arguments)
        launcher = stage / 'launch.sh'
        launcher.write_text(
            _FRAME_ENV_PREAMBLE +
            'cd "$ROOT/game"\n'
            'export LD_LIBRARY_PATH="$ROOT/runtime${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"\n'
            'export LUA_CPATH="$ROOT/runtime/?.so;${LUA_CPATH:-;;}"\n'
            f'chmod +x "$ROOT/runtime/{executable}"\n'
            f'exec "$ROOT/runtime/{executable}" {command} "$@"\n',
            encoding='utf-8', newline='\n')
        launcher.chmod(0o755)
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
    return NativeBuildResult(output, output / 'launch.sh', game_name, engine_version, warnings)
