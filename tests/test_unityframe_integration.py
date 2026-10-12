"""Integration boundaries for exact-profile Windows ARM64 Unity builds."""
import hashlib
import io
import json
import struct
import zipfile
from pathlib import Path

import pytest

from megcfbt.frame_package import create_frame_zip, load_frame_metadata, write_frame_metadata
from megcfbt.native_backend import NativeBuildError
from megcfbt.router import build_source, inspect_source
from unityframe import backend, runtime
from unityframe.find_proton import find_proton


def pe(*, managed=False, flags=1, machine=0x8664):
    result = bytearray(1024)
    result[:2] = b'MZ'
    struct.pack_into('<I', result, 60, 128)
    result[128:132] = b'PE\0\0'
    struct.pack_into('<HHIIIHH', result, 132, machine, 1, 0, 0, 0, 240, 0x2022)
    struct.pack_into('<H', result, 152, 0x20b)
    struct.pack_into('<II', result, 184, 4096, 512)
    struct.pack_into('<II', result, 208, 8192, 512)
    struct.pack_into('<I', result, 260, 16)
    result[392:400] = b'.text\0\0\0'
    struct.pack_into('<IIII', result, 400, 256, 4096, 512, 512)
    if managed:
        struct.pack_into('<II', result, 264 + 14 * 8, 4096, 72)
        struct.pack_into('<I', result, 512, 72)
        struct.pack_into('<I', result, 528, flags)
    return bytes(result)


@pytest.fixture
def source(tmp_path, monkeypatch):
    root = tmp_path / 'Hollow Knight'
    data = root / 'hollow_knight_Data'
    (data / 'Managed').mkdir(parents=True)
    (data / 'Plugins/x86_64').mkdir(parents=True)
    (root / 'MonoBleedingEdge/etc').mkdir(parents=True)
    for name in ['hollow_knight.exe', 'UnityPlayer.dll', 'UnityCrashHandler64.exe']:
        (root / name).write_bytes(pe())
    (data / 'globalgamemanagers').write_bytes(b'6000.0.61f1\0')
    for name in ['Assembly-CSharp.dll', 'com.rlabrecque.steamworks.net.dll']:
        (data / 'Managed' / name).write_bytes(pe(managed=True))
    plugins = ['InControlNative.dll', 'XInputInterface64.dll', 'steam_api64.dll']
    for name in plugins:
        (data / 'Plugins/x86_64' / name).write_bytes(pe())
    (data / 'Plugins/Steamworks.NET.txt').write_text('notice')
    hashed = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    profile = {'id': 'fixture-hollow-knight', 'engine_version': '6000.0.61f1',
               'source_assembly_sha256': hashed(data / 'Managed/Assembly-CSharp.dll'),
               'source_steamworks_sha256': hashed(data / 'Managed/com.rlabrecque.steamworks.net.dll'),
               'source_plugins': {name: hashed(data / 'Plugins/x86_64' / name) for name in plugins},
               'source_plugin_notices': {'Steamworks.NET.txt': hashed(data / 'Plugins/Steamworks.NET.txt')}}
    monkeypatch.setattr(backend, 'profile', lambda: profile)
    return root


def test_exact_source_is_routed_but_modified_assembly_is_gated(source):
    result = inspect_source(source)
    assert result.backend == 'unityframe' and result.buildable
    assembly = source / 'hollow_knight_Data/Managed/Assembly-CSharp.dll'
    assembly.write_bytes(assembly.read_bytes() + b'modified')
    changed = inspect_source(source)
    assert changed.engine == 'unity' and not changed.buildable and changed.backend is None


def test_mixed_mode_dependency_blocks_recipe(source):
    (source / 'hollow_knight_Data/Managed/addon.dll').write_bytes(pe(managed=True, flags=3))
    assert not inspect_source(source).buildable


def test_router_emits_windows_arm64_metadata(source, tmp_path, monkeypatch):
    monkeypatch.setattr(backend, 'resolve_archives', lambda *a, **k: (tmp_path / 'unity.pkg', tmp_path / 'bridge.tgz'))
    def prepare_copy(src, unity, bridge, output):
        output.mkdir()
        (output / 'launch-hollow-knight-arm64.sh').write_text('#!/bin/sh\nexit 0\n')
    monkeypatch.setattr(backend, 'prepare', prepare_copy)
    monkeypatch.setattr('megcfbt.router.complete_frame_artwork', lambda *a, **k: {})
    result = build_source(source, output=tmp_path / 'converted', archive=False)
    metadata = load_frame_metadata(result.output_path)
    assert result.target_platform == metadata['target_platform'] == 'windows-arm64-proton'
    assert metadata['runtime'] == 'arm64-proton'
    assert metadata['operating_system'] == 'windows'
    assert source.is_dir() and result.launcher_path.is_file()


def test_windows_package_excludes_live_prefix_and_logs(tmp_path):
    root = tmp_path / 'HollowKnight-frame'
    root.mkdir()
    launcher = root / 'launch-hollow-knight-arm64.sh'
    launcher.write_text('#!/bin/sh\nexit 0\n')
    for relative in ['.hk-arm64/compatdata/save.dat', '.hk-arm64/logs/game.log', '.hk-arm64/runtime/aarch64-windows/bridge.dll']:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture')
    write_frame_metadata(root, name='Hollow Knight', launcher_path=launcher,
                         engine='unity', target_platform='windows-arm64-proton')
    archive = create_frame_zip(root)
    assert archive.name == 'HollowKnight-windows-arm64-proton.zip'
    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        assert not any('/compatdata/' in name or '/logs/' in name for name in names)
        assert any('/runtime/aarch64-windows/bridge.dll' in name for name in names)
        meta = json.loads(package.read('HollowKnight-frame/.megcfbt/package.json'))
        assert meta['runtime'] == 'arm64-proton' and meta['launcher'] == 'launch.sh'
        assert 'ARM64 Proton' in package.read('HollowKnight-frame/INSTALL-ON-FRAME.txt').decode()


def test_force_cannot_remove_existing_saves(source, tmp_path):
    output = tmp_path / 'previous'
    save = output / '.hk-arm64/compatdata/save.dat'
    save.parent.mkdir(parents=True)
    save.write_bytes(b'existing save')
    with pytest.raises(NativeBuildError, match='prefix and saves'):
        backend.build_game(source, output=output, force=True)
    assert save.read_bytes() == b'existing save'


def proton(root, name, version, arm64=True):
    directory = root / 'steamapps/common' / name
    directory.mkdir(parents=True)
    (directory / 'version').write_text('123 ' + version)
    (directory / 'proton').write_text('fixture')
    if arm64:
        client = directory / 'files/lib/wine/aarch64-unix/lsteamclient.so'
        client.parent.mkdir(parents=True)
        client.write_text('fixture')
    return directory


def test_proton_discovery_uses_library_folders_and_rejects_x64(tmp_path, monkeypatch):
    monkeypatch.delenv('HK_ARM64_STEAM_ROOT', raising=False)
    root = tmp_path / '.local/share/Steam'
    proton(root, 'Proton 11.0', 'proton-11.0-2e-x86_64', arm64=False)
    sd = tmp_path / 'SD Library'
    expected = proton(sd, 'Proton 11.0 (ARM64)', 'proton-11.0-2e-arm64')
    (root / 'steamapps/libraryfolders.vdf').write_text('"path" "' + str(sd) + '"')
    assert find_proton(tmp_path) == expected


class Response(io.BytesIO):
    @property
    def headers(self):
        return {'Content-Length': str(len(self.getvalue()))}


def test_corrupt_cache_is_replaced_only_after_download_verifies(tmp_path, monkeypatch):
    target = tmp_path / 'runtime.pkg'
    target.write_bytes(b'old invalid cache')
    payload = b'verified content'
    entry = {'url': 'https://example.invalid/runtime', 'sha256': hashlib.sha256(payload).hexdigest(), 'size': len(payload)}
    monkeypatch.setattr(runtime.urllib.request, 'urlopen', lambda *a, **k: Response(payload))
    runtime.cached_archive(entry, target)
    assert target.read_bytes() == payload
    monkeypatch.setattr(runtime.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('Verified cache should not download'))
    assert runtime.cached_archive(entry, target) == target


def test_bad_download_cannot_replace_cache(tmp_path, monkeypatch):
    target = tmp_path / 'runtime.pkg'
    target.write_bytes(b'old cache')
    monkeypatch.setattr(runtime.urllib.request, 'urlopen', lambda *a, **k: Response(b'bad'))
    with pytest.raises(ValueError, match='SHA-256 mismatch'):
        runtime.cached_archive({'url': 'https://example.invalid/runtime', 'sha256': '0' * 64}, target)
    assert target.read_bytes() == b'old cache'
    assert not list(tmp_path.glob('*.part-*'))
