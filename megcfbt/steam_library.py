"""Portable, guided original-entry integration. No Steam configuration writes."""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import hashlib
import stat
from contextlib import contextmanager

# Explicit source-profile identities, never title matching or sidecar guesses.
PROFILES = {
    ('celesteframe', 'celeste-steam-xna-1.4.0.0'): 504230,
    ('monoframe', 'stardew-steam-1.6.15-net6'): 413150,
    ('rpgmframe', 'experimental-until-then-build23785927-native-v1'): 1574820,
}
LEGACY_BACKENDS = {'GameMaker': 'gamemakerframe', 'LÖVE': 'loveframe',
                   'AGS': 'agsframe', 'CelesteFrame': 'celesteframe', 'MonoFrame': 'monoframe'}
NATIVE = set(LEGACY_BACKENDS.values())
WRAPPER_CONTRACT = 'native-steam-chain-v3'


def backend(meta):
    """Use explicit converter identity; accept only exact historical backend names.

    Generic engine names and game titles never establish a backend or Steam identity.
    An explicit unsupported/invalid backend cannot fall back to a legacy name.
    """
    legacy = LEGACY_BACKENDS.get(meta.get('engine'))
    if 'backend' in meta:
        value = meta['backend']
        if not isinstance(value, str) or (legacy and value != legacy):
            return None
        return value
    return legacy


def appid(value):
    if isinstance(value, bool) or not re.fullmatch(r'[1-9][0-9]{0,9}', str(value)):
        raise ValueError('Invalid Steam AppID')
    number = int(value)
    if number >= 2**31:
        raise ValueError('Invalid original Steam AppID')
    return number


def read_vdf(path):
    """Strict text KeyValues subset: malformed/duplicate keys fail closed."""
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('Steam metadata is too large')
    text = path.read_text(encoding='utf-8-sig')
    tokens = []
    at = 0
    pattern = re.compile(r'\s+|//[^\n]*|"((?:\\.|[^"\\])*)"|([{}])')
    while at < len(text):
        match = pattern.match(text, at)
        if not match:
            raise ValueError('Malformed Steam metadata')
        at = match.end()
        if match.group(1) is not None:
            tokens.append(('text', re.sub(r'\\(["\\])', r'\1', match.group(1))))
        elif match.group(2):
            tokens.append((match.group(2), match.group(2)))
    index = 0
    def node(nested=False):
        nonlocal index
        result = {}
        while index < len(tokens):
            kind, key = tokens[index]
            index += 1
            if kind == '}' and nested:
                return result
            if kind != 'text' or key.lower() in result or index >= len(tokens):
                raise ValueError('Conflicting or malformed Steam metadata')
            kind, value = tokens[index]
            index += 1
            if kind == '{':
                value = node(True)
            elif kind != 'text':
                raise ValueError('Malformed Steam metadata')
            result[key.lower()] = value
        if nested:
            raise ValueError('Incomplete Steam metadata')
        return result
    return node()


def steam_roots(home=None):
    home = home or Path.home()
    return [home / '.steam/steam', home / '.local/share/Steam',
            home / '.var/app/com.valvesoftware.Steam/.local/share/Steam']


def discover(roots):
    libraries, errors = set(), []
    for root in roots:
        if not root.is_dir():
            continue
        libraries.add(root.resolve())
        metadata = root / 'steamapps/libraryfolders.vdf'
        try:
            folders = read_vdf(metadata)['libraryfolders']
            for key, value in folders.items():
                if key.isdecimal():
                    raw = value.get('path') if isinstance(value, dict) else value
                    if not isinstance(raw, str) or not Path(raw).is_absolute():
                        raise ValueError('Invalid Steam library path')
                    library = Path(raw)
                    if library.is_dir():
                        libraries.add(library.resolve())
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f'{metadata}: {exc}')
    return sorted(libraries), errors


def installation(number, roots=None):
    number = appid(number)
    libraries, errors = discover(roots if roots is not None else steam_roots())
    found, incomplete, unreliable = [], [], False
    for library in libraries:
        manifest = library / 'steamapps' / f'appmanifest_{number}.acf'
        if not manifest.exists():
            continue
        try:
            if manifest.is_symlink() or (library / 'steamapps/common').is_symlink():
                raise ValueError('Unsafe installed metadata or common-directory symlink')
            data = read_vdf(manifest)['appstate']
            if appid(data['appid']) != number:
                raise ValueError('Conflicting manifest AppID')
            folder = data['installdir']
            if not isinstance(folder, str) or folder in {'', '.', '..'} or '/' in folder or '\\' in folder:
                raise ValueError('Unsafe installed-game path')
            common = (library / 'steamapps/common').resolve()
            game = library / 'steamapps/common' / folder
            if game.is_symlink() or game.resolve().parent != common:
                raise ValueError('Unsafe installed-game symlink')
            # Fully installed only. Update, download and validation states are incomplete.
            if int(data['stateflags']) != 4 or not game.is_dir() or not any(game.iterdir()):
                incomplete.append(str(manifest))
            else:
                found.append({'manifest': str(manifest), 'game': str(game.resolve()),
                              'library': str(library)})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f'{manifest}: {exc}')
            unreliable = True
    return {'state': 'unknown' if unreliable else 'installed' if found else 'incomplete' if incomplete else
            'unknown' if errors or not libraries else 'missing',
            'installations': found, 'errors': errors, 'incomplete': incomplete,
            'ownership': 'unknown'}


def identity(meta):
    known = PROFILES.get((backend(meta), meta.get('compatibility_profile')))
    evidence = meta.get('steam_identity')
    value = None
    if evidence is not None:
        if not isinstance(evidence, dict) or evidence.get('source') != 'installed-source-manifest':
            raise ValueError('Unverified Steam identity')
        value = appid(evidence.get('appid'))
    if known and value and known != value:
        raise ValueError('Steam identity conflicts with compatibility profile')
    runtime_id = meta.get('steam_runtime_appid')
    if runtime_id is not None:
        runtime_id = appid(runtime_id)
        if (known or value) and runtime_id != (known or value):
            raise ValueError('Steam runtime AppID conflicts with original identity')
    return known or value


def capability(meta):
    if meta.get('architecture') != 'aarch64':
        return False, 'Original-entry linking requires validated AArch64 package metadata.'
    if meta.get('target_platform') != 'linux-aarch64':
        return False, 'Windows ARM64/ARM64 Proton retains its specialized launcher; original-entry linking is deferred.'
    if backend(meta) not in NATIVE:
        return False, 'This backend launch contract has not been approved for shared linking.'
    if backend(meta) in {'celesteframe', 'monoframe'} and (backend(meta), meta.get('compatibility_profile')) not in PROFILES:
        return False, 'This managed backend requires an audited compatibility profile.'
    return True, 'Native launch wrapper; Steam Input, playtime and achievements require separate device verification.'


def safe_file(root, relative):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError('Unsafe package path')
    try:
        path = assets().path_inside(root, relative)
    except ValueError as exc:
        raise ValueError('Missing or unsafe package launcher path') from exc
    if (path.resolve().is_relative_to(root.resolve()) and path.is_file()
            and not path.is_symlink() and path.stat().st_nlink == 1):
        return path.resolve()
    raise ValueError('Missing or unsafe package launcher')


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError('Unsafe integration record symlink')
    if path.exists() and (not path.is_file() or path.stat().st_nlink != 1):
        raise ValueError('Unsafe multiply-linked integration record')
    fd, temporary = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name == 'posix':
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def records():
    return Path.home() / '.local/share/megcfbt/steam-links'


def prepare(root, meta, launcher, number, previous, record_path, detected, *,
            mode='guided-native', previous_source=None, preserve_previous=True):
    root = root.resolve()
    launcher = safe_file(root, meta.get('launcher'))
    if (root / '.megcfbt').is_symlink():
        raise ValueError('Unsafe package metadata directory')
    if detected['state'] != 'installed':
        raise ValueError('Original game must be installed through Steam on this Frame before linking.')
    for item in detected.get('installations', []):
        original = Path(item['game']).resolve()
        if root.is_relative_to(original) or original.is_relative_to(root):
            raise ValueError('Converted package must be separate from the original Steam installation')
    allowed, reason = capability(meta)
    if not allowed or identity(meta) != number:
        raise ValueError(reason if not allowed else 'Conflicting Steam identity')
    # Steam expands %command%; do not permit substitution inside our own path.
    if any(c in str(root) for c in '\n\r%'):
        raise ValueError('Move the converted package to a path without newlines or percent signs.')
    # Keep the entry point outside the conversion so deleted/moved packages can
    # still emit repair guidance from the original Steam entry.
    wrapper = record_path.parent / f'launch-{number}.sh'
    if any(c in str(wrapper) for c in '\n\r%'):
        raise ValueError('Integration record path contains unsafe launch-option characters')
    if wrapper.is_symlink():
        raise ValueError('Unsafe wrapper symlink')
    launcher.chmod(launcher.stat().st_mode | 0o100)
    generated = shlex.quote(str(wrapper)) + ' %command%'
    old = json.loads(record_path.read_text()) if record_path.exists() else None
    if preserve_previous and old and old.get('status') != 'restored':
        previous = old.get('previous')
    record = {'schema': 'megcfbt.steam-link/v1', 'appid': number,
              'package': str(root), 'launcher': str(launcher), 'generated': generated,
              'previous': previous, 'previous_source': previous_source or ('user-preserved' if previous is not None else 'unavailable'),
              'converter': meta.get('conversion', {}).get('converter'),
              'profile': meta.get('compatibility_profile'), 'mode': mode,
              'status': 'pending', 'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'installations': detected['installations'], 'wrapper': str(wrapper)}
    record['wrapper_contract'] = WRAPPER_CONTRACT
    atomic_json(record_path, record)  # Recovery information precedes activation.
    # No environment identity is fabricated. Reject standalone/non-Steam launches.
    script = ('#!/bin/sh\nset -eu\n'
              'if [ "$#" -eq 0 ]; then\n'
              ' echo "Launch the original installed game through Steam. Rerun install-to-steam.sh to repair." >&2\n exit 1\nfi\n'
              f'if [ ! -f {shlex.quote(str(launcher))} ]; then\n'
              ' echo "Converted package moved or deleted. Rerun install-to-steam.sh from a newly extracted package and choose Restore or Repair." >&2\n exit 1\nfi\n'
              f'if [ ! -f {shlex.quote(str(root / ".megcfbt/steam_library.py"))} ]; then\n'
              ' echo "Bundled installer helper missing. Re-extract the conversion ZIP and rerun install-to-steam.sh to repair." >&2\n exit 1\nfi\n'
              f'exec python3 {shlex.quote(str(root / ".megcfbt/steam_library.py"))} --launch-link {shlex.quote(str(record_path))} {shlex.quote(generated)} "$@"\n')
    record['wrapper_sha256'] = hashlib.sha256(script.encode('utf-8')).hexdigest()
    atomic_json(record_path, record)
    fd, temporary = tempfile.mkstemp(prefix='.wrapper-', dir=wrapper.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(script)
        os.chmod(temporary, 0o755)
        os.replace(temporary, wrapper)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return record


def receipt(path, generated, expected_package=None):
    record = json.loads(path.read_text())
    if record.get('generated') != generated or record.get('status') == 'restored':
        raise ValueError('Link changed; rerun installer to repair')
    if expected_package is not None and record.get('package') != str(expected_package):
        raise ValueError('Package changed during link repair. Rerun install-to-steam.sh before launching.')
    context = launch_context(record['appid'])
    if context is None:
        raise ValueError('Genuine matching Steam launch context required')
    if installation(record['appid'])['state'] != 'installed':
        raise ValueError('Original Steam installation missing; rerun installer')
    record['status'] = 'launch-observed'
    record['launch_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    record['launch_context'] = context
    atomic_json(path, record)


def arm64_program(path):
    with assets().readonly_open(path) as stream:
        header = stream.read(20)
    if header[:6] != b'\x7fELF\x02\x01' or header[18:20] != b'\xb7\0' or not os.access(path, os.X_OK):
        raise ValueError('Expected installed native ARM64 Steam program: ' + str(path))


def native_host_runtime(steam_directories):
    libraries, _ = discover(steam_directories)
    for library_path in libraries:
        for folder in ('SteamLinuxRuntime_4', 'SteamLinuxRuntime_4-arm64'):
            base = library_path / 'steamapps/common' / folder
            if not base.is_dir() or base.is_symlink():
                continue
            for tools in ('pressure-vessel-arm64/bin', 'pressure-vessel/bin'):
                try:
                    runtime = assets().path_inside(base, tools + '/pressure-vessel-unruntime')
                    wrap = assets().path_inside(base, tools + '/pressure-vessel-wrap')
                    arm64_program(wrap)
                    if runtime.is_file() and os.access(runtime, os.X_OK):
                        return runtime
                except (OSError, ValueError):
                    continue
    raise ValueError('Installed Valve ARM64 host-runtime tools are unavailable; use non-Steam installation. Steam and SteamVR will not be restarted.')


def native_launch_plan(root, number, arguments, *, steam_directories=None):
    """Keep genuine Frame wrapper/reaper; replace only the foreign payload.

    Shared native contract inspired by STS2's two-stage launch plan. Its game
    launcher/finalization are not reused, and Steam identity fields are not set.
    """
    number = appid(number)
    supplied_roots = steam_directories if steam_directories is not None else steam_roots()
    roots = [path.resolve() for path in supplied_roots if path.is_dir()]
    args = list(arguments)
    if not args or not Path(args[0]).is_absolute() or '--' not in args:
        raise ValueError('Missing genuine expanded Steam command; rerun installer and launch the original entry')
    wrapper = Path(args[0]).resolve(strict=True)
    steam = next((path for path in roots if wrapper == path / 'linuxarm64/steam-launch-wrapper'), None)
    if steam is None:
        raise ValueError('Unsupported native Steam launch wrapper; no original executable was run')
    separator = args.index('--')
    options = args[1:separator]
    if options and (len(options) != 2 or options[0] != '--oom-score-adjust'
                    or not re.fullmatch('-?[0-9]{1,4}', options[1]) or not -1000 <= int(options[1]) <= 1000):
        raise ValueError('Unsupported Steam wrapper options')
    tail = args[separator + 1:]
    if len(tail) < 5 or tail[1:4] != ['SteamLaunch', f'AppId={number}', '--']:
        raise ValueError('Unsupported or conflicting Steam reaper command')
    reaper = Path(tail[0]).resolve(strict=True)
    if reaper != steam / 'steamrtarm64/reaper':
        raise ValueError('Unsupported Steam reaper')
    arm64_program(wrapper)
    arm64_program(reaper)
    runtime = native_host_runtime(roots)
    helper = safe_file(root, '.megcfbt/steam_library.py')
    command = [*args[:separator + 5], str(runtime), '--no-copy-runtime', '--no-gc-runtimes',
               '--no-systemd-scope', '--batch', '--terminal=none', '--', 'python3', str(helper),
               '--run-converted', str(records() / f'{number}.json'),
               shlex.quote(str(records() / f'launch-{number}.sh')) + ' %command%']
    return command


def run_linked(path, generated, expected_package, arguments):
    record = json.loads(path.read_text())
    if record.get('package') != str(expected_package):
        raise ValueError('Package changed during repair; rerun installer')
    log = assets().path_inside(expected_package, '.megcfbt/steam-launch.log')
    descriptor = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('Unsafe converted launch log')
        stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        os.write(descriptor, f'\n[{stamp}] Original Steam entry {record["appid"]}: starting converted launcher\n'.encode())
        os.dup2(descriptor, 1)
        os.dup2(descriptor, 2)
    finally:
        os.close(descriptor)
    command = native_launch_plan(expected_package, record['appid'], arguments)
    # Use the exact record path/command supplied by our wrapper, including custom
    # data directories; nothing from the discarded original game suffix is used.
    command[-2:] = [str(path), generated]
    environment = dict(os.environ)
    for key in ('PRESSURE_VESSEL_RUNTIME', 'PRESSURE_VESSEL_RUNTIME_ARCHIVE',
                'PRESSURE_VESSEL_RUNTIME_BASE', 'PRESSURE_VESSEL_PREFIX'):
        environment.pop(key, None)
    os.execve(command[0], command, environment)


def run_converted(path, generated, expected_package):
    receipt(path, generated, expected_package)
    record = json.loads(path.read_text())
    os.environ['MEGCFBT_ORIGINAL_STEAM_ENTRY'] = '1'
    os.environ['MEGCFBT_FRAME_ENV_IMPORTED'] = '1'
    launcher = safe_file(expected_package, Path(record['launcher']).relative_to(expected_package).as_posix())
    os.execv(str(launcher), [str(launcher)])


def launch_context(number, *, proc_root=None, parent=None):
    """Observe genuine supplied context, including clients lacking SteamAppId."""
    keys = ('SteamAppId', 'SteamGameId', 'STEAM_COMPAT_APP_ID', 'SteamOverlayGameId')
    supplied = {key: os.environ[key] for key in keys if os.environ.get(key)}
    if supplied:
        if any(value != str(number) for value in supplied.values()):
            return None
        return {'source': 'steam-environment', 'keys': sorted(supplied)}
    # SteamLaunch's AppId is part of the actual inherited process chain. Never
    # search unrelated processes or set environment IDs to manufacture evidence.
    pid, visited = parent if parent is not None else os.getppid(), set()
    proc_root = proc_root or Path('/proc')
    while pid > 1 and pid not in visited:
        visited.add(pid)
        directory = proc_root / str(pid)
        try:
            args = directory.joinpath('cmdline').read_bytes().split(b'\0')
            if any(Path(arg.decode(errors='replace')).name == 'SteamLaunch' for arg in args):
                ids = [arg[6:].decode('ascii') for arg in args if arg.startswith(b'AppId=')]
                return {'source': 'steam-launch-ancestor', 'pid': pid} if ids == [str(number)] else None
            fields = directory.joinpath('stat').read_text().rsplit(')', 1)[1].split()
            pid = int(fields[1])
        except (OSError, ValueError, IndexError):
            return None
    return None


def live_client():
    try:
        from . import steam_client
    except ImportError:
        import steam_client
    return steam_client.connect()


def configure(root, meta, number, record_path, detected, client):
    with link_transaction(record_path):
        return _configure(root, meta, number, record_path, detected, client)


@contextmanager
def link_transaction(record_path):
    record_path.parent.mkdir(parents=True, exist_ok=True)
    if record_path.is_symlink() or record_path.parent.is_symlink():
        raise ValueError('Unsafe Steam integration record')
    lock = record_path.with_suffix('.lock')
    if lock.is_symlink():
        raise ValueError('Unsafe Steam integration lock')
    descriptor = os.open(lock, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        if os.name == 'posix':
            import fcntl
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError('Another Steam link operation is active; retry after it finishes') from exc
        yield
    finally:
        os.close(descriptor)


def _configure(root, meta, number, record_path, detected, client):
    """Backup before a compare-and-set; verify before reporting configuration."""
    current = client.read(number)
    old = json.loads(record_path.read_text()) if record_path.exists() else None
    if old and (old.get('schema') != 'megcfbt.steam-link/v1' or old.get('appid') != number):
        raise ValueError('Conflicting Steam integration record')
    previous, provenance = current, 'steam-live'
    if old and old.get('status') != 'restored':
        if old.get('mode') == 'live-native' or current == old.get('generated'):
            if current not in {old.get('generated'), old.get('previous')}:
                raise ValueError('Steam launch options changed after linking; unrelated user changes will not be overwritten.')
            if current == old.get('previous') and old.get('status') not in {'pending', 'injecting', 'configuration-unverified'}:
                raise ValueError('Steam launch options changed after linking; restore or reconcile the existing record first.')
            previous, provenance = old.get('previous'), old.get('previous_source')
            if not isinstance(previous, str) or provenance not in {'steam-live', 'user-preserved'}:
                raise ValueError('Previous launch options unavailable; automatic repair cannot invent a backup.')
            wrapper = Path(old.get('wrapper', ''))
            if (current == old['generated'] and old.get('status') in {'configured', 'launch-observed'}
                    and old.get('package') == str(root.resolve())
                    and old.get('profile') == meta.get('compatibility_profile')
                    and old.get('converter') == meta.get('conversion', {}).get('converter')
                    and old.get('wrapper_contract') == WRAPPER_CONTRACT
                    and wrapper.is_file() and not wrapper.is_symlink()
                    and hashlib.sha256(wrapper.read_bytes()).hexdigest() == old.get('wrapper_sha256')):
                safe_file(root, meta['launcher'])
                if not capability(meta)[0] or identity(meta) != number or detected['state'] != 'installed':
                    raise ValueError('Installed game or package contract changed')
                return old
    record = prepare(root, meta, root / meta['launcher'], number, previous, record_path, detected,
                     mode='live-native', previous_source=provenance, preserve_previous=False)
    record['status'], record['client_endpoint'] = 'injecting', client.endpoint
    atomic_json(record_path, record)
    try:
        client.set(number, current, record['generated'])
        if client.read(number) != record['generated']:
            raise ValueError('Live Steam launch-option verification failed')
    except (OSError, ValueError) as exc:
        record['status'] = 'configuration-unverified'
        atomic_json(record_path, record)
        raise ValueError('Automatic configuration was not verified. Recovery record retained; rerun installer to verify or restore.') from exc
    record['status'] = 'configured'
    record['configured_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    atomic_json(record_path, record)
    return record


def restore_live(record_path, client):
    with link_transaction(record_path):
        return _restore_live(record_path, client)


def _restore_live(record_path, client):
    record = json.loads(record_path.read_text())
    previous = record.get('previous')
    if not isinstance(previous, str) or record.get('previous_source') not in {'steam-live', 'user-preserved'}:
        raise ValueError('No reliable previous launch configuration was recorded; restoration cannot invent one.')
    current = client.read(record['appid'])
    if current == previous and record.get('status') in {'restoring', 'restored', 'configuration-unverified'}:
        record['status'] = 'restored'
        atomic_json(record_path, record)
        return previous
    if current != record['generated']:
        raise ValueError('Steam launch options changed after linking; unrelated user settings were not overwritten.')
    record['status'] = 'restoring'
    atomic_json(record_path, record)
    client.set(record['appid'], current, previous)
    if client.read(record['appid']) != previous:
        raise ValueError('Restoration could not be verified; recovery record retained. Rerun Restore.')
    record['status'] = 'restored'
    record['restored_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    atomic_json(record_path, record)
    return previous


def observe_runtime(root, meta, number, *, proc_root=None):
    base = safe_directory(root, meta['payload']) if meta.get('payload') else root
    executable = {'monoframe': 'dotnet/dotnet', 'celesteframe': 'dotnet/dotnet',
                  'gamemakerframe': 'butterscotch', 'loveframe': 'love', 'agsframe': 'ags'}.get(backend(meta))
    if not executable:
        return None
    expected = safe_file(root, (base / 'runtime' / executable).relative_to(root).as_posix())
    with expected.open('rb') as stream:
        header = stream.read(20)
    if len(header) < 20 or header[:6] != b'\x7fELF\x02\x01' or int.from_bytes(header[18:20], 'little') != 183:
        raise ValueError('Converted runtime is not a Linux AArch64 ELF')
    for process in (proc_root or Path('/proc')).glob('[0-9]*'):
        try:
            if (process / 'exe').resolve() != expected.resolve():
                continue
            env = dict(item.split(b'=', 1) for item in (process / 'environ').read_bytes().split(b'\0') if b'=' in item)
            values = [env[key] for key in (b'SteamAppId', b'SteamGameId', b'STEAM_COMPAT_APP_ID', b'SteamOverlayGameId') if env.get(key)]
            if values and all(value == str(number).encode() for value in values):
                return {'pid': int(process.name), 'executable': str(expected), 'architecture': 'aarch64'}
        except (OSError, ValueError):
            continue
    return None


def safe_directory(root, relative):
    return assets().path_inside(root, relative)


def choose(prompt):
    try:
        return input(prompt).strip()
    except EOFError:
        return ''


def assets():
    try:
        from . import asset_dedup
    except ImportError:
        import asset_dedup
    return asset_dedup


def standalone(root):
    data = assets().load(root)
    if data and data['status'] != 'restored':
        print('Restore converted asset copies before non-Steam registration. No deduplication is required for standalone packages.')
        if choose('Restore/recover asset copies now? [y/N]: ').lower() != 'y':
            return False
        print(f'Converted asset copies restored: {assets().restore_assets(root)}')
    return True


def offer_dedup(root, meta, detected):
    module = assets()
    existing = module.load(root)
    if existing and existing['status'] != 'restored':
        try:
            module.validate(root, existing, detected)
            result = module.summary(existing)
            print(f'Existing linked assets: {result["linked"]}; measured reclaimed bytes: {result["reclaimed_bytes"]}')
            return
        except ValueError as exc:
            print(str(exc))
            if choose('Restore/recover converted asset copies now? [y/N]: ').lower() != 'y':
                raise ValueError('Asset recovery is required before link repair; original Steam files remain unchanged')
            module.restore_assets(root, detected)
    try:
        entries, reason = module.candidates(root, meta, detected, progress=asset_progress)
    except (OSError, ValueError) as exc:
        print(f'Asset comparison unavailable: {exc}. Files linked: 0; disk space reclaimed: 0 bytes. Full assets retained.')
        return
    print(reason)
    if not entries:
        print('Files linked: 0. Disk space reclaimed: 0 bytes. Full converted assets retained.')
        return
    print(f'Byte-identical experimental assets: {len(entries)}. Steam files will never be modified.')
    print('Deduplication requires read-only bubblewrap launches. Backend gameplay acceptance is pending; no backend is advertised as safely deduplicated yet.')
    print('Deduplication can take a while, especially for large games or SD cards. A progress bar will show comparison and linking; keep the conversion ZIP for recovery.')
    if choose('Enable experimental asset deduplication? [y/N]: ').lower() != 'y':
        print('Files linked: 0. Disk space reclaimed: 0 bytes. Full converted assets retained.')
        return
    try:
        result = module.enable(root, meta, detected, experimental=True, progress=asset_progress)
    except (OSError, ValueError) as exc:
        if module.load(root):
            raise ValueError(f'Asset transaction requires recovery: {exc}. Rerun installer; original Steam files remain unchanged.') from exc
        print(f'Deduplication unavailable: {exc}. Files linked: 0; disk space reclaimed: 0 bytes. Full assets retained.')
        return
    print(f'Files linked: {result["linked"]}. Disk space reclaimed: {result["reclaimed_bytes"]} bytes' + ('.' if result['allocation_measured'] else ' (allocation unavailable; unmeasured savings not claimed).'))
    print('Reclaimed bytes measure observed free-space increases capped by released file allocations; delayed filesystem reclamation or other disk activity can affect the observation.')


def asset_progress(phase, completed, total):
    width = 24
    done = width * completed // total if total else width
    print(f'{phase}: [{"#" * done}{"-" * (width - done)}] {completed}/{total}', flush=True)


def menu(root, name, launcher):
    """Return True to continue existing non-Steam workflow, False when handled."""
    root = root.resolve()
    if (root / '.megcfbt').is_symlink():
        raise ValueError('Unsafe package metadata directory')
    meta = json.loads((root / '.megcfbt/package.json').read_text(encoding='utf-8'))
    if not isinstance(meta, dict) or meta.get('schema') != 'megcfbt.frame-build/v1':
        raise ValueError('Unsupported package metadata schema')
    if not isinstance(meta.get('conversion', {}), dict):
        raise ValueError('Invalid conversion metadata')
    safe_file(root, meta.get('launcher'))
    try:
        number = identity(meta)
    except ValueError as exc:
        print(f'{name} detected\nAutomatic linking unavailable: {exc}. No trustworthy Steam AppID.')
        return choose('1. Add as non-Steam game\n2. Cancel\nChoice: ') == '1' and standalone(root)
    allowed, reason = capability(meta)
    print(f'{name} detected\nSteam AppID: {number or "unavailable"}')
    if number is None or not allowed:
        print('Automatic linking unavailable: ' + ('no trustworthy original Steam AppID.' if number is None else reason))
        return choose('1. Add as non-Steam game\n2. Cancel\nChoice: ') == '1' and standalone(root)
    path = records() / f'{number}.json'
    if path.is_symlink():
        raise ValueError('Unsafe integration record')
    old = json.loads(path.read_text()) if path.exists() else None
    if old and old.get('status') != 'restored':
        print(f'Existing integration: {old.get("status")} at {old.get("package")}')
        answer = choose('1. Verify existing link\n2. Update or repair link\n3. Restore original Steam launch configuration\n4. Add separate non-Steam shortcut\n5. Cancel\nChoice: ')
        if answer == '4':
            return standalone(root)
        if answer == '1':
            print('Launch observation: ' + str(old.get('launch_utc', 'unverified')))
            present = Path(old['launcher']).is_file()
            print('Package present: ' + str(present))
            if not present:
                print('Package moved or deleted: select Update or repair at the new extracted location, or Restore original Steam launch configuration.')
            print('Local installation: ' + installation(number)['state'])
            try:
                client = live_client()
                try:
                    matches = client.read(number) == old['generated']
                    print('Live Steam launch configuration: ' + ('verified' if matches else 'changed or not configured; use Repair or Restore'))
                finally:
                    client.close()
            except (OSError, ValueError) as exc:
                return automatic_unavailable(root, exc)
            if assets().load(root):
                try:
                    assets().validate(root)
                    print('Linked asset hashes and source installation verified.')
                except ValueError as exc:
                    print('Asset repair required: ' + str(exc))
                    if choose('Restore/recover converted asset copies now? [y/N]: ').lower() == 'y':
                        assets().restore_assets(root)
            if present and matches:
                observed = observe_runtime(root, meta, number)
                if observed:
                    old['runtime_observation'] = observed
                    old['runtime_verified_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    atomic_json(path, old)
                    print(f'Actual converted runtime verified: {observed["executable"]} (AArch64 ELF, PID {observed["pid"]}).')
                else:
                    print('Actual ARM64 game runtime is unverified. Launch the original Steam entry and verify while the game is running; wrapper execution alone is insufficient.')
            print('Gameplay, Steam Input, playtime and achievements remain separately unverified.')
            return False
        if answer == '3':
            try:
                client = live_client()
                try:
                    restore_live(path, client)
                finally:
                    client.close()
                print('Original Steam launch configuration restored and verified through the live client.')
            except (OSError, ValueError) as exc:
                return automatic_unavailable(root, exc)
            data = assets().load(root)
            if data and data['status'] != 'restored' and choose('Also restore converted asset copies for standalone use? [y/N]: ').lower() == 'y':
                assets().restore_assets(root)
            return False
        if answer != '2':
            return False
        if choose('Update/repair this link using verified live Steam settings? [y/N]: ').lower() != 'y':
            return False
    while True:
        detected = installation(number)
        print('Original Steam installation: ' + detected['state'])
        for error in detected['errors']:
            print('Metadata warning: ' + error)
        if detected['state'] == 'installed':
            break
        print('The original Steam game must be installed through Steam on this Steam Frame before library linking is available.')
        print('Ownership or installation on another computer is not sufficient. Ownership here is unknown.')
        answer = choose('1. Install original game through Steam, then link\n2. Add as non-Steam game instead\n3. Cancel\n4. Rescan\nChoice: ')
        if answer == '2':
            return standalone(root)
        if answer == '4':
            continue
        if answer == '1':
            subprocess.run(['xdg-open', f'steam://install/{number}'], check=True)
            if choose('Complete installation in Steam. Press R to rescan, or rerun this installer later: ').lower() == 'r':
                continue
        return False
    answer = choose('1. Link converted ARM64 version to existing Steam game (recommended)\n2. Add separate non-Steam game\n3. Cancel\nChoice: ')
    if answer == '2':
        return standalone(root)
    if answer != '1':
        return False
    print('Configuring the original entry through running Steam; existing launch options will be backed up and verified. Original game files remain untouched.')
    try:
        client = live_client()
        try:
            native_host_runtime(steam_roots())
            configure(root, meta, number, path, detected, client)
        finally:
            client.close()
    except (OSError, ValueError) as exc:
        return automatic_unavailable(root, exc)
    print('Steam launch configuration saved and read back successfully. No copying or Steam Properties editing is required.')
    offer_dedup(root, meta, detected)
    print('Launch the original game through Steam, then rerun installer → Verify existing link while it is running.')
    print('Game runtime, gameplay, Steam Input, playtime and achievements require separate verification.')
    return False


def automatic_unavailable(root, exc):
    print(f'Automatic Steam linking/restoration unavailable: {exc}')
    print('Linking is not reported complete. Steam stays running; no live configuration files will be edited.')
    return choose('1. Add as non-Steam game instead\n2. Cancel\nChoice: ') == '1' and standalone(root)


if __name__ == '__main__':
    import sys
    if len(sys.argv) >= 4 and sys.argv[1] in {'--receipt', '--launch-link', '--run-converted'}:
        try:
            arguments = [Path(sys.argv[2]), sys.argv[3], Path(__file__).resolve().parent.parent]
            if sys.argv[1] == '--launch-link':
                run_linked(*arguments, sys.argv[4:])
            elif sys.argv[1] == '--run-converted':
                run_converted(*arguments)
            else:
                receipt(*arguments)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise SystemExit(f'Steam link repair required: {exc}')
    elif len(sys.argv) == 3 and sys.argv[1] == '--inspect':
        print(json.dumps(installation(appid(sys.argv[2])), indent=2))
    else:
        raise SystemExit('Use install-to-steam.sh. Restoration is available in its existing-link menu.')
