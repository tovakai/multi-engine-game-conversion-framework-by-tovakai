"""Stage exact runtime-only assets from published or authenticated draft releases.

Authentication is handled by gh; tokens are never included in arguments or output.
This script does not create tags, publish releases, or download game files.
"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REPO = 'tovakai/multi-engine-game-conversion-framework-by-tovakai'
TAGS = {'godot-4.1.4-until-then-native-arm64-v1': 'runtime-until-then-arm64-v1',
        'godot-4.5-train45-native-arm64-v1': 'runtime-train45-arm64-v1'}
ASSET_IDS = {'godot-4.1.4-until-then-native-arm64-v1': 642021919,
             'godot-4.5-train45-native-arm64-v1': 642024009}


def stage(entry, tag, destination, *, download=subprocess.run, verify=None):
    name = entry['archive_name']
    if Path(name).name != name or '/' in name or '\\' in name:
        raise ValueError('Unsafe runtime archive name')
    target = destination / name
    destination.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise ValueError('Unsafe staged runtime symlink')
    if verify is None:
        from verify_runtime_bundles import verify
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('Existing runtime checksum differs; retain it for review')
        verify(target)
        return target
    with tempfile.TemporaryDirectory(prefix='runtime-download-', dir=destination) as temporary:
        source = Path(temporary) / name
        try:
            download(['gh', 'release', 'download', tag, '--repo', REPO,
                      '--pattern', name, '--dir', temporary], check=True)
        except subprocess.CalledProcessError:
            asset = ASSET_IDS.get(entry.get('recipe_id'))
            if asset is None:
                raise
            # Direct asset access can work when draft tag lookup is unavailable.
            # Same repository, same authentication, and unchanged hash/member checks.
            with source.open('wb') as stream:
                download(['gh', 'api', f'repos/{REPO}/releases/assets/{asset}',
                          '-H', 'Accept: application/octet-stream'], check=True, stdout=stream)
        if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('Downloaded runtime checksum mismatch')
        verify(source)
        os.replace(source, target)
    return target


if __name__ == '__main__':
    index = json.loads((ROOT / 'rpgmframe/godot_extension_runtime_index.json').read_text(encoding='utf-8'))
    for recipe, tag in TAGS.items():
        try:
            print('STAGED_RUNTIME', stage(index['recipes'][recipe], tag, ROOT / 'build/runtime-bundles'), flush=True)
        except subprocess.CalledProcessError:
            if '--optional' not in sys.argv:
                raise
            print('RUNTIME_PROVISIONING_UNVERIFIED: ' + recipe +
                  '; development smoke build only. Release builds require this asset.', flush=True)
