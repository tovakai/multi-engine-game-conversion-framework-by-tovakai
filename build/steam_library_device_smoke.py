"""Run synthetic fixtures on Linux AArch64; never use the real Steam home."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

spec = importlib.util.spec_from_file_location('fixture_steam_library', sys.argv[1])
lib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lib)
sys.path.insert(0, str(Path(sys.argv[1]).parent))
import asset_dedup as dedup
with tempfile.TemporaryDirectory(prefix='megcfbt-library-fixtures-') as temporary:
    home = Path(temporary)
    steam = home / '.local/share/Steam'
    secondary = home / 'mounted secondary library'
    (steam / 'steamapps').mkdir(parents=True)
    (secondary / 'steamapps/common/Celeste').mkdir(parents=True)
    original = secondary / 'steamapps/common/Celeste/original.bin'
    original.write_bytes(b'original preserved')
    (secondary / 'steamapps/appmanifest_504230.acf').write_text(
        '"AppState" { "appid" "504230" "StateFlags" "4" "installdir" "Celeste" }')
    (steam / 'steamapps/libraryfolders.vdf').write_text(
        '"libraryfolders" { "1" { "path" ' + json.dumps(str(secondary)) + ' } }')
    detected = lib.installation(504230, [steam])
    assert detected['state'] == 'installed'
    assert detected['ownership'] == 'unknown'
    assert lib.installation(123, [steam])['state'] == 'missing'
    root = home / "converted game's folder"
    (root / '.megcfbt').mkdir(parents=True)
    shutil.copyfile(sys.argv[1], root / '.megcfbt/steam_library.py')
    shutil.copyfile(Path(sys.argv[1]).with_name('asset_dedup.py'), root / '.megcfbt/asset_dedup.py')
    launcher = root / 'launch.sh'
    launcher.write_text('#!/bin/sh\n[ "$#" -eq 0 ]\n[ "$SteamAppId" = 504230 ]\nprintf launched > "' + str(root / 'receipt.txt') + '"\n')
    meta = {'architecture': 'aarch64', 'engine': 'CelesteFrame',
            'target_platform': 'linux-aarch64', 'launcher': 'launch.sh',
            'compatibility_profile': 'celeste-steam-xna-1.4.0.0'}
    record_path = home / 'records/504230.json'
    record = lib.prepare(root, meta, launcher, 504230, 'old launch options', record_path, detected)
    wrapper = Path(record['wrapper'])
    subprocess.run(['sh', '-n', str(wrapper)], check=True)
    env = dict(os.environ, HOME=str(home))
    env.pop('SteamAppId', None)
    assert subprocess.run([str(wrapper), '/bin/false'], env=env, capture_output=True).returncode != 0
    # Simulated context, not a hardware Steam launch/ownership claim.
    env['SteamAppId'] = '504230'
    subprocess.run([str(wrapper), '/bin/false', '--must-not-forward'], env=env, check=True)
    assert (root / 'receipt.txt').read_text() == 'launched'
    assert json.loads(record_path.read_text())['status'] == 'launch-observed'
    assert original.read_bytes() == b'original preserved'
    target = root / 'game/Content/Maps/fixture.xnb'
    source = secondary / 'steamapps/common/Celeste/Content/Maps/fixture.xnb'
    target.parent.mkdir(parents=True)
    source.parent.mkdir(parents=True)
    asset = b'XNB' + b'immutable content' * 8192
    target.write_bytes(asset)
    source.write_bytes(asset)
    def snapshot(path):
        info = path.stat()
        return (info.st_mode, info.st_size, info.st_ino, info.st_mtime_ns, info.st_ctime_ns, info.st_atime_ns)
    before = snapshot(source)
    result = dedup.enable(root, meta, detected, experimental=True)
    assert result['linked'] == 1 and result['allocation_measured']
    assert result['reclaimed_bytes'] > 0
    assert snapshot(source) == before
    assert dedup.enable(root, meta, detected, experimental=True) == result
    write_test = ('import errno,pathlib,sys\ntry:\n pathlib.Path(sys.argv[1]).write_bytes(b"unsafe")\n'
                  'except OSError as e:\n sys.exit(0 if e.errno == errno.EROFS else 2)\nsys.exit(3)')
    protected = dedup.isolated_command(root, [str(source.parents[2])], [sys.executable, '-c', write_test, str(target)])
    subprocess.run(protected, check=True)
    assert snapshot(source) == before
    subprocess.run([str(wrapper), '/bin/false'], env=env, check=True)
    assert snapshot(source) == before
    assert dedup.restore_assets(root, detected) == 1
    assert not target.is_symlink() and target.read_bytes() == asset
    assert snapshot(source) == before
    print('PASS: actual bubblewrap denies writes through asset links; source bytes, mode, inode, mtime, ctime and atime preserved. Linked files: 1; measured reclaimed bytes:', result['reclaimed_bytes'])
    launcher.unlink()
    missing = subprocess.run([str(wrapper), '/bin/false'], env=env, capture_output=True, text=True)
    assert missing.returncode != 0 and 'moved or deleted' in missing.stderr
    unsafe = root / 'unsafe.sh'
    unsafe.symlink_to(original)
    try:
        lib.safe_file(root, 'unsafe.sh')
        raise AssertionError('symlink accepted')
    except ValueError:
        pass
    assert lib.restore(record_path, record['generated'], True) == 'old launch options'
    assert original.read_bytes() == b'original preserved'
print('PASS: Linux AArch64 synthetic secondary-library detection, missing install, wrapper syntax/context/argument isolation, launch receipt, missing-package repair diagnostic, symlink rejection, restoration and original preservation. No actual Steam installation modified.')
