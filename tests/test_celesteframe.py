import hashlib
import io
import json
import struct
import tarfile
from pathlib import Path
import pytest
from celesteframe import backend, profiles, runtime
from megcfbt.native_backend import NativeBuildError
from megcfbt.router import inspect_source

def elf(machine=183):
    data = bytearray(64)
    data[:6] = b'\x7fELF\x02\x01'
    struct.pack_into('<H', data, 18, machine)
    return bytes(data)

def pe():
    data = bytearray(512)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 128)
    data[128:132] = b'PE\0\0'
    struct.pack_into('<H', data, 132, 0x8664)
    return bytes(data)

def source(tmp_path, monkeypatch):
    root = tmp_path/'game'
    (root/'Content/FMOD').mkdir(parents=True)
    (root/'Content/Maps').mkdir()
    hashes = {}
    for name in profiles.SOURCE_HASHES:
        data = b'MZfixture-'+name.encode()
        (root/name).write_bytes(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(profiles, 'SOURCE_HASHES', hashes)
    return root

def sdk(tmp_path):
    root = tmp_path/'sdk'
    files = {}
    for name in runtime.REQUIRED:
        data = elf() if name.startswith('native/') or name == 'dotnet/dotnet' else pe()
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        files[name] = hashlib.sha256(data).hexdigest()
    manifest = {'profile': profiles.PROFILE, 'architecture': 'aarch64',
        'dotnet_version': '8.0.31', 'files': files,
        'runtime_files': [name for name in files if not name.startswith('prepare/')]}
    (root/'engine-capabilities.json').write_text(json.dumps(manifest))
    return root

def test_source_routes_and_rejects_changed_or_modded_install(tmp_path, monkeypatch):
    root = source(tmp_path, monkeypatch)
    assert inspect_source(root).backend == 'celesteframe'
    assert inspect_source(root).buildable
    (root/'Mods').mkdir()
    assert not inspect_source(root).buildable
    (root/'Mods').rmdir()
    (root/'Celeste.exe').write_bytes(b'MZ modified')
    assert not profiles.matches_source(root)

def test_modified_source_cannot_replace_output(tmp_path, monkeypatch):
    root = source(tmp_path, monkeypatch)
    (root/'Steamworks.NET.dll').write_bytes(b'changed')
    output = tmp_path/'output'
    output.mkdir()
    (output/'keep').write_text('existing')
    with pytest.raises(NativeBuildError, match='verified vanilla'):
        backend.build_game(root, output=output, force=True)
    assert (output/'keep').read_text() == 'existing'

@pytest.mark.parametrize('change', ['tamper', 'architecture', 'traversal', 'missing'])
def test_runtime_rejects_invalid_bundle(tmp_path, change):
    root = sdk(tmp_path)
    assert runtime.validate_sdk(root)['profile'] == profiles.PROFILE
    path = root/'engine-capabilities.json'
    manifest = json.loads(path.read_text())
    if change == 'tamper':
        (root/'managed/FNA.dll').write_bytes(b'altered')
    elif change == 'architecture':
        (root/'native/libFNA3D.so').write_bytes(elf(62))
        manifest['files']['native/libFNA3D.so'] = hashlib.sha256(elf(62)).hexdigest()
    elif change == 'traversal':
        manifest['files']['../outside'] = '0'*64
    else:
        del manifest['files']['prepare/windows-x64/CelestePrepare.exe']
    path.write_text(json.dumps(manifest))
    with pytest.raises(NativeBuildError):
        runtime.validate_sdk(root)

def test_owner_fmod_is_separate_from_runtime_sdk(tmp_path, monkeypatch):
    root = sdk(tmp_path)
    archive = tmp_path/'fmod.tar.gz'
    with tarfile.open(archive, 'w:gz') as output:
        for directory, name in [('core', 'fmod'), ('studio', 'fmodstudio')]:
            member = tarfile.TarInfo(f'fmodstudioapi20315linux/api/{directory}/lib/arm64/lib{name}.so.14.15')
            data = elf()
            member.size = len(data)
            output.addfile(member, io.BytesIO(data))
        member = tarfile.TarInfo('../outside')
        member.size = 3
        output.addfile(member, io.BytesIO(b'bad'))
    monkeypatch.setattr(runtime, 'validate_fmod_sdk', lambda path: path)
    target = tmp_path/'runtime'
    runtime.copy_runtime(root, target, archive)
    assert (target/'native/libfmod.so.14').read_bytes() == elf()
    assert (target/'native/libfmodstudio.so.14').read_bytes() == elf()
    assert not (target/'prepare').exists()
    assert not (tmp_path/'outside').exists()
    assert not (root/'native/libfmod.so.14').exists()

def test_counterfeit_fmod_sdk_rejected(tmp_path):
    archive = tmp_path/runtime.FMOD_FILENAME
    archive.write_bytes(b'not the SDK')
    with pytest.raises(NativeBuildError, match='checksum'):
        runtime.validate_fmod_sdk(archive)

def test_managed_config_loads_real_fna_and_steam_assemblies(tmp_path):
    backend.write_managed_config(tmp_path, '8.0.31')
    deps = json.loads((tmp_path/'Celeste.deps.json').read_text())
    target = deps['targets'][deps['runtimeTarget']['name']]
    assert target['Celeste/1.0.0']['dependencies'] == {'FNA': '23.10.0', 'Steamworks.NET': '20.0.0'}
    assert 'Steamworks.NET.dll' in target['Steamworks.NET/20.0.0']['runtime']
