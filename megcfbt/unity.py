"""Static Unity candidate inspection. Never loads game binaries."""

from __future__ import annotations

import re
import struct
from pathlib import Path

from megcfbt.models import UnifiedInspection


def pe_architecture(path: Path) -> str:
    """Read the PE machine field, including architectures unsuitable for pure ARM64."""
    try:
        with path.open('rb') as stream:
            header = stream.read(64)
            if len(header) != 64 or header[:2] != b'MZ':
                return 'unknown'
            offset = struct.unpack_from('<I', header, 60)[0]
            if offset < 64 or offset > path.stat().st_size - 6:
                return 'unknown'
            stream.seek(offset)
            pe = stream.read(6)
            if pe[:4] != b'PE\0\0':
                return 'unknown'
            machine = struct.unpack_from('<H', pe, 4)[0]
            return {0x8664: 'x64', 0x14c: 'x86', 0xaa64: 'ARM64',
                    0xa641: 'ARM64EC', 0xa64e: 'ARM64X'}.get(machine, hex(machine))
    except OSError:
        return 'unreadable'


def inspect_game(root: Path) -> UnifiedInspection | None:
    files = {p.name.casefold(): p for p in root.iterdir() if p.is_file()}
    data_dirs = sorted(p for p in root.iterdir() if p.is_dir() and p.name.endswith('_Data'))
    if 'unityplayer.dll' not in files or not data_dirs:
        return None
    # Avoid attributing one export's metadata to a different executable.
    if len(data_dirs) != 1:
        return UnifiedInspection(root, None, 'unity', 'Unity', None, root.name,
                                 'ambiguous', 'high', None, False,
                                 ('Multiple Unity data directories; select one complete export.',))
    data = data_dirs[0]
    evidence = [f'UnityPlayer.dll: {pe_architecture(files["unityplayer.dll"])}']
    versions = set()
    try:
        with (data / 'globalgamemanagers').open('rb') as stream:
            header = stream.read(65536)
        versions = {v[:-1].decode('ascii') for v in re.findall(
            rb'(?<![0-9])(?:6000|20[0-9]{2}|[345])\.[0-9]+\.[0-9]+[abfp][0-9]+\x00', header)
                    }
    except OSError:
        pass
    version = next(iter(versions)) if len(versions) == 1 else None
    if version:
        evidence.append(f'{data.name}/globalgamemanagers: Unity {version}')
    managed = sorted((data / 'Managed').glob('*.dll'))
    il2cpp = ('gameassembly.dll' in files or
              (data / 'il2cpp_data/Metadata/global-metadata.dat').is_file())
    mono = not il2cpp and (data / 'Managed/Assembly-CSharp.dll').is_file()
    evidence.append(f'Managed assemblies: {len(managed)}')
    evidence.append(f'Scripting backend: {"IL2CPP" if il2cpp else "Mono candidate" if mono else "unknown"}')
    warnings = ['This Unity export does not match a supported exact-source conversion profile.']
    if il2cpp:
        warnings.append('IL2CPP native game code requires an ARM64 game build; managed interop assemblies cannot replace it.')
    elif mono:
        warnings.append('Investigate an exact-version Windows ARM64 Mono player under ARM64 Proton; runtime availability and native dependencies must be verified.')
    else:
        warnings.append('Portable managed game code has not been established.')
    if not version:
        warnings.append('Exact Unity version is missing or ambiguous; do not substitute a different player version.')
    plugins = sorted((data / 'Plugins').rglob('*'))
    for plugin in plugins:
        if plugin.is_file() and plugin.suffix.casefold() in {'.dll', '.so', '.dylib'}:
            arch = pe_architecture(plugin) if plugin.suffix.casefold() == '.dll' else 'non-PE (not inspected)'
            relative = plugin.relative_to(root).as_posix()
            evidence.append(f'Native plugin: {relative}: {arch}')
            if arch != 'ARM64':
                warnings.append(f'{plugin.name} ({arch}) needs a compatible ARM64 replacement or a verified managed fallback.')
    warnings.append('Static inventory does not establish P/Invoke coverage, dynamic dependencies, shader compatibility or gameplay.')
    hollow_knight = (data.name == 'hollow_knight_Data' and
                     'hollow_knight.exe' in files and mono and version == '6000.0.61f1')
    if hollow_knight:
        evidence.append('Hollow Knight 6000.0.61f1 research candidate (not a validated conversion profile)')
    return UnifiedInspection(root, None, 'unity', 'Unity IL2CPP' if il2cpp else 'Unity',
                             version, 'Hollow Knight' if hollow_knight else root.name,
                             'unsupported', 'high',
                             'Windows ARM64 Mono / ARM64 Proton research' if mono else None,
                             False, tuple(warnings), tuple(evidence))
