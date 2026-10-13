import json
import os
from pathlib import Path

import pytest

from megcfbt import steam_library as lib
from megcfbt import steam_client
from test_steam_library import package, installed


class Client:
    endpoint = 'synthetic-loopback'
    def __init__(self, options='', ignore=False, fail_after_write=False):
        self.options, self.ignore, self.fail_after_write = options, ignore, fail_after_write
        self.writes = []
    def read(self, number):
        assert number == 504230
        return self.options
    def set(self, number, expected, desired):
        assert number == 504230
        if self.options != expected:
            raise steam_client.Changed('user settings changed')
        self.writes.append(desired)
        if not self.ignore:
            self.options = desired
        if self.fail_after_write:
            raise steam_client.Unavailable('disconnected after write')
    def close(self):
        pass


def configure(tmp_path, package, installed, client):
    root, _, meta = package
    path = tmp_path / 'records/504230.json'
    detected = lib.installation(504230, [installed])
    return path, lib.configure(root, meta, 504230, path, detected, client)


def test_live_backup_verified_configuration_restore_and_idempotence(tmp_path, package, installed):
    previous = 'CUSTOM="quoted option" %command% --existing'
    client = Client(previous)
    path, record = configure(tmp_path, package, installed, client)
    assert record['previous'] == previous and record['previous_source'] == 'steam-live'
    assert record['status'] == 'configured' and client.options == record['generated']
    before = path.read_bytes()
    configure(tmp_path, package, installed, client)
    assert client.writes == [record['generated']] and path.read_bytes() == before
    assert lib.restore_live(path, client) == previous and client.options == previous
    assert json.loads(path.read_text())['status'] == 'restored'
    assert lib.restore_live(path, client) == previous


def test_write_failure_retains_exact_backup_then_repairs(tmp_path, package, installed):
    client = Client('prior', fail_after_write=True)
    with pytest.raises(ValueError, match='not verified'):
        configure(tmp_path, package, installed, client)
    path = tmp_path / 'records/504230.json'
    failed = json.loads(path.read_text())
    assert failed['previous'] == 'prior' and failed['status'] == 'configuration-unverified'
    client.fail_after_write = False
    _, repaired = configure(tmp_path, package, installed, client)
    assert repaired['previous'] == 'prior' and repaired['status'] == 'configured'
    lib.restore_live(path, client)
    assert client.options == 'prior'


def test_ignored_write_never_reports_success(tmp_path, package, installed):
    client = Client('prior', ignore=True)
    with pytest.raises(ValueError, match='not verified'):
        configure(tmp_path, package, installed, client)
    record = json.loads((tmp_path / 'records/504230.json').read_text())
    assert record['status'] == 'configuration-unverified' and record['previous'] == 'prior'
    assert client.options == 'prior'


def test_user_changes_block_repair_and_restoration(tmp_path, package, installed):
    client = Client('prior')
    path, _ = configure(tmp_path, package, installed, client)
    client.options = 'later user setting'
    before = path.read_bytes()
    with pytest.raises(ValueError, match='changed'):
        configure(tmp_path, package, installed, client)
    with pytest.raises(ValueError, match='changed'):
        lib.restore_live(path, client)
    assert path.read_bytes() == before and client.options == 'later user setting'


def test_interrupted_restore_retries_exact_prior_value(tmp_path, package, installed):
    client = Client('prior')
    path, _ = configure(tmp_path, package, installed, client)
    client.fail_after_write = True
    with pytest.raises(steam_client.Unavailable):
        lib.restore_live(path, client)
    assert json.loads(path.read_text())['status'] == 'restoring'
    client.fail_after_write = False
    assert lib.restore_live(path, client) == 'prior'
    assert json.loads(path.read_text())['status'] == 'restored'


def test_moved_package_repair_keeps_original_backup(tmp_path, package, installed):
    client = Client('prior')
    path, first = configure(tmp_path, package, installed, client)
    root, _, meta = package
    moved = root.with_name('new package location')
    root.rename(moved)
    repaired = lib.configure(moved, meta, 504230, path, lib.installation(504230, [installed]), client)
    assert repaired['previous'] == 'prior' and repaired['package'] == str(moved)
    assert repaired['generated'] == first['generated']  # Stable wrapper path.
    assert str(moved) in Path(repaired['wrapper']).read_text()


def test_legacy_pending_setup_gets_actual_live_backup(tmp_path, package, installed):
    root, launcher, meta = package
    path = tmp_path / 'records/504230.json'
    detected = lib.installation(504230, [installed])
    lib.prepare(root, meta, launcher, 504230, 'unreliable old input', path, detected)
    client = Client('actual current options')
    record = lib.configure(root, meta, 504230, path, detected, client)
    assert record['previous'] == 'actual current options' and record['previous_source'] == 'steam-live'


def test_menu_never_requests_launch_option_input(tmp_path, package, installed, monkeypatch, capsys):
    root, launcher, meta = package
    client = Client('prior')
    monkeypatch.setattr(lib, 'records', lambda: tmp_path / 'records')
    monkeypatch.setattr(lib, 'installation', lambda number: {'state': 'installed', 'installations': [] ,'errors': []})
    monkeypatch.setattr(lib, 'live_client', lambda: client)
    monkeypatch.setattr(lib, 'native_host_runtime', lambda roots: Path('/synthetic/native-host-runtime'))
    monkeypatch.setattr(lib, 'offer_dedup', lambda *args: None)
    monkeypatch.setattr(lib, 'choose', lambda prompt: '1')
    monkeypatch.setattr('builtins.input', lambda *a: pytest.fail('manual input requested'))
    assert lib.menu(root, meta['name'], launcher) is False
    assert 'read back successfully' in capsys.readouterr().out


def test_unavailable_client_offers_nonsteam_without_touching_settings(tmp_path, package, installed, monkeypatch, capsys):
    root, launcher, meta = package
    monkeypatch.setattr(lib, 'records', lambda: tmp_path / 'records')
    monkeypatch.setattr(lib, 'installation', lambda number: {'state': 'installed', 'installations': [], 'errors': []})
    monkeypatch.setattr(lib, 'live_client', lambda: (_ for _ in ()).throw(steam_client.Unavailable('no endpoint')))
    monkeypatch.setattr(lib, 'choose', lambda prompt: '1')
    assert lib.menu(root, meta['name'], launcher) is True
    assert not (tmp_path / 'records/504230.json').exists()
    assert 'not reported complete' in capsys.readouterr().out


def test_receipt_without_steamappid_uses_other_actual_context(package, tmp_path, installed, monkeypatch):
    root, launcher, meta = package
    detected = lib.installation(504230, [installed])
    path = tmp_path / 'records/504230.json'
    record = lib.prepare(root, meta, launcher, 504230, '', path, detected)
    for key in ('SteamAppId', 'SteamGameId', 'STEAM_COMPAT_APP_ID', 'SteamOverlayGameId'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('SteamGameId', '504230')
    monkeypatch.setattr(lib, 'installation', lambda number: detected)
    lib.receipt(path, record['generated'], root)
    assert json.loads(path.read_text())['launch_context']['keys'] == ['SteamGameId']
    monkeypatch.setenv('SteamAppId', '999')
    with pytest.raises(ValueError, match='Genuine'):
        lib.receipt(path, record['generated'], root)


def test_actual_steamlaunch_ancestry_fallback(tmp_path, monkeypatch):
    for key in ('SteamAppId', 'SteamGameId', 'STEAM_COMPAT_APP_ID', 'SteamOverlayGameId'):
        monkeypatch.delenv(key, raising=False)
    proc = tmp_path / 'proc'
    (proc / '37').mkdir(parents=True)
    (proc / '37/cmdline').write_bytes(b'/steam/reaper\0SteamLaunch\0AppId=504230\0--\0game\0')
    assert lib.launch_context(504230, proc_root=proc, parent=37)['source'] == 'steam-launch-ancestor'
    assert lib.launch_context(413150, proc_root=proc, parent=37) is None


def test_wrapper_receipt_is_not_running_runtime_proof(package):
    root, _, meta = package
    runtime = root / 'runtime/dotnet/dotnet'
    runtime.parent.mkdir(parents=True)
    header = bytearray(20)
    header[:6] = b'\x7fELF\x02\x01'
    header[18:20] = (183).to_bytes(2, 'little')
    runtime.write_bytes(header)
    empty = root / 'synthetic-proc'
    empty.mkdir()
    assert lib.observe_runtime(root, meta, 504230, proc_root=empty) is None
    header[18:20] = (62).to_bytes(2, 'little')
    runtime.write_bytes(header)
    with pytest.raises(ValueError, match='AArch64 ELF'):
        lib.observe_runtime(root, meta, 504230, proc_root=empty)


def test_link_rejects_launcher_hardlink_without_chmodding_original(tmp_path, package, installed):
    root, launcher, meta = package
    original = installed / 'steamapps/common/Celeste/original.bin'
    launcher.unlink()
    os.link(original, launcher)
    before = original.stat()
    with pytest.raises(ValueError, match='unsafe'):
        lib.configure(root, meta, 504230, tmp_path / 'records/504230.json',
                      lib.installation(504230, [installed]), Client())
    after = original.stat()
    assert (after.st_mode, after.st_nlink, after.st_ctime_ns) == (before.st_mode, before.st_nlink, before.st_ctime_ns)


def test_atomic_record_rejects_original_hardlink(tmp_path):
    original = tmp_path / 'original'
    original.write_bytes(b'original bytes')
    record = tmp_path / 'record.json'
    os.link(original, record)
    before = original.stat()
    with pytest.raises(ValueError, match='multiply-linked'):
        lib.atomic_json(record, {'unsafe': True})
    assert original.stat().st_nlink == before.st_nlink
    assert original.stat().st_ctime_ns == before.st_ctime_ns
    assert original.read_bytes() == b'original bytes'
