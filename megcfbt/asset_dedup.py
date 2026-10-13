"""Experimental post-extraction asset links with journal and read-only launches.

Only the converted tree is mutated. No hardlinks, writes or chmods at the source.
Backend gameplay acceptance is deliberately separate from filesystem tests.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

SCHEMA = 'megcfbt.asset-links/v1'
DENIED = {'saves', 'save', 'mods', 'config', 'userdata', 'userconfig', 'runtime', 'patches'}
PROFILES = {('CelesteFrame', 'celeste-steam-xna-1.4.0.0'),
            ('MonoFrame', 'stardew-steam-1.6.15-net6')}


def library():
    try:
        from . import steam_library
    except ImportError:
        import steam_library
    return steam_library


def manifest_path(root):
    return root / '.megcfbt/asset-links.json'


@contextmanager
def transaction(root):
    path = path_inside(root, '.megcfbt/asset-dedup.lock')
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        if os.name == 'posix':
            import fcntl
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError('Another asset operation is active; retry after it finishes') from exc
        yield
    finally:
        os.close(descriptor)


def sync_directory(path):
    if os.name == 'posix':
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def path_inside(root, relative, *, linked=False):
    """Reject parent traversal and every intermediate symlink, including in-tree."""
    if not isinstance(relative, str) or not relative or '\\' in relative:
        raise ValueError('Unsafe asset path')
    parts = relative.split('/')
    if any(part in {'', '.', '..'} for part in parts) or Path(relative).is_absolute():
        raise ValueError('Unsafe asset path')
    at = root
    for index, part in enumerate(parts):
        at = at / part
        if at.is_symlink() and not (linked and index == len(parts) - 1):
            raise ValueError('Symlink traversal in asset path')
    if not at.parent.resolve().is_relative_to(root.resolve()):
        raise ValueError('Asset escaped package/source boundary')
    return at


def readonly_open(path):
    """Do not update source atime; lacking permission fails closed on Linux."""
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
    if sys.platform == 'linux':
        flags |= os.O_NOATIME
    return os.fdopen(os.open(path, flags), 'rb')


def digest(path, *, source=False):
    opener = readonly_open if source else lambda p: p.open('rb')
    with opener(path) as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError('Asset is not a regular file')
        sha = hashlib.sha256()
        while chunk := stream.read(1024 * 1024):
            sha.update(chunk)
        after = os.fstat(stream.fileno())
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        if any(getattr(before, key) != getattr(after, key) for key in fields):
            raise ValueError('Asset changed while hashing')
        return sha.hexdigest()


def allocated(path):
    value = getattr(path.lstat(), 'st_blocks', None)
    return value * 512 if value is not None else None


def link_matches(target, source):
    if not target.is_symlink():
        return False
    value = os.readlink(target)
    # Windows synthetic fixtures expose the same absolute link with an NT
    # namespace prefix. Real Linux linking requires the exact recorded target.
    if os.name == 'nt' and value.startswith('\\\\?\\'):
        value = value[4:]
    return value == str(source)


def candidates(root, meta, detected):
    if detected.get('state') != 'installed':
        raise ValueError('Original Steam game must be installed locally before deduplication')
    if (meta.get('engine'), meta.get('compatibility_profile')) not in PROFILES:
        return [], 'No experimental read-only asset allowlist for this backend; full converted package retained.'
    if library().identity(meta) is None or not library().capability(meta)[0]:
        raise ValueError('Deduplication requires a validated native linking identity')
    payload = meta.get('payload')
    base = path_inside(root, payload) if payload else root
    game = base / 'game'
    content = game / 'Content'
    path_inside(root, content.relative_to(root).as_posix())
    if not content.is_dir():
        return [], 'Converted Content directory missing; no storage savings possible.'
    result = []
    # Compiled static XNA/MonoGame content only. Scripts, executables, packs,
    # patched resources, configs, saves and even other Content extensions stay.
    for target in sorted(content.rglob('*.xnb')):
        relative = target.relative_to(root).as_posix()
        path_inside(root, relative)
        asset = target.relative_to(game).as_posix()
        if any(part.lower() in DENIED for part in Path(asset).parts):
            continue
        if not target.is_file() or target.stat().st_nlink != 1:
            continue
        with target.open('rb') as stream:
            if stream.read(3) != b'XNB':
                continue
        for installation in detected.get('installations', []):
            original = Path(installation['game'])
            if root.is_relative_to(original) or original.is_relative_to(root):
                raise ValueError('Converted package and original installation must be separate')
            source = path_inside(original, asset)
            if not source.is_file() or source.stat().st_size != target.stat().st_size:
                continue
            sha = digest(source, source=True)
            if sha != digest(target):
                continue
            result.append({'path': relative, 'source_root': str(original),
                           'source_path': asset, 'source': str(source), 'sha256': sha,
                           'size': target.stat().st_size, 'allocated': allocated(target),
                           'mode': stat.S_IMODE(target.stat().st_mode), 'status': 'planned',
                           'backup': relative + '.megcfbt-backup-' + uuid.uuid4().hex})
            break
    return result, 'Experimental Content/*.xnb candidates; backend gameplay/write-safety acceptance is pending.'


def isolated_command(root, source_roots, command, executable=None):
    executable = executable or shutil.which('bwrap')
    if sys.platform != 'linux' or not executable:
        raise ValueError('Read-only bubblewrap isolation unavailable; keep full converted assets')
    # Keep Steam's PID/network/IPC context. Root is read-only; package, temp,
    # devices and existing session sockets retain the access native games need.
    args = [executable, '--ro-bind', '/', '/', '--bind', str(root), str(root),
            '--bind', '/tmp', '/tmp', '--dev-bind', '/dev', '/dev', '--proc', '/proc']
    session = os.environ.get('XDG_RUNTIME_DIR')
    if session and Path(session).is_absolute() and Path(session).is_dir():
        args += ['--bind', session, session]
    for source in sorted(set(source_roots)):
        args += ['--ro-bind', source, source]
    return args + ['--', *command]


def probe_isolation(root):
    """Try writing a synthetic read-only file, never an original Steam asset."""
    with tempfile.TemporaryDirectory(prefix='.isolation-check-', dir=root / '.megcfbt') as temporary:
        directory = Path(temporary)
        sample = directory / 'sample'
        sample.write_bytes(b'unchanged')
        script = ('import errno, pathlib, sys\np=pathlib.Path(sys.argv[1])\n'
                  'try:\n p.write_bytes(b"unsafe")\nexcept OSError as e:\n'
                  ' sys.exit(0 if e.errno == errno.EROFS else 2)\nsys.exit(3)\n')
        executable = shutil.which('bwrap')
        command = isolated_command(root, [str(directory)], [sys.executable, '-c', script, str(sample)], executable)
        result = subprocess.run(command, capture_output=True, timeout=15)
        if result.returncode or sample.read_bytes() != b'unchanged':
            raise ValueError('Read-only isolation check failed; converted assets were not deduplicated')
        return str(Path(executable).resolve())


def load(root):
    path = manifest_path(root)
    if not path.exists():
        return None
    path_inside(root, '.megcfbt/asset-links.json')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('schema') != SCHEMA or not isinstance(data.get('entries'), list):
        raise ValueError('Invalid asset-link manifest; re-extract the original conversion ZIP')
    library().appid(data.get('appid'))
    if data.get('status') not in {'preparing', 'active', 'restoring', 'restored'}:
        raise ValueError('Invalid asset transaction status; recover from the original ZIP')
    for entry in data['entries']:
        if not isinstance(entry, dict):
            raise ValueError('Invalid asset entry')
        target = path_inside(root, entry.get('path'), linked=True)
        relative = entry.get('source_path', '')
        if not relative.startswith('Content/') or not relative.endswith('.xnb') or any(p.lower() in DENIED for p in Path(relative).parts):
            raise ValueError('Unapproved source asset in manifest')
        parts = target.relative_to(root).parts
        if ('game', 'Content') not in tuple(zip(parts, parts[1:])) or target.suffix != '.xnb':
            raise ValueError('Unapproved converted asset in manifest')
        if not re.fullmatch(re.escape(entry['path']) + r'\.megcfbt-backup-[0-9a-f]{32}', entry.get('backup', '')):
            raise ValueError('Unsafe asset recovery path')
        if not re.fullmatch(r'[0-9a-f]{64}', entry.get('sha256', '')):
            raise ValueError('Invalid recorded asset hash')
    # A moved package can be restored using relative paths; active execution
    # requires relinking so all recorded identities/launcher locations agree.
    return data


def save(root, data):
    library().atomic_json(manifest_path(root), data)


def source_for(entry, detected):
    roots = {item['game'] for item in detected.get('installations', [])}
    if detected.get('state') != 'installed' or entry['source_root'] not in roots:
        raise ValueError('Steam installation disappeared. Restore assets from the original conversion ZIP or relink a validated installation.')
    source = path_inside(Path(entry['source_root']), entry['source_path'])
    if str(source) != entry['source'] or not source.is_file() or source.stat().st_size != entry['size'] or digest(source, source=True) != entry['sha256']:
        raise ValueError('Steam asset changed or disappeared. Do not launch; restore from the original conversion ZIP, or reconvert and relink.')
    return source


def validate(root, data=None, detected=None):
    data = data or load(root)
    if not data or data['status'] == 'restored':
        return []
    if data['status'] != 'active' or data['package'] != str(root):
        raise ValueError('Asset deduplication is interrupted or the package moved. Rerun installer to restore/recover assets before launching.')
    detected = detected or library().installation(data['appid'])
    roots = []
    for entry in data['entries']:
        if entry['status'] != 'linked':
            raise ValueError('Incomplete asset transaction; restore/recover before launching')
        source = source_for(entry, detected)
        target = path_inside(root, entry['path'], linked=True)
        if not link_matches(target, source):
            raise ValueError('Converted asset link changed/broken. Rerun installer to recover or re-extract the conversion ZIP.')
        roots.append(entry['source_root'])
    return sorted(set(roots))


def summary(data):
    entries = [entry for entry in data['entries'] if entry['status'] == 'linked']
    exact = all(entry.get('reclaimed') is not None for entry in entries)
    return {'linked': len(entries), 'reclaimed_bytes': sum(entry.get('reclaimed') or 0 for entry in entries),
            'allocation_measured': exact}


def replace_bytes(path, content, mode):
    fd, temporary = tempfile.mkstemp(prefix='.asset-write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install_guard(root, meta, data):
    launcher = library().safe_file(root, meta['launcher'])
    backup = path_inside(root, meta['launcher'] + '.megcfbt-before-dedup')
    if backup.exists():
        raise ValueError('Unexpected launcher backup; recover deduplication before retrying')
    original = launcher.read_bytes()
    data['launcher'] = meta['launcher']
    data['launcher_backup'] = backup.relative_to(root).as_posix()
    data['launcher_sha256'] = hashlib.sha256(original).hexdigest()
    data['launcher_mode'] = stat.S_IMODE(launcher.stat().st_mode)
    script = ('#!/bin/sh\nset -eu\nROOT="$(cd "$(dirname "$0")" && pwd)"\n'
              'exec python3 "$ROOT/.megcfbt/asset_dedup.py" --launch "$ROOT" "$@"\n').encode()
    if meta['launcher'] != 'launch.sh':
        raise ValueError('Experimental deduplication requires the standard root launch.sh contract')
    data['guard_sha256'] = hashlib.sha256(script).hexdigest()
    save(root, data)
    replace_bytes(backup, original, data['launcher_mode'])
    replace_bytes(launcher, script, 0o755)


def enable(root, meta, detected, *, experimental=False):
    root = root.resolve()
    with transaction(root):
        return _enable(root, meta, detected, experimental=experimental)


def _enable(root, meta, detected, *, experimental=False):
    root = root.resolve()
    data = load(root)
    if data and data['status'] != 'restored':
        validate(root, data, detected)
        return summary(data)
    if not experimental:
        return {'linked': 0, 'reclaimed_bytes': 0, 'allocation_measured': True,
                'reason': 'No backend is advertised as safely deduplicated before Steam Frame gameplay acceptance. Full package retained.'}
    entries, reason = candidates(root, meta, detected)
    if not entries:
        return {'linked': 0, 'reclaimed_bytes': 0, 'allocation_measured': True, 'reason': reason + ' No byte-identical eligible assets; no storage savings.'}
    executable = probe_isolation(root)
    data = {'schema': SCHEMA, 'appid': library().identity(meta), 'package': str(root),
            'package_identity': meta.get('conversion'), 'profile': meta.get('compatibility_profile'),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'status': 'preparing', 'isolation': executable, 'entries': entries}
    save(root, data)
    install_guard(root, meta, data)  # Guard refuses partial state before any links exist.
    for entry in entries:
        target = path_inside(root, entry['path'])
        source = source_for(entry, detected)
        if target.stat().st_nlink != 1 or target.stat().st_size != entry['size'] or digest(target) != entry['sha256']:
            raise ValueError('Converted asset changed during comparison; recovery manifest retained')
        backup = path_inside(root, entry['backup'])
        if backup.exists():
            raise ValueError('Unexpected asset backup; recover before retrying')
        entry['status'] = 'replacing'
        save(root, data)
        os.replace(target, backup)
        sync_directory(target.parent)
        # Keep the complete converted copy until the replacement is verified.
        temporary = target.with_name('.' + target.name + '.link-' + uuid.uuid4().hex)
        try:
            temporary.symlink_to(source)
            os.replace(temporary, target)
            sync_directory(target.parent)
            if not link_matches(target, source) or digest(source, source=True) != entry['sha256']:
                raise ValueError('Replacement source changed; converted backup retained')
            entry['status'] = 'linked'
            save(root, data)
            blocks = allocated(target)
            free_before = shutil.disk_usage(root).free
            backup.unlink()  # Exclusively converted package, after verified link + journal.
            sync_directory(backup.parent)
            free_after = shutil.disk_usage(root).free
            released = max(0, entry['allocated'] - blocks) if entry['allocated'] is not None and blocks is not None else None
            entry['released_allocation'] = released
            entry['observed_free_increase'] = max(0, free_after - free_before)
            entry['reclaimed'] = min(released, entry['observed_free_increase']) if released is not None else None
            save(root, data)
        finally:
            if temporary.is_symlink():
                temporary.unlink()
    data['status'] = 'active'
    save(root, data)
    validate(root, data, detected)
    return summary(data)


def restore_assets(root, detected=None):
    root = root.resolve()
    with transaction(root):
        return _restore_assets(root, detected)


def _restore_assets(root, detected=None):
    """Restore ordinary converted copies. Changed Steam targets never supply bytes."""
    root = root.resolve()
    data = load(root)
    if not data or data['status'] == 'restored':
        return 0
    detected = detected or library().installation(data['appid'])
    data['status'] = 'restoring'
    save(root, data)
    count = 0
    for entry in data['entries']:
        target = path_inside(root, entry['path'], linked=True)
        backup = path_inside(root, entry['backup'])
        if target.exists() and not target.is_symlink():
            if digest(target) != entry['sha256']:
                raise ValueError('Converted asset has user changes; recovery will not overwrite it')
        elif backup.is_file():
            if digest(backup) != entry['sha256']:
                raise ValueError('Recovery backup changed; no overwrite performed')
            os.replace(backup, target)
            sync_directory(target.parent)
            count += 1
        else:
            if target.is_symlink() and not link_matches(target, entry['source']):
                raise ValueError('User changed asset link; restoration refused')
            source = source_for(entry, detected)
            fd, temporary = tempfile.mkstemp(prefix='.restore-asset-', dir=target.parent)
            try:
                with os.fdopen(fd, 'wb') as output, readonly_open(source) as input_file:
                    shutil.copyfileobj(input_file, output, 1024 * 1024)
                    output.flush()
                    os.fsync(output.fileno())
                if digest(Path(temporary)) != entry['sha256']:
                    raise ValueError('Source changed during restoration; linked file left intact')
                os.chmod(temporary, entry['mode'])
                os.replace(temporary, target)
                sync_directory(target.parent)
                count += 1
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        if backup.is_file():
            if digest(backup) != entry['sha256']:
                raise ValueError('Unexpected recovery backup; retained')
            backup.unlink()
            sync_directory(backup.parent)
        entry['status'] = 'restored'
        save(root, data)
    if data.get('launcher_backup'):
        launcher = path_inside(root, data['launcher'])
        backup = path_inside(root, data['launcher_backup'])
        current = digest(launcher)
        if current not in {data['guard_sha256'], data['launcher_sha256']}:
            raise ValueError('Launcher changed by user; assets restored but launcher needs manual reconciliation')
        if current != data['launcher_sha256']:
            if not backup.is_file() or digest(backup) != data['launcher_sha256']:
                raise ValueError('Launcher backup unavailable; re-extract the original conversion ZIP')
            replace_bytes(launcher, backup.read_bytes(), data['launcher_mode'])
        if backup.is_file():
            backup.unlink()
    data['status'] = 'restored'
    save(root, data)
    return count


def launch(root, args):
    data = load(root)
    roots = validate(root, data)
    if not data or data['status'] != 'active':
        raise ValueError('Inactive or interrupted deduplication; rerun installer to recover')
    original = path_inside(root, data['launcher_backup'])
    if digest(original) != data['launcher_sha256']:
        raise ValueError('Converted launcher changed; repair before launching')
    command = isolated_command(root, roots, [str(original), *args], data['isolation'])
    os.execv(command[0], command)


if __name__ == '__main__':
    try:
        if len(sys.argv) >= 3 and sys.argv[1] == '--launch':
            launch(Path(sys.argv[2]).resolve(), sys.argv[3:])
        else:
            raise ValueError('Use install-to-steam.sh to verify, recover or restore asset links')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f'Asset-link safety check: {exc}')
