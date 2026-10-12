"""Verify a prepared experiment using only the Python standard library on Frame."""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path


def file_hash(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def machine(path):
    with path.open('rb') as source:
        dos = source.read(64)
        if len(dos) != 64 or dos[:2] != b'MZ':
            raise ValueError(f'Invalid PE binary: {path}')
        offset = struct.unpack_from('<I', dos, 60)[0]
        if not 64 <= offset <= path.stat().st_size - 6:
            raise ValueError(f'Invalid PE offset: {path}')
        source.seek(offset)
        header = source.read(6)
        if header[:4] != b'PE\0\0':
            raise ValueError(f'Invalid PE signature: {path}')
        return struct.unpack_from('<H', header, 4)[0]


def verify(root):
    root = root.resolve()
    manifest = json.loads((root / '.hk-arm64/manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema') != 1 or manifest.get('target') != 'windows-arm64-proton':
        raise ValueError('Invalid experiment manifest')
    native, managed = manifest['native_files'], manifest['managed_files']
    if not native or not managed:
        raise ValueError('Empty binary inventory')
    expected = dict(native) | dict(managed)
    actual = set()
    trees = [root / 'hollow_knight_Data', root / 'MonoBleedingEdge', root / '.hk-arm64/runtime']
    for base in trees:
        for path in base.rglob('*'):
            if path.is_file() and path.suffix.lower() in {'.dll', '.exe', '.so', '.dylib'}:
                actual.add(path.relative_to(root).as_posix())
    for path in root.iterdir():
        if path.is_file() and path.suffix.lower() in {'.dll', '.exe', '.so', '.dylib'}:
            actual.add(path.name)
    if actual != expected.keys():
        raise ValueError(f'Binary inventory changed: added={sorted(actual - expected.keys())}, missing={sorted(expected.keys() - actual)}')
    for relative, expected_hash in expected.items():
        path = root / relative
        if path.resolve().is_relative_to(root) is False:
            raise ValueError(f'Binary resolves outside the experiment: {relative}')
        if file_hash(path) != expected_hash:
            raise ValueError(f'Binary hash changed: {relative}')
        if relative in native and machine(path) != 0xaa64:
            raise ValueError(f'Expected pure ARM64 PE, not x64/ARM64EC/ARM64X: {relative}')
    assembly = 'hollow_knight_Data/Managed/Assembly-CSharp.dll'
    if managed.get(assembly) != manifest['prepared_assembly_sha256']:
        raise ValueError('Patched assembly identity is inconsistent')
    return manifest


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.directory)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f'Experiment verification failed: {exc}\n')
    print(f'Binary integrity verified: {len(result["native_files"])} ARM64 components, {len(result["managed_files"])} managed assemblies. Instance status: {result.get("status", "unknown")}.')


if __name__ == '__main__':
    main()
