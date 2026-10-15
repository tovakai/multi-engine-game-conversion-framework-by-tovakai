from pathlib import Path
import zipfile

import pytest

from megcfbt.frame_package import create_frame_zip, write_frame_metadata
from megcfbt.models import UnifiedBuildResult
from megcfbt.output_cleanup import finish_gui_conversion


@pytest.fixture
def conversion(tmp_path):
    source = tmp_path / 'original'
    source.mkdir()
    (source / 'keep').write_bytes(b'original')
    output = tmp_path / 'game-frame'
    output.mkdir()
    launcher = output / 'launch.sh'
    launcher.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
    (output / 'data').write_bytes(b'converted assets')
    write_frame_metadata(output, name='Fixture', launcher_path=launcher, engine='godot')
    archive = create_frame_zip(output)
    return UnifiedBuildResult(source, output, launcher, archive, 'rpgmframe', 'godot', '4', 'Fixture')


def test_verified_work_copy_removed_and_zip_and_original_preserved(conversion):
    result = finish_gui_conversion(conversion)
    assert result.work_directory_removed and not result.output_path.exists()
    assert (result.source_path / 'keep').read_bytes() == b'original'
    with zipfile.ZipFile(result.archive_path) as archive:
        assert archive.testzip() is None
        assert archive.read('game-frame/payload/data') == b'converted assets'


@pytest.mark.parametrize('change', ['modified', 'new_save', 'corrupt_zip', 'missing_zip'])
def test_failed_verification_retains_work_copy(conversion, change):
    if change == 'modified':
        (conversion.output_path / 'data').write_bytes(b'changed assets')
    elif change == 'new_save':
        (conversion.output_path / 'save').write_bytes(b'save')
    elif change == 'corrupt_zip':
        conversion.archive_path.write_bytes(b'broken ZIP')
    else:
        conversion.archive_path.unlink()
    result = finish_gui_conversion(conversion)
    assert not result.work_directory_removed and result.warnings
    assert conversion.output_path.is_dir()
    assert (result.source_path / 'keep').read_bytes() == b'original'


def test_folder_output_and_sts2_handoff_are_retained(conversion):
    from dataclasses import replace
    for result in [replace(conversion, archive_path=None), replace(conversion, requires_frame_install=True)]:
        assert finish_gui_conversion(result) is result
    assert conversion.output_path.is_dir()


def test_source_directory_never_removed(conversion):
    from dataclasses import replace
    result = finish_gui_conversion(replace(conversion, output_path=conversion.source_path))
    assert result.warnings
    assert (result.source_path / 'keep').exists()


def test_symlink_root_rejected(conversion, tmp_path):
    from dataclasses import replace
    link = tmp_path / 'link'
    try:
        link.symlink_to(conversion.output_path, target_is_directory=True)
    except OSError:
        pytest.skip('symlinks unavailable')
    assert finish_gui_conversion(replace(conversion, output_path=link)).warnings
    assert conversion.output_path.is_dir()


def test_benign_access_time_updates_do_not_prevent_cleanup(conversion, monkeypatch):
    from types import SimpleNamespace
    original_stat = Path.stat
    reads = 0
    def stat_with_atime_update(path, *args, **kwargs):
        nonlocal reads
        value = original_stat(path, *args, **kwargs)
        if path == conversion.output_path / 'data':
            reads += 1
            fields = {key: getattr(value, key) for key in dir(value) if key.startswith('st_')}
            fields['st_atime'] += reads
            fields['st_atime_ns'] += reads * 10**9
            return SimpleNamespace(**fields)
        return value
    monkeypatch.setattr(Path, 'stat', stat_with_atime_update)
    result = finish_gui_conversion(conversion)
    assert result.work_directory_removed and not result.output_path.exists()
    assert result.archive_path.exists()
