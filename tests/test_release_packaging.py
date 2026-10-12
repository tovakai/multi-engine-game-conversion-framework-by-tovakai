"""Release archives must identify their source and contain required notices."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
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
    (root / 'LICENSE').write_text('license fixture')
    (root / 'THIRD_PARTY_NOTICES.md').write_text('notice fixture')
    notes = root / f'docs/releases/{module.RELEASE_VERSION}.md'
    notes.parent.mkdir(parents=True)
    notes.write_text('release scope fixture [support](../monoframe.md)')
    monkeypatch.setattr(module, 'ROOT', root)
    from megcfbt.version import unknown_build_info
    identity = unknown_build_info()
    identity.update(version=module.RELEASE_VERSION, build_kind='release', commit='a' * 40,
                    short_commit='a' * 12, tracked_changes=False, shallow=False,
                    platform='windows-x64', architecture='x86_64', built_utc='2026-10-12T12:00:00+00:00')
    monkeypatch.setattr(module, 'resolve_source', lambda root: identity)
    application = root / 'dist/windows' / module.APP_NAME
    application.mkdir(parents=True)
    embedded = application / '_internal/megcfbt/_build_info.json'
    embedded.parent.mkdir(parents=True)
    embedded.write_text(json.dumps(identity))
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
        notes = packaged.read(module.APP_NAME + '/RELEASE-NOTES.md').decode()
        assert 'release scope fixture' in notes
        assert f'/blob/{"a" * 40}/docs/monoframe.md' in notes
        assert '](../' not in notes


def test_release_refuses_mislabeled_executable_architecture(release):
    module, application = release
    (application / (module.APP_NAME + '.exe')).write_bytes(executable(0xaa64))
    with pytest.raises(ValueError, match='architecture'):
        module.package(application, 'windows-x64')


def test_release_refuses_source_change_after_freezing(release):
    module, application = release
    embedded = application / '_internal/megcfbt/_build_info.json'
    identity = json.loads(embedded.read_text())
    identity['commit'] = 'b' * 40
    embedded.write_text(json.dumps(identity))
    with pytest.raises(ValueError, match='identity disagree: commit'):
        module.package(application, 'windows-x64')


def test_release_tag_mismatch_rejected(release, monkeypatch):
    module, application = release
    monkeypatch.setenv('GITHUB_REF_TYPE', 'tag')
    monkeypatch.setenv('GITHUB_REF_NAME', 'v0.1.0.1')
    with pytest.raises(ValueError, match='does not match'):
        module.package(application, 'windows-x64')
