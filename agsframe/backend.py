from pathlib import Path
import shutil
import json

from megcfbt.models import UnifiedInspection
from megcfbt.native_backend import NativeBuildError, build_native, validate_runtime
from agsframe.compat import is_windows_vsync_hook, native_graphics_config
from megcfbt.native_runtime import configured_runtime

FOOTER = b'CLIB\x01\x02\x03\x04SIGE'


def find_game(root: Path):
    matches = []
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix.casefold() not in {'.exe', '.ags', '.dat'}:
            continue
        try:
            with path.open('rb') as stream:
                head = stream.read(5)
                stream.seek(max(0, path.stat().st_size - 32))
                tail = stream.read(32)
            if head == b'CLIB\x1a' or FOOTER in tail:
                matches.append(path)
        except OSError:
            continue
    return matches


def inspect_game(root: Path):
    matches = find_game(root)
    if not matches:
        return None
    plugins = tuple(p.name for p in root.glob('*.dll') if p.name.casefold().startswith('ags') or p.name.casefold() == 'agsteam.dll')
    warnings = ('AGS plugins require matching ARM64 implementations; Windows DLLs cannot be executed.',)
    return UnifiedInspection(root, 'agsframe', 'ags', 'Adventure Game Studio', None, root.name,
                             'needs_testing' if len(matches) == 1 else 'ambiguous', 'high', 'ags',
                             len(matches) == 1, warnings,
                             tuple(f'{p.name}: CLIB game data' for p in matches) + plugins)


def build_game(source: Path, *, output, runtime=None, force=False, progress=None, **kwargs):
    runtime = runtime if runtime is not None else configured_runtime('ags')
    inspection = inspect_game(source)
    if inspection is None or not inspection.buildable:
        raise NativeBuildError('No unambiguous AGS CLIB game data found.')
    payload = find_game(source)[0]
    warnings = list(inspection.warnings)
    vsync_hook = False
    if runtime is not None:
        runtime_root = validate_runtime(Path(runtime), 'ags')
        manifest = runtime_root / 'engine-capabilities.json'
        try:
            capabilities = json.loads(manifest.read_text()) if manifest.exists() else {}
            builtin = {name.casefold() for name in capabilities.get('builtin_plugins', [])}
            stubs = {name.casefold() for name in capabilities.get('stub_plugins', [])}
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            raise NativeBuildError('Invalid AGS runtime capability manifest.') from exc
        missing = []
        for plugin in source.glob('*.dll'):
            name = plugin.stem.casefold()
            if name.startswith('ags') or name == 'agsteam':
                if is_windows_vsync_hook(plugin):
                    vsync_hook = True
                    warnings.append('Known Windows Direct3D vsync hook replaced by native AGS OpenGL vsync.')
                elif name in stubs:
                    warnings.append(f'{plugin.name}: runtime uses offline placeholder functions; its online/plugin features are unavailable.')
                elif name not in builtin and not any(p.stem.casefold() in {name, 'lib'+name} for p in runtime_root.glob('*.so')):
                    missing.append(plugin.name)
        if missing:
            raise NativeBuildError('ARM64 AGS plugin implementations required: ' + ', '.join(missing))
    def prepare(destination):
        shutil.copytree(source, destination, symlinks=False,
                        ignore=shutil.ignore_patterns('*.dll', '.git'))
        native_graphics_config(destination,replace_vsync_hook=vsync_hook)
        # An executable containing CLIB is data to AGS; retain it and never
        # execute the original Windows program. Numbered volumes remain intact.
    return build_native(source, output=Path(output), runtime=runtime, executable='ags', engine='AGS',
                        game_name=inspection.game_name, engine_version=inspection.engine_version,
                        prepare_game=prepare, arguments=[payload.name], warnings=tuple(warnings), force=force, progress=progress,
                        steam_app_id=kwargs.get('steam_app_id'))
