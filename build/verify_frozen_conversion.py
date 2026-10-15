"""Verify the real frozen GUI's conversion/ZIP/cleanup flow using synthetic assets."""
import argparse
import json
import os
import time
from pathlib import Path
import struct
import subprocess
import tempfile
import zipfile


def verify(executable, receipt):
    with tempfile.TemporaryDirectory(prefix='megcfbt-frozen-conversion-') as directory:
        root = Path(directory)
        source = root / 'Synthetic RGSS game'
        source.mkdir()
        assets = b'RGSSAD\x00\x03' + b'fixture assets, not a playable commercial game'
        (source / 'Game.rgss3a').write_bytes(assets)
        (source / 'Game.ini').write_text('[Game]\nLibrary=System/RGSS301.dll\nScripts=Data/Scripts.rvdata2\nTitle=Release fixture\n', encoding='utf-8')
        runtime = root / 'runtime'
        runtime.mkdir()
        header = bytearray(64)
        header[:6] = b'\x7fELF\x02\x01'
        struct.pack_into('<H', header, 18, 183)
        (runtime / 'mkxp-z.aarch64').write_bytes(header)
        support = runtime / 'frame_steam_env.c'
        support.write_text('/* synthetic runtime support */\n', encoding='utf-8')
        old = time.time() - 172800
        os.utime(support, (old, old))
        output = root / 'output'
        output.mkdir()
        subprocess.run([str(executable.resolve()), '--verify-gui-conversion', str(source),
                        '--output-dir', str(output), '--backend-runtime', str(runtime),
                        '--receipt', str(receipt.resolve()), '--controller-profile', '--timeout', '120'], check=True, timeout=150)
        result = json.loads(receipt.read_text(encoding='utf-8'))
        assert result['state'] == 'complete' and result['frozen']
        assert (source / 'Game.rgss3a').read_bytes() == assets
        archives = list(output.glob('*.zip'))
        assert len(archives) == 1 and not list(output.glob('*-frame'))
        with zipfile.ZipFile(archives[0]) as package:
            assert package.testzip() is None
            names = package.namelist()
            original = next(name for name in names if name.endswith('/game/Game.rgss3a'))
            assert package.read(original) == assets
            metadata = [json.loads(package.read(name)) for name in names if name.endswith('/.megcfbt/package.json')]
            assert len(metadata) == 2
            assert all(item['conversion']['converter'] == result['build_info'] for item in metadata)
            profiles = [name for name in names if name.endswith('/controllers/profile.json')]
            assert len(profiles) == 1, 'Frozen converter did not bundle controller resources'
            manifest = json.loads(package.read(profiles[0]))
            assert manifest['engine'] == 'vxace' and manifest['toggle'] == 'R3'
            folder = profiles[0].rsplit('/', 1)[0]
            import hashlib
            for item in manifest['controllers'].values():
                assert hashlib.sha256(package.read(folder + '/' + item['file'])).hexdigest() == item['sha256']
            assert folder + '/setup.py' in names and folder + '/steam_cdp.py' in names
        result['synthetic_zip_cleanup_verified'] = True
        result['controller_resources_verified'] = True
        receipt.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    verify(args.executable, args.receipt)
