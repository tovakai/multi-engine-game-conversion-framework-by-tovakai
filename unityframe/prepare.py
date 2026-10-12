"""Prepare a copied Windows ARM64 Hollow Knight installation for ARM64 Proton.

Consumes owner-supplied game files and pinned local runtime archives. This is
not the framework's supported build path and does not install or launch a game.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import tarfile
import tempfile
import uuid
from pathlib import Path

import pefile

from .unity_package import extract_selected


HERE = Path(__file__).resolve().parent
DATA = 'hollow_knight_Data'


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def require_hash(path, expected):
    if digest(path) != expected:
        raise ValueError(f'SHA-256 mismatch: {path}')


def require_arm64(path):
    with pefile.PE(str(path), fast_load=True) as pe:
        if pe.FILE_HEADER.Machine != 0xaa64:
            raise ValueError(f'Expected pure ARM64 PE: {path}')


def require_managed_il(path):
    with pefile.PE(str(path), fast_load=True) as pe:
        directory = pe.OPTIONAL_HEADER.DATA_DIRECTORY[14]
        if not directory.VirtualAddress or directory.Size < 20:
            raise ValueError(f'Expected managed IL assembly: {path}')
        flags = struct.unpack('<I', pe.get_data(directory.VirtualAddress + 16, 4))[0]
        if flags & 3 != 1:
            raise ValueError(f'Mixed-mode or required-x86 managed assembly: {path}')


def patch_assembly(source, destination, profile):
    """Apply reviewed byte substitutions only to the exact audited assembly."""
    require_hash(source, profile['source_assembly_sha256'])
    payload = bytearray(source.read_bytes())
    changes = []
    for patch in profile['patches']:
        start = patch['offset']
        original = bytes.fromhex(patch['original'])
        if payload[start:start + len(original)] != original:
            raise ValueError(f'Method bytes changed: {patch["method"]}')
        # Preserve tiny method headers, metadata, tokens and total file length.
        if original[0] & 3 != 2 or original[0] >> 2 != len(original) - 1:
            raise ValueError('Expected a complete tiny-format IL body')
        patched = original[:1] + bytes([0x17 if patch['return'] else 0x16, 0x2a])
        patched += bytes(len(original) - len(patched))
        payload[start:start + len(original)] = patched
        changes.append({'method': patch['method'], 'offset': start,
                        'original': original.hex(), 'patched': patched.hex(),
                        'reason': patch['reason']})
    destination.write_bytes(payload)
    return changes


def extract_bridge(package, output, profile):
    spec = profile['bridge_package']
    require_hash(package, spec['sha256'])
    seen = set()
    with tarfile.open(package, 'r:gz') as archive:
        for member in archive:
            if member.name == spec['prefix'].rstrip('/') and member.isdir():
                continue
            if not member.name.startswith(spec['prefix']):
                raise ValueError('Unexpected bridge package root')
            relative = member.name[len(spec['prefix']):]
            if relative in spec['files'] or relative in {'LICENSE', 'SOURCES.md', 'versions.env'} or relative.startswith('licenses/'):
                # Reject archive-controlled traversal, links, device nodes and duplicates.
                parts = relative.split('/')
                if any(part in {'', '.', '..'} or ':' in part or '\\' in part for part in parts):
                    raise ValueError(f'Unsafe archive path: {relative}')
                if member.isdir():
                    continue
                if not member.isfile() or relative in seen or member.size > 64 * 1024 * 1024:
                    raise ValueError(f'Invalid bridge member: {relative}')
                destination = output / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, destination.open('xb') as target:
                    shutil.copyfileobj(source, target)
                seen.add(relative)
    for name, expected in spec['files'].items():
        require_hash(output / name, expected)
        require_arm64(output / name)
    for name in {'LICENSE', 'SOURCES.md', 'versions.env'}:
        if name not in seen:
            raise ValueError(f'Missing bridge provenance: {name}')
    if not any(name.startswith('licenses/') for name in seen):
        raise ValueError('Missing upstream component licenses')


def verify_source(source, profile):
    if not source.is_dir():
        raise ValueError('Source must be an installed game directory')
    for path in source.rglob('*'):
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise ValueError(f'Linked source entry is unsupported: {path}')
    allowed = {DATA, 'MonoBleedingEdge', 'D3D12', 'hollow_knight.exe',
               'UnityPlayer.dll', 'UnityCrashHandler64.exe'}
    if {p.name for p in source.iterdir()} - allowed:
        raise ValueError('Unexpected source root entries; this experiment requires the audited vanilla layout')
    require_hash(source / DATA / 'Managed/Assembly-CSharp.dll', profile['source_assembly_sha256'])
    require_hash(source / DATA / 'Managed/com.rlabrecque.steamworks.net.dll', profile['source_steamworks_sha256'])
    with (source / DATA / 'globalgamemanagers').open('rb') as stream:
        metadata = stream.read(65536)
    if (profile['engine_version'] + '\0').encode('ascii') not in metadata:
        raise ValueError('Unity version does not match the profile')
    expected = {f'x86_64/{name}' for name in profile['source_plugins']} | set(profile['source_plugin_notices'])
    plugin_root = source / DATA / 'Plugins'
    actual = {p.relative_to(plugin_root).as_posix() for p in plugin_root.rglob('*') if p.is_file()}
    if actual != expected:
        raise ValueError(f'Native plugin inventory changed: {sorted(actual)}')
    for name, expected_hash in profile['source_plugins'].items():
        require_hash(plugin_root / 'x86_64' / name, expected_hash)
    for name, expected_hash in profile['source_plugin_notices'].items():
        require_hash(plugin_root / name, expected_hash)
    for path in (source / DATA / 'Managed').glob('*.dll'):
        require_managed_il(path)


def prepare(source: Path, unity_package: Path, bridge_package: Path, output: Path):
    profile = json.loads((HERE / 'profile.json').read_text(encoding='utf-8'))
    source, output = source.resolve(), output.resolve()
    if output == source or source in output.parents or output in source.parents:
        raise ValueError('Output and source must be separate directory trees')
    if output.exists():
        raise ValueError('Output already exists; select a new directory')
    print('Verifying original installation and pinned packages...', flush=True)
    verify_source(source, profile)
    require_hash(unity_package, profile['unity_package']['sha256'])
    require_hash(bridge_package, profile['bridge_package']['sha256'])
    output.parent.mkdir(parents=True, exist_ok=True)
    # The published tree inherits the workspace ACL. On Windows, mkdtemp's
    # private ACL must not travel with a renamed game directory.
    stage = output.with_name(f'.{output.name}-preparing-{uuid.uuid4().hex}')
    stage.mkdir()
    try:
        return _prepare_verified(source, unity_package, bridge_package, output, stage, profile)
    finally:
        if stage.exists():
            if stage.resolve().parent != output.parent or not stage.name.startswith(f'.{output.name}-preparing-'):
                raise ValueError('Refusing cleanup outside the staging parent')
            shutil.rmtree(stage)


def _prepare_verified(source, unity_package, bridge_package, output, stage, profile):
    # Extract downloaded components privately; publish only after verification.
    with tempfile.TemporaryDirectory(prefix=f'.{output.name}-preparing-', dir=output.parent) as temporary:
        runtime = Path(temporary) / 'unity'
        spec = profile['unity_package']
        extract_selected(unity_package, {spec['prefix'] + name: runtime / name for name in spec['files']})
        for name, expected in spec['files'].items():
            require_hash(runtime / name, expected)
            require_arm64(runtime / name)
        bridge = Path(temporary) / 'bridge'
        extract_bridge(bridge_package, bridge, profile)
        with pefile.PE(str(bridge / 'steam_api64.dll')) as pe:
            exports = {row.name.decode('ascii') for row in pe.DIRECTORY_ENTRY_EXPORT.symbols if row.name}
        missing = set(profile['required_steam_exports']) - exports
        if missing:
            raise ValueError(f'Steam wrapper exports missing: {sorted(missing)}')
        print('Copying assets and managed code, selecting the Unity input fallback...', flush=True)
        source_data = source / DATA
        shutil.copytree(source_data, stage / DATA,
                        ignore=lambda path, names: ['Plugins'] if Path(path) == source_data else [])
        for name in profile['source_plugin_notices']:
            destination = stage / DATA / 'Plugins' / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_data / 'Plugins' / name, destination)
        shutil.copytree(source / 'MonoBleedingEdge/etc', stage / 'MonoBleedingEdge/etc')
        changes = patch_assembly(source_data / 'Managed/Assembly-CSharp.dll',
                                 stage / DATA / 'Managed/Assembly-CSharp.dll', profile)
        for name in spec['files']:
            destination = 'hollow_knight.exe' if name == 'WindowsPlayer.exe' else name
            path = stage / destination
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(runtime / name, path)
        bridge_destinations = {'steam_api64.dll': f'{DATA}/Plugins/ARM64/steam_api64.dll',
                              'lsteamclient_a64.dll': '.hk-arm64/runtime/aarch64-windows/lsteamclient_a64.dll',
                              'MonoPosixHelper.dll': 'MonoBleedingEdge/EmbedRuntime/MonoPosixHelper.dll'}
        for name in profile['bridge_package']['files']:
            destination = stage / bridge_destinations.get(name, name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bridge / name, destination)
        notices = stage / '.hk-arm64/licenses'
        shutil.copytree(bridge / 'licenses', notices)
        shutil.copy2(bridge / 'LICENSE', notices / 'bs-arm64-MIT.txt')
        shutil.copy2(bridge / 'SOURCES.md', stage / '.hk-arm64/BRIDGE-SOURCES.md')
        shutil.copy2(bridge / 'versions.env', stage / '.hk-arm64/bridge-versions.env')
        shutil.copy2(HERE / 'launch.sh', stage / 'launch-hollow-knight-arm64.sh')
        shutil.copy2(HERE / 'find_proton.py', stage / '.hk-arm64/find_proton.py')
        (stage / 'launch-hollow-knight-arm64.sh').chmod(0o755)
        shutil.copy2(HERE / 'profile.json', stage / '.hk-arm64/profile.json')
        shutil.copy2(HERE / 'verify.py', stage / '.hk-arm64/verify.py')
        shutil.copy2(HERE / 'validation-2026-10-12.json', stage / '.hk-arm64/recipe-validation.json')
        native_files, managed_files = {}, {}
        for path in stage.rglob('*'):
            if not path.is_file() or path.suffix.lower() not in {'.dll', '.exe'}:
                continue
            if path.parent == stage / DATA / 'Managed':
                require_managed_il(path)
                managed_files[path.relative_to(stage).as_posix()] = digest(path)
            else:
                require_arm64(path)
                native_files[path.relative_to(stage).as_posix()] = digest(path)
        manifest = {'schema': 1, 'profile': profile['id'], 'status': 'prepared',
                    'recipe_validation': profile['status'],
                    'target': 'windows-arm64-proton', 'steam_app_id': 367520,
                    'source_path': str(source), 'source_assembly_sha256': profile['source_assembly_sha256'],
                    'prepared_assembly_sha256': digest(stage / DATA / 'Managed/Assembly-CSharp.dll'),
                    'patches': changes, 'native_files': native_files, 'managed_files': managed_files,
                    'proton_tags': profile['bridge_package']['proton_tags']}
        (stage / '.hk-arm64/manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        # Recheck the original while the copy was prepared; never write to it.
        require_hash(source_data / 'Managed/Assembly-CSharp.dll', profile['source_assembly_sha256'])
        stage.rename(output)
    print(f'Prepared experiment: {output}', flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--unity-package', required=True, type=Path)
    parser.add_argument('--bridge-package', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        prepare(args.source, args.unity_package, args.bridge_package, args.output)
    except (OSError, ValueError, pefile.PEFormatError, tarfile.TarError) as exc:
        parser.exit(1, f'Preparation failed: {exc}\n')


if __name__ == '__main__':
    main()
