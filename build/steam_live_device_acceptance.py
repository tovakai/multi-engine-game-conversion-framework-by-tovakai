"""Explicit real-device acceptance helper; never run by automated fixture suites.

Run on Frame with the installer helper ZIP and extracted converted package path.
Updates only converted installer helpers, uses the real live Steam API, roundtrips
launch options, leaves the verified converted link configured and can launch it.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time
import zipfile


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def snapshot(root, dedup):
    result = {}
    def visit(directory):
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NOATIME)
        try:
            with os.scandir(fd) as entries:
                children = sorted(entry.name for entry in entries)
        finally:
            os.close(fd)
        for name in children:
            path = directory / name
            info = path.lstat()
            fields = {key: getattr(info, key) for key in ('st_mode', 'st_size', 'st_ino',
                'st_dev', 'st_uid', 'st_gid', 'st_mtime_ns', 'st_ctime_ns', 'st_atime_ns')}
            if stat.S_ISREG(info.st_mode):
                fields['sha256'] = dedup.digest(path, source=True)
            elif stat.S_ISLNK(info.st_mode):
                fields['link'] = os.readlink(path)
            elif stat.S_ISDIR(info.st_mode):
                visit(path)
            else:
                raise ValueError('Unexpected original installation file type')
            result[path.relative_to(root).as_posix()] = fields
    visit(root)
    return result


def run(package, archive, launch):
    package = package.resolve()
    metadata = package / '.megcfbt'
    if metadata.is_symlink():
        raise ValueError('Unsafe converted metadata directory')
    meta = json.loads((metadata / 'package.json').read_text())
    if meta.get('backend') != 'monoframe' or meta.get('compatibility_profile') != 'stardew-steam-1.6.15-net6':
        raise ValueError('This acceptance run requires the audited Stardew conversion')
    asset_record = metadata / 'asset-links.json'
    if asset_record.exists() and json.loads(asset_record.read_text())['status'] != 'active':
        raise ValueError('Wait for the existing deduplication transaction to finish before testing')
    names = ['steam_library.py', 'steam_client.py', 'asset_dedup.py']
    backup = metadata / ('installer-before-live-test-' + str(time.time_ns()))
    backup.mkdir(mode=0o700)
    with zipfile.ZipFile(archive) as packed:
        if set(packed.namelist()) != set(names):
            raise ValueError('Unexpected installer helper ZIP contents')
        for name in names:
            path = metadata / name
            if path.is_symlink():
                raise ValueError('Unsafe installer helper path')
            if path.exists():
                shutil.copy2(path, backup / name)
            temporary = metadata / (name + '.live-test-pending')
            with temporary.open('xb') as stream:
                stream.write(packed.read(name))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
    sys.path.insert(0, str(metadata))
    lib = load('steam_library', metadata / 'steam_library.py')
    dedup = load('asset_dedup', metadata / 'asset_dedup.py')
    load('steam_client', metadata / 'steam_client.py')
    number = lib.identity(meta)
    detected = lib.installation(number)
    if detected['state'] != 'installed':
        raise ValueError('Original game is not reliably installed locally')
    originals = {item['game']: snapshot(Path(item['game']), dedup) for item in detected['installations']}
    dedup.repair_graphics_bootstrap(package, meta, detected)
    client = lib.live_client()
    previous = client.read(number)
    path = lib.records() / f'{number}.json'
    if path.exists():
        existing = json.loads(path.read_text())
        if (existing.get('mode') == 'live-native' and previous == existing.get('generated')
                and existing.get('previous_source') == 'steam-live'):
            previous = existing['previous']
    report = {'appid': number, 'endpoint': client.endpoint,
        'previous_length': len(previous), 'previous_sha256': hashlib.sha256(previous.encode()).hexdigest(),
        'package': str(package), 'helper_backup': str(backup),
        'installer_sources': {name: hashlib.sha256((metadata / name).read_bytes()).hexdigest() for name in names}}
    report['original_snapshot_sha256'] = hashlib.sha256(
        json.dumps(originals, sort_keys=True).encode()).hexdigest()
    try:
        record = lib.configure(package, meta, number, path, detected, client)
        assert client.read(number) == record['generated']
        report['injection_verified'] = True
        report['backup_exact'] = record['previous'] == previous and record['previous_source'] == 'steam-live'
        lib.configure(package, meta, number, path, detected, client)
        report['idempotent_configuration'] = True
        lib.restore_live(path, client)
        assert client.read(number) == previous
        report['restoration_verified'] = True
        record = lib.configure(package, meta, number, path, detected, client)
        assert client.read(number) == record['generated']
        report['final_link_configured'] = True
    finally:
        client.close()
    report['original_files_and_metadata_unchanged'] = all(
        snapshot(Path(root), dedup) == before for root, before in originals.items())
    assert report['original_files_and_metadata_unchanged']
    evidence = metadata / 'live-steam-acceptance.json'
    lib.atomic_json(evidence, report)
    print(json.dumps(report, indent=2), flush=True)
    if launch:
        # connect() just verified an existing client; the CLI forwards this
        # request to it. SSH sessions need not have a graphical xdg-open handler.
        subprocess.run(['steam', '-applaunch', str(number)], check=True)
        for attempt in range(30):
            observed = lib.observe_runtime(package, meta, number)
            if observed:
                report['actual_runtime'] = observed
                report['original_files_and_metadata_unchanged_after_launch'] = all(
                    snapshot(Path(root), dedup) == before for root, before in originals.items())
                lib.atomic_json(evidence, report)
                print(json.dumps({'actual_runtime': observed,
                    'original_files_unchanged_after_launch': report['original_files_and_metadata_unchanged_after_launch']}), flush=True)
                return
            time.sleep(1)
        print('Actual ARM64 runtime not observed within 30 seconds; launch acceptance is UNVERIFIED.', flush=True)


def verify_running(package):
    package = package.resolve()
    metadata = package / '.megcfbt'
    sys.path.insert(0, str(metadata))
    lib = load('steam_library', metadata / 'steam_library.py')
    load('asset_dedup', metadata / 'asset_dedup.py')
    load('steam_client', metadata / 'steam_client.py')
    meta = json.loads((metadata / 'package.json').read_text())
    number = lib.identity(meta)
    path = lib.records() / f'{number}.json'
    record = json.loads(path.read_text())
    client = lib.live_client()
    try:
        assert client.read(number) == record['generated']
        observed = lib.observe_runtime(package, meta, number)
        if not observed:
            raise ValueError('Actual converted runtime is not currently observable')
        record['runtime_observation'] = observed
        record['runtime_verified_utc'] = lib.datetime.datetime.now(lib.datetime.timezone.utc).isoformat()
        lib.atomic_json(path, record)
        evidence = metadata / 'live-steam-acceptance.json'
        report = json.loads(evidence.read_text())
        report['actual_runtime'] = observed
        report['genuine_native_launch_chain'] = True
        report['steamvr_controller_gameplay_save_relaunch'] = 'user-confirmed, not inferred from wrapper execution'
        report['persistence_across_steam_restart'] = 'unverified'
        report['playtime'] = 'unverified'
        report['achievements'] = 'unverified'
        lib.atomic_json(evidence, report)
        print(json.dumps(report, indent=2), flush=True)
    finally:
        client.close()


if __name__ == '__main__':
    if sys.argv[2] == '--verify-user-confirmed-running':
        verify_running(Path(sys.argv[1]))
    else:
        run(Path(sys.argv[1]), Path(sys.argv[2]), '--launch' in sys.argv[3:])
