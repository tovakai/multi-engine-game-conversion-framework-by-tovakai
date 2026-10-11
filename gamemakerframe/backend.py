from pathlib import Path
import shutil
import struct

from megcfbt.models import UnifiedInspection
from megcfbt.native_backend import NativeBuildError, build_native
from megcfbt.native_runtime import resolve_runtime


def data_info(path: Path):
    """Read bounded FORM chunk headers without loading textures or bytecode."""
    try:
        with path.open('rb') as stream:
            header = stream.read(8)
            if len(header) != 8 or header[:4] != b'FORM':
                return None
            end = struct.unpack_from('<I', header, 4)[0] + 8
            if end > path.stat().st_size:
                return None
            chunks, wad, version, code = set(), None, None, 0
            for _ in range(256):
                if stream.tell() == end:
                    break
                header = stream.read(8)
                if len(header) != 8:
                    return None
                tag, size = struct.unpack('<4sI', header)
                start = stream.tell()
                if start + size > end or tag in chunks:
                    return None
                chunks.add(tag)
                if tag == b'GEN8' and size >= 60:
                    data = stream.read(60)
                    wad = data[1]
                    version = '.'.join(map(str, struct.unpack_from('<4I', data, 44)))
                if tag == b'CODE' and size >= 4:
                    code = struct.unpack('<I', stream.read(4))[0]
                    if code > (size - 4) // 4:
                        return None
                stream.seek(start + size)
            if stream.tell() != end or wad is None:
                return None
            return {'wad': wad, 'version': version, 'code': code}
    except (OSError, struct.error):
        return None


def find_game(root: Path):
    matches = []
    for path in sorted(root.iterdir()):
        if path.is_file() and (path.suffix.casefold() == '.win' or path.name.casefold() in {'game.unx', 'data.droid', 'game.ios'}):
            info = data_info(path)
            if info:
                matches.append((path, info))
    return matches


def inspect_game(root: Path):
    matches = find_game(root)
    if not matches:
        return None
    path, info = matches[0]
    supported = len(matches) == 1 and 8 <= info['wad'] <= 17 and info['code'] > 0
    warning = ('GameMaker VM compatibility varies by runner and native extensions; verify gameplay and saves.',)
    if not supported:
        warning = ('Multiple data files, unsupported bytecode, or absent VM CODE: YYC/GMRT exports cannot use the VM runner.',)
    return UnifiedInspection(root, 'gamemakerframe', 'gamemaker', 'GameMaker', info['version'],
                             root.name, 'needs_testing' if supported else 'unsupported', 'high',
                             'gamemaker-vm' if supported else 'gamemaker-unsupported', supported,
                             warning, (f'{path.name}: FORM/GEN8 WAD {info["wad"]}, CODE {info["code"]}',))


def build_game(source: Path, *, output, runtime=None, force=False, progress=None, **kwargs):
    inspection = inspect_game(source)
    if inspection is None or not inspection.buildable:
        raise NativeBuildError('No supported unambiguous GameMaker VM data found.')
    runtime = resolve_runtime('gamemaker',runtime,progress=progress,download_progress=kwargs.get('download_progress'))
    data_path, _ = find_game(source)[0]
    def prepare(destination):
        shutil.copytree(source, destination, symlinks=False,
                        ignore=shutil.ignore_patterns('*.exe', '*.dll', '*.dylib', '.git'))
    return build_native(source, output=Path(output), runtime=runtime, executable='butterscotch',
                        engine='GameMaker', game_name=inspection.game_name,
                        engine_version=inspection.engine_version, prepare_game=prepare,
                        arguments=[data_path.name], warnings=inspection.warnings, force=force, progress=progress,
                        steam_app_id=kwargs.get('steam_app_id'))
