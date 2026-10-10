from pathlib import Path
import re
import shutil
import zipfile

from megcfbt.models import UnifiedInspection
from megcfbt.native_backend import NativeBuildError, build_native, validate_runtime
from rpgmframe.source import _safe_extract_zip
from megcfbt.native_runtime import configured_runtime


def find_game(root: Path):
    if (root / 'main.lua').is_file():
        return [root]
    matches = []
    for path in sorted(root.iterdir()):
        if path.is_file() and path.suffix.casefold() in {'.exe', '.love'}:
            try:
                with zipfile.ZipFile(path) as archive:
                    if 'main.lua' in archive.namelist():
                        matches.append(path)
            except (OSError, zipfile.BadZipFile):
                pass
    return matches


def inspect_game(root: Path):
    matches = find_game(root)
    if not matches:
        return None
    source = matches[0]
    conf = ''
    try:
        if source.is_dir() and (source / 'conf.lua').is_file():
            with (source / 'conf.lua').open('rb') as stream:
                conf = stream.read(65536).decode('utf-8', errors='replace')
        elif source.is_file():
            with zipfile.ZipFile(source) as archive:
                if 'conf.lua' in archive.namelist():
                    with archive.open('conf.lua') as stream:
                        conf = stream.read(65536).decode('utf-8', errors='replace')
    except (OSError, zipfile.BadZipFile):
        pass
    version = re.search(r'''\bt\.version\s*=\s*["']([^"']+)["']''', conf)
    return UnifiedInspection(root, 'loveframe', 'love', 'LÖVE', version.group(1) if version else None,
                             root.name, 'needs_testing' if len(matches) == 1 else 'ambiguous', 'high',
                             'love', len(matches) == 1,
                             ('Lua native modules require compatible ARM64 builds in the runtime bundle.',),
                             (f'{source.name}: main.lua',))


def build_game(source: Path, *, output, runtime=None, force=False, progress=None, **kwargs):
    runtime = runtime if runtime is not None else configured_runtime('love')
    inspection = inspect_game(source)
    if inspection is None or not inspection.buildable:
        raise NativeBuildError('No unambiguous LÖVE export found.')
    payload = find_game(source)[0]
    if runtime is not None:
        runtime_root = validate_runtime(Path(runtime), 'love')
        for module in ('luasteam', 'https'):
            if any(p.stem.casefold() == module for p in source.glob('*.dll')):
                if not (runtime_root / (module + '.so')).is_file():
                    raise NativeBuildError(f'This export includes {module}.dll; supply a matching ARM64 {module}.so in the LÖVE runtime bundle.')
    def prepare(destination):
        if payload.is_dir():
            shutil.copytree(payload, destination, symlinks=False)
        else:
            _safe_extract_zip(payload, destination)
        # Windows/macOS modules cannot load in the ARM64 runtime. Keep game
        # assets intact; replace native modules only with supplied equivalents.
        for path in destination.rglob('*'):
            if path.is_file() and path.suffix.casefold() in {'.dll', '.dylib', '.so'}:
                from renframe.elf import read_elf_architecture
                if read_elf_architecture(path) != 'aarch64':
                    replacement = Path(runtime) / path.name if runtime else None
                    if replacement and replacement.is_file():
                        shutil.copy2(replacement, path)
                    elif path.suffix.casefold() == '.so' and '/linux/' in path.as_posix().casefold():
                        raise NativeBuildError(f'ARM64 replacement required for native module {path.relative_to(destination)}.')
    return build_native(source, output=Path(output), runtime=runtime, executable='love', engine='LÖVE',
                        game_name=inspection.game_name, engine_version=inspection.engine_version,
                        prepare_game=prepare, arguments=['.'], warnings=inspection.warnings, force=force, progress=progress,
                        steam_app_id=kwargs.get('steam_app_id'))
