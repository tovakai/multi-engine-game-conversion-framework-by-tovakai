"""Synthetic assets only. Linux-only symlink/isolation checks also run on Frame."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys

import pytest

from megcfbt import asset_dedup as dedup
from megcfbt import steam_library as lib
from megcfbt.nonsteam_package import installer_files


@pytest.fixture
def trees(tmp_path, monkeypatch):
    root = tmp_path / 'converted'
    original = tmp_path / 'original Steam game'
    target = root / 'game/Content/Maps/map.xnb'
    source = original / 'Content/Maps/map.xnb'
    target.parent.mkdir(parents=True)
    source.parent.mkdir(parents=True)
    payload = b'XNB' + b'identical compiled immutable content' * 1024
    target.write_bytes(payload)
    source.write_bytes(payload)
    (root / '.megcfbt').mkdir()
    launcher = root / 'launch.sh'
    launcher.write_text('#!/bin/sh\nexit 0\n')
    launcher.chmod(0o755)
    meta = {'engine': 'CelesteFrame', 'architecture': 'aarch64', 'target_platform': 'linux-aarch64',
            'compatibility_profile': 'celeste-steam-xna-1.4.0.0', 'launcher': 'launch.sh',
            'conversion': {'converter': {'version': '0.1.1.0.dev1+fixture'}}}
    detected = {'state': 'installed', 'installations': [{'game': str(original)}]}
    monkeypatch.setattr(lib, 'installation', lambda number: detected)
    monkeypatch.setattr(dedup, 'probe_isolation', lambda package: '/usr/bin/bwrap')
    return root, original, target, source, meta, detected


def metadata(path):
    info = path.stat()
    result = (info.st_mode, info.st_size, info.st_ino, info.st_mtime_ns, info.st_ctime_ns)
    return result + (info.st_atime_ns,) if sys.platform == 'linux' else result


def require_symlinks(root):
    try:
        check = root / 'check-symlink'
        check.symlink_to(root / 'launch.sh')
        check.unlink()
    except OSError:
        pytest.skip('OS does not permit creating symlinks')


def test_identical_candidates_and_source_metadata_unchanged(trees):
    root, original, target, source, meta, detected = trees
    before = metadata(source)
    candidates, _ = dedup.candidates(root, meta, detected)
    assert len(candidates) == 1
    assert candidates[0]['sha256'] == hashlib.sha256(target.read_bytes()).hexdigest()
    assert metadata(source) == before
    assert not source.is_symlink() and not target.is_symlink()


def test_modified_and_unmatched_assets_remain(trees):
    root, original, target, source, meta, detected = trees
    source.write_bytes(b'XNB' + b'different' * 1024)
    (target.parent / 'settings.json').write_text('{}')
    (target.parent / 'patched.dll').write_bytes(b'patched')
    (target.parent / 'script.rpy').write_text('script')
    result = dedup.enable(root, meta, detected, experimental=True)
    assert result['linked'] == result['reclaimed_bytes'] == 0
    assert target.is_file() and not target.is_symlink()
    assert not dedup.manifest_path(root).exists()


def test_equal_size_different_hash_not_linked(trees):
    root, original, target, source, meta, detected = trees
    data = bytearray(source.read_bytes())
    data[-1] ^= 1
    source.write_bytes(data)
    assert dedup.candidates(root, meta, detected)[0] == []


def test_no_backend_advertised_safe_without_hardware_acceptance(trees):
    root, _, target, _, meta, detected = trees
    result = dedup.enable(root, meta, detected)
    assert result['linked'] == 0 and 'acceptance' in result['reason']
    assert not target.is_symlink()


@pytest.mark.parametrize('engine', ['renpy', 'godot', 'GameMaker', 'UnityFrame', 'rpgmaker_mv', 'LÖVE', 'AGS'])
def test_unsafe_or_unaudited_backend_keeps_full_assets(trees, engine):
    root, _, target, _, meta, detected = trees
    meta['engine'] = engine
    assert dedup.candidates(root, meta, detected)[0] == []
    assert target.is_file() and not target.is_symlink()


def test_missing_installation(trees):
    root, _, target, _, meta, _ = trees
    with pytest.raises(ValueError, match='installed locally'):
        dedup.enable(root, meta, {'state': 'missing'}, experimental=True)
    assert target.is_file()


def test_link_repeat_restore_preserves_original(trees):
    root, original, target, source, meta, detected = trees
    require_symlinks(root)
    before = metadata(source)
    original_bytes = target.read_bytes()
    launch_bytes = (root / 'launch.sh').read_bytes()
    first = dedup.enable(root, meta, detected, experimental=True)
    assert first['linked'] == 1
    assert target.is_symlink() and os.readlink(target) == str(source)
    assert source.stat().st_nlink == 1
    assert dedup.validate(root, detected=detected) == [str(original)]
    assert metadata(source) == before
    assert dedup.enable(root, meta, detected, experimental=True) == first
    assert len(dedup.load(root)['entries']) == 1
    assert dedup.restore_assets(root, detected) == 1
    assert not target.is_symlink() and target.read_bytes() == original_bytes
    assert (root / 'launch.sh').read_bytes() == launch_bytes
    assert metadata(source) == before
    assert dedup.restore_assets(root, detected) == 0


@pytest.mark.parametrize('update', ['changed', 'deleted'])
def test_steam_updates_and_broken_links_block_launch_and_restore(trees, update):
    root, _, target, source, meta, detected = trees
    require_symlinks(root)
    dedup.enable(root, meta, detected, experimental=True)
    if update == 'deleted':
        source.unlink()  # synthetic simulated Steam update, never actual installed games
    else:
        source.write_bytes(b'XNB incompatible update')
    with pytest.raises(ValueError, match='changed|disappeared'):
        dedup.validate(root, detected=detected)
    with pytest.raises(ValueError, match='changed|disappeared'):
        dedup.restore_assets(root, detected)
    assert target.is_symlink()
    assert dedup.load(root)['status'] == 'restoring'


def test_interrupted_replacement_recovers_converted_backup(trees, monkeypatch):
    root, _, target, source, meta, detected = trees
    require_symlinks(root)
    original_bytes = target.read_bytes()
    before = metadata(source)
    symlink = Path.symlink_to
    def interrupted(path, destination, **kwargs):
        raise OSError('simulated interruption')
    monkeypatch.setattr(Path, 'symlink_to', interrupted)
    with pytest.raises(OSError, match='interruption'):
        dedup.enable(root, meta, detected, experimental=True)
    assert not target.exists()
    record = dedup.load(root)
    assert record['status'] == 'preparing'
    backup = root / record['entries'][0]['backup']
    assert backup.read_bytes() == original_bytes
    with pytest.raises(ValueError, match='interrupted'):
        dedup.validate(root, detected=detected)
    monkeypatch.setattr(Path, 'symlink_to', symlink)
    assert dedup.restore_assets(root, {'state': 'missing', 'installations': []}) == 1
    assert target.read_bytes() == original_bytes
    assert metadata(source) == before


def test_readonly_isolation_required_before_any_asset_change(trees, monkeypatch):
    root, _, target, _, meta, detected = trees
    def failure(package):
        raise ValueError('isolation failed')
    monkeypatch.setattr(dedup, 'probe_isolation', failure)
    with pytest.raises(ValueError, match='isolation'):
        dedup.enable(root, meta, detected, experimental=True)
    assert target.is_file() and not target.is_symlink()
    assert not dedup.manifest_path(root).exists()


def test_unsafe_source_symlink_rejected(trees):
    root, original, target, source, meta, detected = trees
    require_symlinks(root)
    other = original / 'elsewhere.xnb'
    source.rename(other)
    source.symlink_to(other)
    with pytest.raises(ValueError, match='Symlink'):
        dedup.candidates(root, meta, detected)
    assert not target.is_symlink()


@pytest.mark.parametrize('path', ['../outside.xnb', '/absolute', 'game/../outside.xnb', 'game\\Content\\asset.xnb'])
def test_unsafe_paths(trees, path):
    with pytest.raises(ValueError, match='Unsafe'):
        dedup.path_inside(trees[0], path)


def test_user_asset_edits_not_overwritten(trees):
    root, _, target, _, meta, detected = trees
    require_symlinks(root)
    dedup.enable(root, meta, detected, experimental=True)
    target.unlink()
    target.write_bytes(b'user modified converted asset')
    with pytest.raises(ValueError, match='user changes'):
        dedup.restore_assets(root, detected)
    assert target.read_bytes() == b'user modified converted asset'


def test_nonsteam_package_contains_standalone_guard_dependency():
    files = installer_files()
    assert files['.megcfbt/asset_dedup.py'][0] == Path(dedup.__file__).read_bytes()
    assert 'steam://addnonsteamgame/' in files['.megcfbt/install-to-steam.py'][0].decode()


def test_exclusions_even_when_content_matches(trees):
    root, original, target, source, meta, detected = trees
    for name in ['save', 'config', 'mods']:
        converted = root / 'game/Content' / name / 'mutable.xnb'
        steam = original / 'Content' / name / 'mutable.xnb'
        converted.parent.mkdir()
        steam.parent.mkdir()
        converted.write_bytes(target.read_bytes())
        steam.write_bytes(target.read_bytes())
    assert len(dedup.candidates(root, meta, detected)[0]) == 1


def test_wrapped_zip_layout(trees):
    root, _, target, _, meta, detected = trees
    (root / 'payload').mkdir()
    (root / 'game').rename(root / 'payload/game')
    meta['payload'] = 'payload'
    entries, _ = dedup.candidates(root, meta, detected)
    assert entries[0]['path'] == 'payload/game/Content/Maps/map.xnb'


def test_interrupted_after_link_before_copy_deletion(trees, monkeypatch):
    root, _, target, source, meta, detected = trees
    require_symlinks(root)
    before = metadata(source)
    unlink = Path.unlink
    def interrupted(path, *args, **kwargs):
        if '.megcfbt-backup-' in path.name:
            raise OSError('simulated crash before backup deletion')
        return unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', interrupted)
    with pytest.raises(OSError, match='crash'):
        dedup.enable(root, meta, detected, experimental=True)
    record = dedup.load(root)
    assert record['status'] == 'preparing'
    assert (root / record['entries'][0]['backup']).is_file()
    source.unlink()  # simulated external Steam removal; recovery still has copy
    monkeypatch.setattr(Path, 'unlink', unlink)
    assert dedup.restore_assets(root, {'state': 'missing', 'installations': []}) == 1
    assert not target.is_symlink()


def test_no_unmeasured_or_logical_size_storage_claim(trees, monkeypatch):
    root, _, target, _, meta, detected = trees
    require_symlinks(root)
    class Usage:
        free = 1000000
    monkeypatch.setattr(dedup.shutil, 'disk_usage', lambda path: Usage())
    result = dedup.enable(root, meta, detected, experimental=True)
    assert result['linked'] == 1 and result['reclaimed_bytes'] == 0
    assert dedup.load(root)['entries'][0]['observed_free_increase'] == 0


@pytest.mark.skipif(sys.platform != 'linux' or not shutil.which('bwrap'), reason='requires Linux bubblewrap')
def test_attempted_write_to_linked_asset_denied(trees, monkeypatch):
    root, original, target, source, meta, detected = trees
    # Use actual mount isolation in a synthetic fixture, including unchanged atime.
    monkeypatch.undo()
    before = metadata(source)
    dedup.enable(root, meta, detected, experimental=True)
    script = ('import errno,pathlib,sys\ntry:\n pathlib.Path(sys.argv[1]).write_bytes(b"unsafe")\n'
              'except OSError as e:\n sys.exit(0 if e.errno == errno.EROFS else 2)\nsys.exit(3)')
    command = dedup.isolated_command(root, [str(original)], [sys.executable, '-c', script, str(target)])
    import subprocess
    result = subprocess.run(command, capture_output=True)
    assert result.returncode == 0, result.stderr.decode()
    assert metadata(source) == before
