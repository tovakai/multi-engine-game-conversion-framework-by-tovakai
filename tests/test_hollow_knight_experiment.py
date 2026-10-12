"""Verify the experimental package boundary and exact-build assembly patches."""
import gzip
import hashlib
import importlib.util
import io
import json
import struct
import tarfile
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1] / 'experiments/hollow-knight'


@pytest.fixture
def modules(monkeypatch):
    pytest.importorskip('pefile', reason='Install experiments/hollow-knight/requirements.txt to test the preparer.')
    def load(name, filename):
        spec = importlib.util.spec_from_file_location(name, ROOT / filename)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(__import__('sys').modules, name, module)
        spec.loader.exec_module(module)
        return module
    extractor = load('unity_package', 'unity_package.py')
    prepare = load('hk_prepare', 'prepare.py')
    return extractor, prepare


def cpio(name, payload=b'', mode=0o100644):
    encoded = name.encode() + b'\0'
    return (b'070707' + b''.join(f'{value:06o}'.encode() for value in [0, 1, mode, 0, 0, 1, 0])
            + f'{0:011o}{len(encoded):06o}{len(payload):011o}'.encode() + encoded + payload)


def package(path, entries, corrupt_crc=False):
    payload = gzip.compress(b''.join(cpio(*entry) for entry in entries) + cpio('TRAILER!!!'))
    if corrupt_crc:
        payload = payload[:-8] + bytes([payload[-8] ^ 0xff]) + payload[-7:]
    root = ET.Element('xar')
    toc = ET.SubElement(root, 'toc')
    file = ET.SubElement(toc, 'file')
    ET.SubElement(file, 'name').text = 'Payload'
    data = ET.SubElement(file, 'data')
    ET.SubElement(data, 'offset').text = '0'
    ET.SubElement(data, 'length').text = str(len(payload))
    raw = ET.tostring(root)
    compressed = zlib.compress(raw)
    path.write_bytes(struct.pack('>4sHHQQI', b'xar!', 28, 1, len(compressed), len(raw), 0) + compressed + payload)


def test_allowlist_cannot_write_archive_paths(tmp_path, modules):
    extractor, _ = modules
    archive = tmp_path / 'unity.pkg'
    package(archive, [('Variations/arm64/UnityPlayer.dll', b'player'), ('../../escaped.dll', b'bad')])
    target = tmp_path / 'selected.dll'
    extractor.extract_selected(archive, {'Variations/arm64/UnityPlayer.dll': target})
    assert target.read_bytes() == b'player'
    assert sorted(p.name for p in tmp_path.iterdir()) == ['selected.dll', 'unity.pkg']


@pytest.mark.parametrize('entries', [[('wanted', b'a'), ('wanted', b'b')],
                                   [('wanted', b'elsewhere', 0o120777)]])
def test_duplicate_and_link_selected_members_fail(tmp_path, modules, entries):
    extractor, _ = modules
    archive = tmp_path / 'unity.pkg'
    package(archive, entries)
    with pytest.raises(ValueError, match='Invalid selected member'):
        extractor.extract_selected(archive, {'wanted': tmp_path / 'output'})


def test_missing_player_member_fails(tmp_path, modules):
    extractor, _ = modules
    archive = tmp_path / 'unity.pkg'
    package(archive, [('other', b'data')])
    with pytest.raises(ValueError, match='Missing player files'):
        extractor.extract_selected(archive, {'wanted': tmp_path / 'output'})


def test_gzip_crc_is_checked(tmp_path, modules):
    extractor, _ = modules
    archive = tmp_path / 'unity.pkg'
    package(archive, [('wanted', b'data')], corrupt_crc=True)
    with pytest.raises(gzip.BadGzipFile):
        extractor.extract_selected(archive, {'wanted': tmp_path / 'output'})


def test_truncated_xar_fails(tmp_path, modules):
    extractor, _ = modules
    archive = tmp_path / 'unity.pkg'
    archive.write_bytes(b'xar!')
    with pytest.raises(ValueError, match='Truncated'):
        extractor.extract_selected(archive, {})


def test_patches_preserve_original_and_file_length(tmp_path, modules):
    _, prepare = modules
    source = tmp_path / 'source.dll'
    destination = tmp_path / 'copy.dll'
    original = b'prefix' + bytes.fromhex('1a7e252600042a') + b'suffix'
    source.write_bytes(original)
    profile = {'source_assembly_sha256': hashlib.sha256(original).hexdigest(),
               'patches': [{'method': 'Input::get_EnableNativeInput', 'offset': 6,
                            'original': '1a7e252600042a', 'return': False, 'reason': 'fallback'}]}
    changes = prepare.patch_assembly(source, destination, profile)
    assert source.read_bytes() == original
    assert len(destination.read_bytes()) == len(original)
    assert destination.read_bytes()[6:13] == bytes.fromhex('1a162a00000000')
    assert changes[0]['original'] == '1a7e252600042a'


def test_modified_assembly_cannot_be_patched(tmp_path, modules):
    _, prepare = modules
    source = tmp_path / 'source.dll'
    source.write_bytes(b'changed')
    with pytest.raises(ValueError, match='SHA-256 mismatch'):
        prepare.patch_assembly(source, tmp_path / 'copy.dll',
                               {'source_assembly_sha256': '0' * 64, 'patches': []})
    assert not (tmp_path / 'copy.dll').exists()


def test_source_output_overlap_fails_before_any_writes(tmp_path, modules):
    _, prepare = modules
    source = tmp_path / 'game'
    source.mkdir()
    with pytest.raises(ValueError, match='separate directory trees'):
        prepare.prepare(source, tmp_path / 'missing.pkg', tmp_path / 'missing.tgz', source / 'output')
    assert list(source.iterdir()) == []


def test_bridge_path_traversal_is_rejected(tmp_path, modules):
    _, prepare = modules
    archive = tmp_path / 'bridge.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        entry = tarfile.TarInfo('bridge/licenses/../../escaped')
        entry.size = 3
        tar.addfile(entry, io.BytesIO(b'bad'))
    profile = {'bridge_package': {'prefix': 'bridge/', 'sha256': prepare.digest(archive), 'files': {}}}
    with pytest.raises(ValueError, match='Unsafe archive path'):
        prepare.extract_bridge(archive, tmp_path / 'output', profile)
    assert not (tmp_path / 'escaped').exists()


def test_target_verifier_rejects_arm64ec_even_with_matching_hash(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('hk_verify', ROOT / 'verify.py')
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    header = bytearray(64)
    header[:2] = b'MZ'
    struct.pack_into('<I', header, 60, 64)
    (tmp_path / 'hollow_knight.exe').write_bytes(bytes(header) + b'PE\0\0' + struct.pack('<H', 0xa641))
    managed = tmp_path / 'hollow_knight_Data/Managed/Assembly-CSharp.dll'
    managed.parent.mkdir(parents=True)
    managed.write_bytes(b'managed fixture')
    state = tmp_path / '.hk-arm64'
    state.mkdir()
    manifest = {'schema': 1, 'target': 'windows-arm64-proton',
                'native_files': {'hollow_knight.exe': verifier.file_hash(tmp_path / 'hollow_knight.exe')},
                'managed_files': {'hollow_knight_Data/Managed/Assembly-CSharp.dll': verifier.file_hash(managed)},
                'prepared_assembly_sha256': verifier.file_hash(managed)}
    (state / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='Expected pure ARM64 PE'):
        verifier.verify(tmp_path)
