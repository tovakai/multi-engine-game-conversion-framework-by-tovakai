import hashlib
import importlib.util
from pathlib import Path
import subprocess

import pytest

spec = importlib.util.spec_from_file_location('runtime_staging', Path(__file__).resolve().parents[1] / 'build/stage_runtime_bundles.py')
staging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(staging)


def entry(data=b'approved'):
    return {'archive_name': 'runtime.tar.gz', 'sha256': hashlib.sha256(data).hexdigest()}


def test_stage_verifies_download_before_install_and_is_idempotent(tmp_path):
    calls = []
    verified = []
    def download(command, **kwargs):
        calls.append(command)
        (Path(command[-1]) / 'runtime.tar.gz').write_bytes(b'approved')
    target = staging.stage(entry(), 'runtime-test', tmp_path, download=download, verify=lambda p: verified.append(p.read_bytes()))
    assert target.read_bytes() == b'approved'
    assert calls[0][:4] == ['gh', 'release', 'download', 'runtime-test']
    assert '--repo' in calls[0]
    staging.stage(entry(), 'runtime-test', tmp_path, download=download, verify=lambda p: None)
    assert len(calls) == 1 and verified == [b'approved']


def test_corrupt_download_leaves_no_staged_runtime(tmp_path):
    def download(command, **kwargs):
        (Path(command[-1]) / 'runtime.tar.gz').write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='checksum'):
        staging.stage(entry(), 'runtime-test', tmp_path, download=download, verify=lambda p: pytest.fail('untrusted runtime'))
    assert list(tmp_path.iterdir()) == []


def test_missing_draft_fails_without_partial_staging(tmp_path):
    def download(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)
    with pytest.raises(subprocess.CalledProcessError):
        staging.stage(entry(), 'runtime-test', tmp_path, download=download, verify=lambda p: None)
    assert list(tmp_path.iterdir()) == []


def test_existing_unexpected_runtime_preserved(tmp_path):
    path = tmp_path / 'runtime.tar.gz'
    path.write_bytes(b'user content')
    with pytest.raises(ValueError, match='Existing runtime'):
        staging.stage(entry(), 'runtime-test', tmp_path, verify=lambda p: None)
    assert path.read_bytes() == b'user content'
