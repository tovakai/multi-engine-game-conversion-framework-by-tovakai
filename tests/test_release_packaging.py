"""Release archives must identify their source and contain required notices."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import zipfile

import pytest


@pytest.fixture
def release(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'build/release_metadata.py'
    spec = importlib.util.spec_from_file_location('release_metadata', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / 'project'
    root.mkdir()
    (root / 'pyproject.toml').write_text('[project]\nversion="0.1.0"\n')
    (root / 'LICENSE').write_text('license fixture')
    (root / 'THIRD_PARTY_NOTICES.md').write_text('notice fixture')
    notes = root / 'docs/releases/0.1.0.md'
    notes.parent.mkdir(parents=True)
    notes.write_text('release scope fixture')
    monkeypatch.setattr(module, 'ROOT', root)
    monkeypatch.setattr(module.subprocess, 'check_output', lambda *a, **k: 'a' * 40)
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(a, 0))
    application = root / 'dist/windows' / module.APP_NAME
    application.mkdir(parents=True)
    return module, application


def executable(machine):
    data = bytearray(256)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 128)
    data[128:132] = b'PE\0\0'
    struct.pack_into('<H', data, 132, machine)
    return data


def test_release_archive_provenance_notices_and_checksum(release):
    module, application = release
    (application / (module.APP_NAME + '.exe')).write_bytes(executable(0x8664))
    archive = module.package(application, 'windows-x64')
    checksum = archive.parent / 'SHA256SUMS-windows-x64.txt'
    assert checksum.read_text().split()[0] == hashlib.sha256(archive.read_bytes()).hexdigest()
    with zipfile.ZipFile(archive) as packaged:
        assert packaged.testzip() is None
        metadata = json.loads(packaged.read(module.APP_NAME + '/BUILD.json'))
        assert metadata['commit'] == 'a' * 40
        assert metadata['platform'] == 'windows-x64'
        assert packaged.read(module.APP_NAME + '/LICENSE') == b'license fixture'
        assert packaged.read(module.APP_NAME + '/THIRD_PARTY_NOTICES.md') == b'notice fixture'
        assert packaged.read(module.APP_NAME + '/RELEASE-NOTES.md') == b'release scope fixture'


def test_release_refuses_mislabeled_executable_architecture(release):
    module, application = release
    (application / (module.APP_NAME + '.exe')).write_bytes(executable(0xaa64))
    with pytest.raises(ValueError, match='architecture'):
        module.package(application, 'windows-x64')
