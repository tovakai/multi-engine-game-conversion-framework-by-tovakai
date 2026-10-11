"""Finish a locally prepared STS2 package on Linux ARM64; no SSH transport."""

import argparse
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import sys
import tempfile

if __name__ == '__main__':
    sys.dont_write_bytecode = True  # Keep the sealed backend inventory unchanged.

from converter_io import safe, relative, read_verified, verified_stream, write_new, publish_new
from convert_sts2 import load_profile, executable, require_elf
from verify_output import MANIFEST, inspect, verify
from patch_pack import validate_native_bindings
from native_cache import cached_build
from build_native import STEAM_API, sdk_headers, sdk_file
from remote_worker import tools
from steam_installation import require_installed
from build_progress import BuildProgress
import steam_entry

HANDOFF = 'frame-package.json'
KIND = 'sts2-frame-handoff-v1'


def verify_package(root):
    root = safe(root)
    manifest_path = safe(root / HANDOFF)
    if manifest_path.stat().st_size > 1024 * 1024:
        raise ValueError('Transfer manifest exceeds limit')
    manifest = json.loads(manifest_path.read_bytes())
    if (not isinstance(manifest, dict) or manifest.get('kind') != KIND
            or not isinstance(manifest.get('files'), list) or len(manifest['files']) > 10000):
        raise ValueError('Not a supported STS2 transfer package')
    names = set()
    for item in manifest['files']:
        if not isinstance(item, dict) or not isinstance(item.get('path'), str):
            raise ValueError('Malformed transfer member')
        name = item['path']
        relative(name)
        if name in names or name == HANDOFF:
            raise ValueError('Duplicate transfer member')
        names.add(name)
        with verified_stream(root / relative(name), item):
            pass
    # Allow only these mutable installation artifacts outside the sealed payload.
    for path in root.rglob('*'):
        name = path.relative_to(root).as_posix()
        if name.split('/')[0] in {'cache', 'game', 'installation-result.json', 'steam-integration'}:
            continue
        safe(path)
        # The bundled launch/collector scripts can write diagnostics when run
        # from the prepared tree. They are not conversion inputs, and the game
        # verifier already permits this same diagnostics directory.
        if name.startswith('prepared/diagnostics/'):
            continue
        if path.is_file() and name not in names | {HANDOFF}:
            raise ValueError('Unexpected transfer file: ' + name)
    return manifest


def finish(prepared, output, native, profile, evidence):
    """Add built natives to verified prepared files without repeating transformations."""
    prepared, output, native = map(safe, (prepared, output, native))
    if output.exists() or not output.parent.is_dir():
        raise ValueError('Game destination must be new, with an existing parent')
    for path in (prepared, native):
        if output == path or path in output.parents or output in path.parents:
            raise ValueError('Game destination overlaps installation inputs')
    report = verify(prepared)
    if report['errors']:
        raise ValueError('Prepared game verification failed: ' + str(report['errors']))
    manifest = json.loads((prepared / MANIFEST).read_bytes())
    if (manifest.get('converter_recipe') != 'sts2-windows-prepared-v1'
            or (manifest.get('release'), manifest.get('commit')) != (profile['release'], profile['commit'])):
        raise ValueError('Prepared game recipe differs from the selected build')
    stage = Path(tempfile.mkdtemp(prefix='.sts2-install-', dir=output.parent))
    try:
        for item in manifest['files']:
            target = stage / relative(item['path'])
            target.parent.mkdir(parents=True, exist_ok=True)
            with verified_stream(prepared / relative(item['path']), item) as source, target.open('xb') as dest:
                shutil.copyfileobj(source, dest, 1024 * 1024)
            target.chmod(0o755 if item.get('executable') else 0o644)
        for item in profile['native_files']:
            raw = read_verified(native / relative(item['provider_name']), item)
            require_elf(raw, item['provider_name'])
            write_new(stage / relative(item['destination']), raw)
        write_new(stage / 'native-build.json', (json.dumps(evidence, indent=2, sort_keys=True) + '\n').encode())
        manifest['native_bindings'] = validate_native_bindings(stage / 'SlayTheSpire2.pck', stage)
        manifest['converter_recipe'] = 'sts2-source-v1'
        manifest['scope'] = 'Prepared locally and compiled on Linux ARM64. Gameplay acceptance remains required.'
        manifest['files'] = [
            {'path': path.relative_to(stage).as_posix(),
             'executable': executable(path.relative_to(stage).as_posix()), **inspect(path)}
            for path in sorted(stage.rglob('*')) if path.is_file()
        ]
        write_new(stage / MANIFEST, (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode())
        report = verify(stage, check_modes=True)
        if report['errors']:
            raise ValueError('Completed game verification failed: ' + str(report['errors']))
        publish_new(stage, output)
        stage = None
        return report
    finally:
        if stage is not None:
            shutil.rmtree(stage)


def install(root, *, progress=print, build_progress=None):
    root = safe(root)
    if platform.system() != 'Linux' or platform.machine() not in {'aarch64', 'arm64'}:
        raise ValueError('Run install.sh on the Steam Frame (Linux ARM64), not on Windows.')
    if sys.version_info < (3, 11):
        raise ValueError('The Frame installation requires Python 3.11 or newer.')
    progress('Checking the Slay the Spire 2 Steam installation')
    steam = require_installed()
    progress('STS2 Steam entry ready: ' + steam['installation'])
    progress('Verifying the transferred package')
    handoff = verify_package(root)
    output = root / 'game'
    if output.exists():
        report = verify(output, check_modes=True)
        manifest = json.loads((output / MANIFEST).read_bytes())
        if report['errors'] or manifest.get('converter_recipe') != 'sts2-source-v1' or (
                manifest.get('release'), manifest.get('commit')) != (handoff['release'], handoff['commit']):
            raise ValueError('Existing game failed verification; it will not be overwritten.')
        progress('Existing completed installation verified')
        return installation_result(root, output, report)
    missing = [name for name in ('git', 'g++', 'readelf') if not shutil.which(name)]
    if missing:
        raise ValueError('Missing Frame prerequisites: ' + ', '.join(missing)
                         + '. Install these through your supported system setup, then rerun install.sh.')
    import importlib.util
    if importlib.util.find_spec('venv') is None:
        raise ValueError('Python venv is required on the Frame; enable it, then rerun install.sh.')
    if shutil.disk_usage(root).free < 10 * 1024**3:
        raise ValueError('At least 10 GiB free storage is required for compilation.')
    profile_path = 'converter_profile_v107.json' if (handoff['release'], handoff['commit']) == ('v0.107.1', '59260271') else 'converter_profile_v1.json'
    profile = json.loads((Path(__file__).parent / profile_path).read_bytes())
    if (profile['release'], profile['commit']) != (handoff['release'], handoff['commit']):
        raise ValueError('Unsupported transfer release')
    pin = next(item for item in profile['native_files'] if item['provider_name'] == 'libsteam_api64.so')
    read_verified(STEAM_API, pin)
    runtime = Path.home() / '.local/share/Steam/steamapps/common/SteamLinuxRuntime_4/pressure-vessel-arm64/bin/pressure-vessel-unruntime'
    if not runtime.is_file() or not os.access(runtime, os.X_OK):
        raise ValueError('The supported Valve ARM64 Steam host runtime is missing.')
    sdk = root / 'vendor-sdk'
    sdk_headers(sdk)
    # Refuse modified vendor runtimes before provisioning tools or fetching sources.
    for section, name in (('core', 'libfmod.so.14'), ('studio', 'libfmodstudio.so.14')):
        pin = next(item for item in profile['native_files'] if item['provider_name'] == name)
        read_verified(sdk_file(sdk, f'api/{section}/lib/arm64/{name}'), pin)
    progress('Preparing private compiler tools; first installation needs internet access')
    scons = tools(root)
    progress('Compiling pinned native sources; build logs are retained under cache/compiled')
    status = {'progress': build_progress} if build_progress is not None else {}
    native, generated, evidence = cached_build(root / 'cache/compiled', sdk, scons=str(scons), **status)
    for item in profile['native_files']:
        built = next(row for row in generated['native_files'] if row['provider_name'] == item['provider_name'])
        item.update(sha256=built['sha256'], size_bytes=built['size_bytes'])
    progress('Completing and verifying the native game')
    report = finish(root / 'prepared', output, native, profile, evidence)
    return installation_result(root, output, report)


def installation_result(root, output, report):
    result = {'output': str(output), 'validation': report,
              'launch_command': shlex.quote(str(output / 'play-steam.sh')) + ' %command%'}
    (root / 'installation-result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def connect_steam(root, *, restore=False):
    root = safe(root)
    require_installed()
    output = safe(root / 'game')
    safe(root / 'steam-integration')
    if restore:
        return steam_entry.restore(output, consent=True)
    return steam_entry.configure(output, consent=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', type=Path, default=Path(__file__).resolve().parent.parent)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--connect-steam', action='store_true',
                         help='configure the existing compiled game in Steam, with a backup; no compilation')
    actions.add_argument('--restore-steam', action='store_true',
                         help='restore the saved Steam launch option; preserve later user edits')
    actions.add_argument('--skip-steam', action='store_true',
                         help='finish compilation without offering Steam configuration')
    args = parser.parse_args(argv)
    try:
        if args.connect_steam or args.restore_steam:
            connect_steam(args.root, restore=args.restore_steam)
            print('Previous Steam launch option restored.' if args.restore_steam
                  else 'Steam launch option configured. Open Slay the Spire 2 in Steam and press Play.')
            return 0
        with BuildProgress() as meter:
            result = install(args.root, progress=meter.message, build_progress=meter.event)
    except Exception as error:
        if args.connect_steam or args.restore_steam:
            print('Steam configuration stopped: ' + str(error), file=sys.stderr)
            print('The compiled game is retained. Steam must be running with its local library UI endpoint '
                  'available; rerun this same action after resolving the error.', file=sys.stderr)
            return 2
        print('Installation stopped: ' + str(error), file=sys.stderr)
        print('Your transfer package and build cache are retained. Resolve the error and rerun install.sh.', file=sys.stderr)
        return 2
    print('\nCompilation and verification complete.')
    configure = False
    if not args.skip_steam and sys.stdin.isatty():
        try:
            answer = input('Configure the STS2 Steam launch option now? The previous setting will be backed up. [Y/n] ')
            configure = answer.strip().lower() in {'', 'y', 'yes'}
        except (EOFError, KeyboardInterrupt):
            print('\nSteam configuration skipped; the compiled game is retained.')
    if configure:
        try:
            connect_steam(args.root)
        except Exception as error:
            print('The compiled game is ready, but Steam configuration failed: ' + str(error), file=sys.stderr)
            print('Steam must be running with its local library UI endpoint available. '
                  'No live Steam configuration files are edited. '
                  'After resolving this, run sh ./install.sh --connect-steam; no recompilation is needed.', file=sys.stderr)
            return 2
        print('Steam launch option configured. Open Slay the Spire 2 in Steam and press Play.\n'
              'To undo: sh ./install.sh --restore-steam')
    else:
        print('To configure Steam without typing the launch option, run:\nsh ./install.sh --connect-steam\n'
              'Manual launch option (optional):\n' + result['launch_command'])
    print('Gameplay compatibility remains experimental.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
