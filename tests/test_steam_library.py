"""Synthetic Steam trees only; never discover or modify the developer's Steam."""
import json
import os
from pathlib import Path

import pytest

from megcfbt import steam_library as lib
from megcfbt.frame_package import write_frame_metadata
from megcfbt.nonsteam_package import installer_files
from megcfbt.steam_context import verified_source_identity


def manifest(root, number=504230, flags=4, folder='Celeste', content=True):
    apps = root / 'steamapps'
    apps.mkdir(parents=True, exist_ok=True)
    path = apps / f'appmanifest_{number}.acf'
    path.write_text(f'"AppState" {{ "appid" "{number}" "StateFlags" "{flags}" "installdir" "{folder}" }}')
    game = apps / 'common' / folder
    if content:
        game.mkdir(parents=True, exist_ok=True)
        (game / 'original.bin').write_bytes(b'original immutable fixture')
    return path, game


@pytest.fixture
def installed(tmp_path):
    root = tmp_path / 'Steam'
    manifest(root)
    (root / 'steamapps/libraryfolders.vdf').write_text('"libraryfolders" {}')
    return root


@pytest.fixture
def package(tmp_path):
    root = tmp_path / 'converted game'
    root.mkdir()
    launcher = root / 'launch.sh'
    launcher.write_text('#!/bin/sh\nexit 0\n')
    write_frame_metadata(root, name='Celeste', launcher_path=launcher, engine='CelesteFrame',
                         compatibility_profile='celeste-steam-xna-1.4.0.0')
    meta = json.loads((root / '.megcfbt/package.json').read_text())
    return root, launcher, meta


def test_installed_does_not_infer_ownership(installed):
    detected = lib.installation(504230, [installed])
    assert detected['state'] == 'installed'
    assert detected['ownership'] == 'unknown'


def test_secondary_library(tmp_path, installed):
    secondary = tmp_path / 'mounted SD card'
    manifest(secondary, number=413150, folder='Stardew Valley')
    path = str(secondary).replace('\\', '\\\\')
    (installed / 'steamapps/libraryfolders.vdf').write_text(f'"libraryfolders" {{ "1" {{ "path" "{path}" }} }}')
    result = lib.installation(413150, [installed])
    assert result['state'] == 'installed'
    assert result['installations'][0]['library'] == str(secondary.resolve())


@pytest.mark.parametrize('flags,content', [(4, False), (2, True), (1028, True)])
def test_stale_and_incomplete(tmp_path, flags, content):
    manifest(tmp_path, flags=flags, content=content)
    assert lib.installation(504230, [tmp_path])['state'] == 'incomplete'


def test_missing_and_unknown(installed, tmp_path):
    assert lib.installation(123, [installed])['state'] == 'missing'
    assert lib.installation(123, [tmp_path / 'absent'])['state'] == 'unknown'
    (installed / 'steamapps/libraryfolders.vdf').unlink()
    assert lib.installation(123, [installed])['state'] == 'unknown'


@pytest.mark.parametrize('number', [0, -1, True, '1;echo bad', 2**31, '504230\n'])
def test_invalid_appids(number):
    with pytest.raises(ValueError):
        lib.appid(number)


def test_conflicting_manifest(installed):
    path = installed / 'steamapps/appmanifest_504230.acf'
    path.write_text(path.read_text().replace('"appid" "504230"', '"appid" "123"'))
    assert lib.installation(504230, [installed])['state'] == 'unknown'


def test_duplicate_vdf_keys(installed):
    path = installed / 'steamapps/appmanifest_504230.acf'
    path.write_text('"AppState" { "appid" "504230" "appid" "123" }')
    assert lib.installation(504230, [installed])['state'] == 'unknown'


def test_identity_is_not_title_or_sidecar(package):
    _, _, meta = package
    assert lib.identity(meta) == 504230
    assert lib.identity({'name': 'Celeste', 'steam_appid': 504230}) is None
    meta['steam_identity'] = {'appid': 123, 'source': 'installed-source-manifest'}
    with pytest.raises(ValueError, match='conflicts'):
        lib.identity(meta)


def test_verified_source_identity(installed):
    source = installed / 'steamapps/common/Celeste'
    assert verified_source_identity(source)['appid'] == 504230
    with pytest.raises(ValueError, match='Conflicting'):
        verified_source_identity(source, 123)


def test_loose_sidecar_not_verified(tmp_path):
    (tmp_path / 'steam_appid.txt').write_text('504230')
    assert verified_source_identity(tmp_path) is None


@pytest.mark.parametrize('engine,target,profile,supported', [
    ('CelesteFrame', 'linux-aarch64', 'celeste-steam-xna-1.4.0.0', True),
    ('MonoFrame', 'linux-aarch64', 'stardew-steam-1.6.15-net6', True),
    ('CelesteFrame', 'linux-aarch64', None, False),
    ('GameMaker', 'linux-aarch64', None, True),
    ('LÖVE', 'linux-aarch64', None, True),
    ('AGS', 'linux-aarch64', None, True),
    ('godot', 'linux-aarch64', None, False),
    ('renpy', 'linux-aarch64', None, False),
    ('UnityFrame', 'windows-arm64-proton', None, False),
    ('STS2', 'linux-aarch64', None, False),
])
def test_capabilities(engine, target, profile, supported):
    assert lib.capability({'engine': engine, 'architecture': 'aarch64', 'target_platform': target, 'compatibility_profile': profile})[0] == supported


def test_prepare_idempotent_restore_and_original_preservation(tmp_path, package, installed):
    root, launcher, meta = package
    original = installed / 'steamapps/common/Celeste/original.bin'
    before = original.read_bytes()
    record_path = tmp_path / 'records/504230.json'
    detected = lib.installation(504230, [installed])
    record = lib.prepare(root, meta, launcher, 504230, 'old user options', record_path, detected)
    assert record['status'] == 'pending'
    wrapper = Path(record['wrapper'])
    assert wrapper.parent == record_path.parent
    body = wrapper.read_text()
    assert '%command%' in record['generated']
    assert 'exec ' in body and '--launch-link' in body and '"$@"' in body
    assert 'export SteamAppId' not in body
    assert 'Proton' not in body
    repeated = lib.prepare(root, meta, launcher, 504230, 'incorrect new backup', record_path, detected)
    assert repeated['previous'] == 'old user options'
    assert wrapper.read_text() == body
    from test_steam_live_link import Client
    client = Client('user edited options')
    with pytest.raises(ValueError, match='changed'):
        lib.restore_live(record_path, client)
    assert json.loads(record_path.read_text())['status'] == 'pending'
    client.options = record['generated']
    assert lib.restore_live(record_path, client) == 'old user options'
    assert json.loads(record_path.read_text())['status'] == 'restored'
    assert original.read_bytes() == before


def test_stable_wrapper_survives_deleted_package_for_repair(tmp_path, package, installed):
    import shutil
    root, launcher, meta = package
    record = lib.prepare(root, meta, launcher, 504230, '', tmp_path / 'records/504230.json', lib.installation(504230, [installed]))
    wrapper = Path(record['wrapper'])
    shutil.rmtree(root)
    assert wrapper.is_file()
    assert 'Converted package moved or deleted' in wrapper.read_text()


def test_move_repair_preserves_original_backup(tmp_path, package, installed):
    root, launcher, meta = package
    path = tmp_path / 'records/504230.json'
    detected = lib.installation(504230, [installed])
    lib.prepare(root, meta, launcher, 504230, 'original options', path, detected)
    moved = root.with_name('moved conversion')
    root.rename(moved)
    repaired = lib.prepare(moved, meta, moved / 'launch.sh', 504230, 'stale wrapper', path, detected)
    assert repaired['previous'] == 'original options'
    assert repaired['package'] == str(moved)


def test_missing_install_cannot_prepare(tmp_path, package):
    root, launcher, meta = package
    with pytest.raises(ValueError, match='must be installed'):
        lib.prepare(root, meta, launcher, 504230, '', tmp_path / 'record.json', {'state': 'missing'})
    assert not (tmp_path / 'record.json').exists()


def test_unsafe_package_path(package):
    root, _, meta = package
    meta['launcher'] = '../outside.sh'
    with pytest.raises(ValueError, match='unsafe'):
        lib.safe_file(root, meta['launcher'])


def symlink_or_skip(path, target, directory=False):
    try:
        path.symlink_to(target, target_is_directory=directory)
    except OSError:
        pytest.skip('OS does not permit creating symlinks')


def test_unsafe_installed_symlink(tmp_path):
    manifest_path, game = manifest(tmp_path / 'Steam', content=False)
    game.parent.mkdir(parents=True)
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    (elsewhere / 'data').write_text('data')
    symlink_or_skip(game, elsewhere, True)
    assert lib.installation(504230, [tmp_path / 'Steam'])['state'] == 'unknown'


def test_record_symlink_rejected(tmp_path):
    real = tmp_path / 'real'
    real.write_text('unrelated')
    link = tmp_path / 'record'
    symlink_or_skip(link, real)
    with pytest.raises(ValueError, match='symlink'):
        lib.atomic_json(link, {})
    assert real.read_text() == 'unrelated'


def test_interrupted_wrapper_write_retains_recovery(tmp_path, package, installed, monkeypatch):
    root, launcher, meta = package
    path = tmp_path / 'records/504230.json'
    replace = os.replace
    def interrupt(source, destination):
        if str(destination).endswith('.sh'):
            raise OSError('interrupted')
        return replace(source, destination)
    monkeypatch.setattr(os, 'replace', interrupt)
    with pytest.raises(OSError, match='interrupted'):
        lib.prepare(root, meta, launcher, 504230, 'backup', path, lib.installation(504230, [installed]))
    assert json.loads(path.read_text())['previous'] == 'backup'
    assert json.loads(path.read_text())['status'] == 'pending'
    assert not list((root / '.megcfbt').glob('.wrapper-*'))


def test_receipt_requires_real_context(tmp_path, package, installed, monkeypatch):
    root, launcher, meta = package
    path = tmp_path / 'records/504230.json'
    detected = lib.installation(504230, [installed])
    record = lib.prepare(root, meta, launcher, 504230, '', path, detected)
    with pytest.raises(ValueError, match='Package changed'):
        lib.receipt(path, record['generated'], root.with_name('obsolete package'))
    monkeypatch.delenv('SteamAppId', raising=False)
    with pytest.raises(ValueError, match='context'):
        lib.receipt(path, record['generated'])
    monkeypatch.setenv('SteamAppId', '504230')
    monkeypatch.setattr(lib, 'installation', lambda number: detected)
    lib.receipt(path, record['generated'])
    assert json.loads(path.read_text())['status'] == 'launch-observed'


def test_bundled_dependency_and_nonsteam_preserved():
    files = installer_files()
    assert files['.megcfbt/steam_library.py'][0] == Path(lib.__file__).read_bytes()
    compile(files['.megcfbt/steam_library.py'][0], 'bundled.py', 'exec')
    installer = files['.megcfbt/install-to-steam.py'][0].decode()
    assert 'steam://addnonsteamgame/' in installer
    assert 'apply_artwork(found)' in installer
    assert 'find_shortcuts(launcher' in installer


def test_missing_game_opens_only_official_steam_flow(package, monkeypatch, capsys, tmp_path):
    root, launcher, _ = package
    monkeypatch.setattr(lib, 'records', lambda: tmp_path / 'records')
    monkeypatch.setattr(lib, 'installation', lambda n: {'state': 'missing', 'errors': []})
    answers = iter(['2', ''])
    monkeypatch.setattr('builtins.input', lambda prompt: next(answers))
    calls = []
    monkeypatch.setattr(lib.subprocess, 'run', lambda args, **kw: calls.append(args))
    assert lib.menu(root, 'Celeste', launcher) is False
    assert calls == [['xdg-open', 'steam://install/504230']]
    assert 'original Steam game must be installed through Steam on this Steam Frame' in capsys.readouterr().out
    assert not (tmp_path / 'records').exists()


@pytest.mark.parametrize('state', ['installed', 'missing'])
def test_nonsteam_is_primary_without_live_link_or_dedup(package, monkeypatch, capsys, tmp_path, state):
    root, launcher, _ = package
    monkeypatch.setattr(lib, 'records', lambda: tmp_path / 'records')
    monkeypatch.setattr(lib, 'installation', lambda n: {'state': state, 'errors': []})
    monkeypatch.setattr(lib, 'live_client', lambda: pytest.fail('Non-Steam selection must not change original launch options'))
    monkeypatch.setattr(lib, 'offer_dedup', lambda *a: pytest.fail('Non-Steam selection must not deduplicate'))
    prompts = []
    def choose(prompt):
        prompts.append(prompt)
        return '1'
    monkeypatch.setattr('builtins.input', choose)
    assert lib.menu(root, 'Celeste', launcher) is True
    assert prompts[-1].startswith('1. Add as non-Steam game (recommended)\n2. [experimental]')
    assert '[experimental]' in capsys.readouterr().out
    assert not (tmp_path / 'records').exists()


def test_install_flow_failure_allows_rescan_or_cancel(package, monkeypatch, capsys, tmp_path):
    root, launcher, _ = package
    monkeypatch.setattr(lib, 'records', lambda: tmp_path / 'records')
    monkeypatch.setattr(lib, 'installation', lambda n: {'state': 'missing', 'errors': []})
    answers = iter(['2', '3'])
    monkeypatch.setattr('builtins.input', lambda prompt: next(answers))
    def failed(*args, **kwargs):
        raise lib.subprocess.CalledProcessError(3, args[0])
    monkeypatch.setattr(lib.subprocess, 'run', failed)
    assert lib.menu(root, 'Celeste', launcher) is False
    assert 'could not be opened' in capsys.readouterr().out
    assert not (tmp_path / 'records').exists()


@pytest.mark.parametrize('number', [0, -1, True, '504230', 2**31])
def test_install_flow_rejects_invalid_appid(number, monkeypatch):
    monkeypatch.setattr(lib.subprocess, 'run', lambda *a, **kw: pytest.fail('invalid URI dispatched'))
    with pytest.raises(ValueError, match='AppID'):
        lib.open_install_flow(number)


def test_frame_install_flow_forwards_without_bootstrap(tmp_path, monkeypatch):
    import stat
    from types import SimpleNamespace
    config = tmp_path / '.steam'
    helper = config / 'root/steamrtarm64/steam'
    helper.parent.mkdir(parents=True)
    helper.write_bytes(b'fixture')
    (config / 'steam.pid').write_text('123')
    proc = tmp_path / 'proc/123'
    proc.mkdir(parents=True)
    (proc / 'comm').write_text('steam\n')
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    original_stat, original_lstat = Path.stat, Path.lstat
    monkeypatch.setattr(Path, 'stat', lambda self, **kw: SimpleNamespace(st_uid=42) if self == Path('/proc/123') else original_stat(self, **kw))
    monkeypatch.setattr(Path, 'lstat', lambda self, **kw: SimpleNamespace(st_uid=42, st_mode=stat.S_IFIFO | 0o600) if self == config / 'steam.pipe' else original_lstat(self, **kw))
    original_read = Path.read_text
    monkeypatch.setattr(Path, 'read_text', lambda self, **kw: 'steam\n' if self == Path('/proc/123/comm') else original_read(self, **kw))
    monkeypatch.setattr(lib.os, 'getuid', lambda: 42, raising=False)
    monkeypatch.setattr(lib.os, 'access', lambda *args: True)
    calls = []
    monkeypatch.setattr(lib.subprocess, 'run', lambda args, **kw: calls.append((args, kw)))
    lib.open_install_flow(2121980)
    assert calls == [([str(helper), 'steam://install/2121980'], {'check': True, 'timeout': 15})]
    # A stale PID must never execute the forwarding helper or bootstrap Steam.
    (config / 'steam.pid').write_text('-1')
    lib.open_install_flow(2121980)
    assert calls[-1][0] == ['xdg-open', 'steam://install/2121980']


def test_conflicting_identity_still_offers_nonsteam(package, monkeypatch, capsys):
    root, launcher, meta = package
    meta['steam_identity'] = {'appid': 123, 'source': 'installed-source-manifest'}
    (root / '.megcfbt/package.json').write_text(json.dumps(meta))
    monkeypatch.setattr('builtins.input', lambda prompt: '1')
    assert lib.menu(root, 'Celeste', launcher) is True
    assert 'No trustworthy Steam AppID' in capsys.readouterr().out
