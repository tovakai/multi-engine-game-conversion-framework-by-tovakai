"""Real Git history and portable build provenance regression coverage."""
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest
from packaging.version import Version

from megcfbt import version
from megcfbt import frame_package


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, text=True, stderr=subprocess.STDOUT).strip()


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / 'repo'
    root.mkdir()
    git(root, 'init')
    git(root, 'config', 'user.email', 'test@example.invalid')
    git(root, 'config', 'user.name', 'Version test')
    (root / 'source.txt').write_text('first\n')
    git(root, 'add', 'source.txt')
    git(root, 'commit', '-m', 'first')
    return root


@pytest.mark.parametrize('value,parts', [('0.1.0',(0,1,0,0)), ('0.1.0.1',(0,1,0,1)),
                                      ('0.1.1.0',(0,1,1,0)), ('1.0.0.0',(1,0,0,0))])
def test_release_parsing(value, parts):
    assert version.parse_release(value) == parts
    assert Version(value).release == tuple(int(n) for n in value.split('.'))


@pytest.mark.parametrize('value', ['v0.1.0', '0.1', '0.1.0.0.0', '0.01.0', '0.1.1.dev3', '0.1.0+dirty', '-1.0.0'])
def test_invalid_public_release(value):
    with pytest.raises(ValueError):
        version.parse_release(value)


def test_pep440_ordering():
    values = ['0.1.0', '0.1.0.1', '0.1.0.2', '0.1.1.0.dev7+gabc', '0.1.1.0', '0.1.1.1', '0.2.0.0', '1.0.0.0']
    assert sorted(values, key=Version) == values
    assert Version('0.1.0') == Version('0.1.0.0')


def test_commits_detached_head_and_untracked_files(repository):
    first = version.resolve_source(repository)
    assert first['commit'] == git(repository, 'rev-parse', 'HEAD')
    assert first['commit_count'] == 1 and first['tracked_changes'] is False
    (repository / 'cache.tmp').write_text('untracked')
    assert version.resolve_source(repository) == first
    (repository / 'source.txt').write_text('second\n')
    git(repository, 'commit', '-am', 'second')
    second = version.resolve_source(repository)
    assert second['version'] != first['version']
    assert second['commit_count'] == 2
    git(repository, 'checkout', '--detach', first['commit'])
    assert version.resolve_source(repository) == first


def test_dirty_staged_and_unstaged_identity(repository):
    clean = version.resolve_source(repository)
    (repository / 'source.txt').write_text('dirty\n')
    dirty = version.resolve_source(repository)
    assert dirty['tracked_changes'] and dirty['commit'] == clean['commit']
    assert '.dirty.' in dirty['version'] and dirty['tracked_diff_sha256']
    git(repository, 'add', 'source.txt')
    assert version.resolve_source(repository)['version'] == dirty['version']
    (repository / 'source.txt').write_text('different\n')
    assert version.resolve_source(repository)['version'] != dirty['version']


def test_release_tag_validation(repository):
    tag = 'v' + version.RELEASE_VERSION
    git(repository, 'tag', tag)
    info = version.resolve_source(repository)
    assert info['version'] == version.RELEASE_VERSION and info['build_kind'] == 'release'
    version.validate_release(tag, info)
    with pytest.raises(ValueError, match='does not match'):
        version.validate_release('v0.1.0.1', info)
    (repository / 'source.txt').write_text('dirty\n')
    with pytest.raises(ValueError, match='clean'):
        version.validate_release(tag, version.resolve_source(repository))


def test_shallow_identity(repository, tmp_path):
    git(repository, 'tag', 'v' + version.RELEASE_VERSION)
    shallow = tmp_path / 'shallow'
    git(tmp_path, 'clone', '--depth', '1', repository.as_uri(), str(shallow))
    info = version.resolve_source(shallow)
    assert info['commit'] == version.resolve_source(repository)['commit']
    assert info['shallow'] and info['commit_count'] is None
    assert '.dev0+' in info['version'] and '.shallow' in info['version']
    with pytest.raises(ValueError):
        version.validate_release('v' + version.RELEASE_VERSION, info)


def test_missing_git_and_enclosing_repository(repository, tmp_path, monkeypatch):
    missing = version.resolve_source(tmp_path)
    assert missing['commit'] is None and missing['tracked_changes'] is None
    assert missing['build_kind'] == 'unknown'
    child = repository / 'unrelated'
    child.mkdir()
    assert version.resolve_source(child)['commit'] is None
    monkeypatch.setattr(version, '_git', lambda *args: (_ for _ in ()).throw(FileNotFoundError()))
    assert version.resolve_source(repository)['build_kind'] == 'unknown'


def test_frozen_uses_embedded_identity_without_git(tmp_path, monkeypatch):
    info = version.resolve_source()
    embedded = tmp_path / '_build_info.json'
    embedded.write_text(json.dumps(info))
    monkeypatch.setattr(version, 'EMBEDDED', embedded)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(version, '_git', lambda *args: pytest.fail('Frozen app invoked Git'))
    assert version.read_build_info() == info
    embedded.write_text(json.dumps({'schema': 'megcfbt.build/v1', 'release_version': version.RELEASE_VERSION, 'version': version.RELEASE_VERSION}))
    assert version.read_build_info()['build_kind'] == 'unknown'
    embedded.unlink()
    assert version.read_build_info()['commit'] is None
    assert 'unavailable' in version.read_build_info()['metadata_status']


def test_cli_and_gui_share_identity(capsys):
    from megcfbt import cli, gui, __version__
    with pytest.raises(SystemExit) as result:
        cli.main(['--version'])
    assert result.value.code == 0
    assert capsys.readouterr().out.strip().endswith(__version__)
    with pytest.raises(SystemExit):
        cli.main(['--build-info'])
    info = json.loads(capsys.readouterr().out)
    assert info == gui.get_build_info()
    assert gui.display_version(info) == version.display_version(info)


@pytest.mark.parametrize('target', ['linux-aarch64', 'windows-arm64-proton'])
def test_package_provenance_names_repackaging_and_overwrite(tmp_path, monkeypatch, target):
    old = version.resolve_source()
    old.update(version='0.1.0.1', commit='a' * 40, build_kind='release', tracked_changes=False)
    monkeypatch.setattr(frame_package, 'get_build_info', lambda: old.copy())
    build = tmp_path / 'Game-frame'
    build.mkdir()
    launcher = build / 'launch.sh'
    launcher.write_text('#!/bin/sh\n')
    frame_package.write_frame_metadata(build, name='Game', launcher_path=launcher,
                                      engine='godot', engine_version='4.2', runtime_engine_version='4.3',
                                      game_version='2.0', target_platform=target, compatibility_profile='test')
    original = frame_package.load_frame_metadata(build)
    archive = frame_package.create_frame_zip(build)
    assert archive.name == f'Game-frame-conv-v0.1.0.1-{target}.zip'
    assert original['game_version'] == '2.0' and original['engine_version'] == '4.2'
    assert original['runtime_engine_version'] == '4.3'
    assert original['conversion']['converter']['commit'] == 'a' * 40
    assert original['conversion']['converted_utc'].endswith('+00:00')
    with pytest.raises(frame_package.FramePackageError, match='already exists'):
        frame_package.create_frame_zip(build)
    newer = {**old, 'version': '0.1.1.0', 'commit': 'b' * 40}
    monkeypatch.setattr(frame_package, 'get_build_info', lambda: newer.copy())
    frame_package.create_frame_zip(build, force=True)
    assert frame_package.load_frame_metadata(build) == original
    with zipfile.ZipFile(archive) as zf:
        assert zf.testzip() is None
        for name in ('Game-frame/.megcfbt/package.json', 'Game-frame/payload/.megcfbt/package.json'):
            meta = json.loads(zf.read(name))
            assert meta['conversion'] == original['conversion']
            assert meta['packaging']['tool']['commit'] == 'b' * 40


def test_legacy_package_remains_readable_and_not_claimed_as_new_conversion(tmp_path):
    build = tmp_path / 'Legacy-frame'
    build.mkdir()
    (build / 'launch.sh').write_text('#!/bin/sh\n')
    (build / '.megcfbt').mkdir()
    metadata = {'schema': 'megcfbt.frame-build/v1', 'name': 'Legacy', 'launcher': 'launch.sh'}
    (build / '.megcfbt/package.json').write_text(json.dumps(metadata))
    assert frame_package.load_frame_metadata(build) == metadata
    archive = frame_package.create_frame_zip(build)
    assert archive.name == 'Legacy-linux-aarch64.zip'
    with zipfile.ZipFile(archive) as zf:
        packaged = json.loads(zf.read('Legacy-frame/.megcfbt/package.json'))
        assert 'conversion' not in packaged
        assert 'packaging' in packaged


def test_archive_publication_race_does_not_overwrite(tmp_path, monkeypatch):
    build = tmp_path / 'Race-frame'
    build.mkdir()
    launcher = build / 'launch.sh'
    launcher.write_text('#!/bin/sh\n')
    output = tmp_path / 'manual.zip'
    original_link = frame_package.os.link
    def race(source, target):
        output.write_bytes(b'existing archive')
        original_link(source, target)
    monkeypatch.setattr(frame_package.os, 'link', race)
    with pytest.raises(frame_package.FramePackageError):
        frame_package.create_frame_zip(build, launcher_path=launcher, output=output)
    assert output.read_bytes() == b'existing archive'


def test_archive_filesystem_without_hardlinks(tmp_path, monkeypatch):
    import errno
    build = tmp_path / 'Portable-frame'
    build.mkdir()
    launcher = build / 'launch.sh'
    launcher.write_text('#!/bin/sh\n')
    def unavailable(*args):
        raise OSError(errno.ENOTSUP, 'Hardlinks unsupported')
    monkeypatch.setattr(frame_package.os, 'link', unavailable)
    output = tmp_path / 'explicit-name.zip'
    frame_package.create_frame_zip(build, launcher_path=launcher, output=output)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
    with pytest.raises(frame_package.FramePackageError, match='already exists'):
        frame_package.create_frame_zip(build, launcher_path=launcher, output=output)
