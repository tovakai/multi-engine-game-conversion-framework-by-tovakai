"""Portable, guided original-entry integration. No Steam configuration writes."""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile

# Explicit source-profile identities, never title matching or sidecar guesses.
PROFILES = {
    ('celesteframe', 'celeste-steam-xna-1.4.0.0'): 504230,
    ('monoframe', 'stardew-steam-1.6.15-net6'): 413150,
}
LEGACY_BACKENDS = {'GameMaker': 'gamemakerframe', 'LÖVE': 'loveframe',
                   'AGS': 'agsframe', 'CelesteFrame': 'celesteframe', 'MonoFrame': 'monoframe'}
NATIVE = set(LEGACY_BACKENDS.values())


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
    path = root / relative
    if path.resolve().is_relative_to(root.resolve()) and path.is_file() and not path.is_symlink():
        return path.resolve()
    raise ValueError('Missing or unsafe package launcher')


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError('Unsafe integration record symlink')
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


def prepare(root, meta, launcher, number, previous, record_path, detected):
    root = root.resolve()
    launcher = safe_file(root, meta.get('launcher'))
    launcher.chmod(launcher.stat().st_mode | 0o100)
    if (root / '.megcfbt').is_symlink():
        raise ValueError('Unsafe package metadata directory')
    if detected['state'] != 'installed':
        raise ValueError('Original game must be installed through Steam on this Frame before linking.')
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
    generated = shlex.quote(str(wrapper)) + ' %command%'
    old = json.loads(record_path.read_text()) if record_path.exists() else None
    if old and old.get('status') != 'restored':
        previous = old.get('previous')
    record = {'schema': 'megcfbt.steam-link/v1', 'appid': number,
              'package': str(root), 'launcher': str(launcher), 'generated': generated,
              'previous': previous, 'previous_source': 'user-preserved' if previous is not None else 'unavailable',
              'converter': meta.get('conversion', {}).get('converter'),
              'profile': meta.get('compatibility_profile'), 'mode': 'guided-native',
              'status': 'pending', 'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'installations': detected['installations'], 'wrapper': str(wrapper)}
    atomic_json(record_path, record)  # Recovery information precedes activation.
    # No environment identity is fabricated. Reject standalone/non-Steam launches.
    script = ('#!/bin/sh\nset -eu\n'
              f'if [ "${{SteamAppId:-}}" != "{number}" ] || [ "$#" -eq 0 ]; then\n'
              ' echo "Launch the original installed game through Steam. Rerun install-to-steam.sh to repair." >&2\n exit 1\nfi\n'
              f'if [ ! -f {shlex.quote(str(launcher))} ]; then\n'
              ' echo "Converted package moved or deleted. Restore Launch Options in Steam or rerun the installer at the new location." >&2\n exit 1\nfi\n'
              f'if [ ! -f {shlex.quote(str(root / ".megcfbt/steam_library.py"))} ]; then\n'
              ' echo "Bundled installer helper missing. Re-extract the conversion ZIP and rerun install-to-steam.sh to repair." >&2\n exit 1\nfi\n'
              f'python3 {shlex.quote(str(root / ".megcfbt/steam_library.py"))} --receipt {shlex.quote(str(record_path))} {shlex.quote(generated)}\n'
              f'exec {shlex.quote(str(launcher))}\n')
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
    if os.environ.get('SteamAppId') != str(record['appid']):
        raise ValueError('Genuine matching Steam launch context required')
    if installation(record['appid'])['state'] != 'installed':
        raise ValueError('Original Steam installation missing; rerun installer')
    record['status'] = 'launch-observed'
    record['launch_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    atomic_json(path, record)


def copy_command(command):
    for tool, args in [('wl-copy', []), ('xclip', ['-selection', 'clipboard']), ('xsel', ['--clipboard', '--input'])]:
        if shutil.which(tool):
            try:
                subprocess.run([tool, *args], input=command, text=True, timeout=3, check=True)
                print('Copied to clipboard.')
                return
            except (OSError, subprocess.SubprocessError):
                pass
    print('Clipboard unavailable; select and copy the command printed above.')


def restore(record_path, current, confirmed=False):
    record = json.loads(record_path.read_text())
    if current != record['generated']:
        raise ValueError('Steam launch settings changed. Preserve your current settings; automatic restoration is unavailable.')
    previous = record.get('previous')
    print('In Steam → game Properties → General → Launch Options, restore:')
    print(previous if previous is not None else 'Your separately preserved previous settings (no backup was available).')
    if confirmed:
        record['status'] = 'restored'
        atomic_json(record_path, record)
    return previous


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
        entries, reason = module.candidates(root, meta, detected)
    except (OSError, ValueError) as exc:
        print(f'Asset comparison unavailable: {exc}. Files linked: 0; disk space reclaimed: 0 bytes. Full assets retained.')
        return
    print(reason)
    if not entries:
        print('Files linked: 0. Disk space reclaimed: 0 bytes. Full converted assets retained.')
        return
    print(f'Byte-identical experimental assets: {len(entries)}. Steam files will never be modified.')
    print('Deduplication requires read-only bubblewrap launches. Backend gameplay acceptance is pending; no backend is advertised as safely deduplicated yet.')
    if choose('Enable experimental asset deduplication? [y/N]: ').lower() != 'y':
        print('Files linked: 0. Disk space reclaimed: 0 bytes. Full converted assets retained.')
        return
    try:
        result = module.enable(root, meta, detected, experimental=True)
    except (OSError, ValueError) as exc:
        if module.load(root):
            raise ValueError(f'Asset transaction requires recovery: {exc}. Rerun installer; original Steam files remain unchanged.') from exc
        print(f'Deduplication unavailable: {exc}. Files linked: 0; disk space reclaimed: 0 bytes. Full assets retained.')
        return
    print(f'Files linked: {result["linked"]}. Disk space reclaimed: {result["reclaimed_bytes"]} bytes' + ('.' if result['allocation_measured'] else ' (allocation unavailable; unmeasured savings not claimed).'))
    print('Reclaimed bytes measure observed free-space increases capped by released file allocations; delayed filesystem reclamation or other disk activity can affect the observation.')


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
            print('Compare Steam Launch Options with: ' + old['generated'])
            if assets().load(root):
                try:
                    assets().validate(root)
                    print('Linked asset hashes and source installation verified.')
                except ValueError as exc:
                    print('Asset repair required: ' + str(exc))
                    if choose('Restore/recover converted asset copies now? [y/N]: ').lower() == 'y':
                        assets().restore_assets(root)
            print('Gameplay, Steam Input, playtime and achievements remain separately unverified.')
            return False
        if answer == '3':
            current = input('Paste CURRENT Steam Launch Options to detect user changes: ')
            restore(path, current)
            if choose('Have you restored those options in Steam? Type RESTORED: ') == 'RESTORED':
                restore(path, current, True)
                data = assets().load(root)
                if data and data['status'] != 'restored' and choose('Also restore converted asset copies for standalone use? [y/N]: ').lower() == 'y':
                    assets().restore_assets(root)
            return False
        if answer != '2':
            return False
        if choose('Preserve any current Steam Launch Options before replacing them. Continue repair? [y/N]: ').lower() != 'y':
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
    print('Steam stays running; no configuration files or original game files will be modified.')
    print('Copy existing Launch Options from Steam before replacing them. This is a user-provided backup, not an automatic snapshot.')
    previous = input('Paste previous Launch Options (empty if none): ')
    record = prepare(root, meta, launcher, number, previous, path, detected)
    offer_dedup(root, meta, detected)
    print('\n' + record['generated'] + '\n')
    copy_command(record['generated'])
    print('Paste into the ORIGINAL game → Properties → General → Launch Options.')
    print('Disable forced compatibility tools for this native Linux launcher; do not select x86 Proton.')
    print('Launch the original game through Steam, then rerun installer → Verify existing link.')
    print('Setup pending. A launch observation does not verify gameplay, Steam Input, playtime or achievements.')
    return False


if __name__ == '__main__':
    import sys
    if len(sys.argv) == 4 and sys.argv[1] == '--receipt':
        try:
            receipt(Path(sys.argv[2]), sys.argv[3], Path(__file__).resolve().parent.parent)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise SystemExit(f'Steam link repair required: {exc}')
    elif len(sys.argv) == 3 and sys.argv[1] == '--inspect':
        print(json.dumps(installation(appid(sys.argv[2])), indent=2))
    else:
        raise SystemExit('Use install-to-steam.sh. Restoration is available in its existing-link menu.')
