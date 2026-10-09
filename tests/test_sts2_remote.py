import hashlib
import json
from pathlib import Path
from unittest import mock

import pytest

from megcfbt.sts2_remote import FrameSettings, FrameTransport, RemoteError, backend_bundle, digest_file


def test_settings_reject_shell_injection_and_original_installation_paths():
    for host in ('-oProxyCommand=bad','frame;command','$(command)'):
        with pytest.raises(RemoteError): FrameSettings(host=host).validate()
    for path in ('/usr/local/app','/opt/app','/home/steamos/Steam/steamapps/common/Game','/run/media/steamos/SD512/../Game','/run/media/steamos/SD512/$(command)','/run/media/steamos/SD512/quote"'):
        with pytest.raises(RemoteError): FrameSettings(remote_root=path).validate()


def test_legacy_settings_do_not_require_ownership_attestation(tmp_path):
    with mock.patch('megcfbt.sts2_remote.settings_directory', return_value=tmp_path):
        (tmp_path / 'connection.json').write_text(json.dumps({
            'host': 'frame',
            'remote_sdk': '/home/steamos/Downloads/fmodstudioapi20315linux.tar.gz',
            'authorized': False,  # Legacy persisted UI field, intentionally ignored.
        }))
        settings = FrameSettings.load()
        assert settings.host == 'frame'
        assert settings.remote_sdk.endswith('fmodstudioapi20315linux.tar.gz')
        assert 'authorized' not in FrameSettings.__dataclass_fields__
        settings.validate()
        settings.save()
        assert 'authorized' not in json.loads((tmp_path / 'connection.json').read_text())


def test_transport_enforces_host_verification_and_noninteractive_key_authentication(tmp_path):
    settings=FrameSettings(host='192.168.0.102')
    with mock.patch('megcfbt.sts2_remote.ssh_program',return_value='ssh'), \
         mock.patch('megcfbt.sts2_remote.settings_directory',return_value=tmp_path):
        args=FrameTransport(settings).arguments("python3 -c 'print(1)'")
    assert 'StrictHostKeyChecking=yes' in args
    assert 'BatchMode=yes' in args
    assert args[-2]=='steamos@192.168.0.102'
    assert args[-1]=="python3 -c 'print(1)'"


def test_bundle_contains_software_only_and_remote_worker(tmp_path):
    import tarfile
    target=tmp_path/'software.tar'
    backend_bundle(target)
    with tarfile.open(target) as package:
        names={p.name for p in package}
    assert {'package_converter.py','remote_worker.py','pipeline.py','retail_107.py','converter_profile_v107.json','steam_launch.py'} <= names
    assert not any(n.endswith(('.dll','.so','.pck','.nupkg','.tpz')) for n in names)


def test_prefix_digest_supports_resumable_transfer(tmp_path):
    path=tmp_path/'payload'
    path.write_bytes(b'prefix'+b'new suffix')
    assert digest_file(path,6)==hashlib.sha256(b'prefix').hexdigest()
    assert digest_file(path)==hashlib.sha256(path.read_bytes()).hexdigest()


def test_in_process_detection_does_not_require_external_python(tmp_path):
    from megcfbt import sts2
    (tmp_path/'SlayTheSpire2.pck').write_bytes(b'detection marker')
    (tmp_path/'data_sts2_windows_x86_64').mkdir()
    (tmp_path/'data_sts2_windows_x86_64/sts2.dll').write_bytes(b'detection marker')
    (tmp_path/'release_info.json').write_text('{"version":"unsupported","commit":"unknown"}')
    with mock.patch.object(sts2,'python_command',side_effect=AssertionError('External interpreter invoked')):
        result=sts2.summary(tmp_path)
    assert result.backend=='sts2' and not result.buildable


def test_interrupted_upload_retains_prefix_and_resumes_with_full_hash(tmp_path):
    import io
    from types import SimpleNamespace
    from megcfbt.sts2_backend import module
    worker=module('remote_worker')
    root=tmp_path/'job-test';root.mkdir()
    (root/'job.json').write_text(json.dumps({'kind':'megcfbt-sts2-job-v1','id':'test'}))
    raw=b'prefix'+b'continuation';digest=hashlib.sha256(raw).hexdigest()
    with mock.patch.object(worker.sys,'stdin',SimpleNamespace(buffer=io.BytesIO(raw[:6]))):
        with pytest.raises(ValueError,match='Interrupted upload'):
            worker.upload(root,'source.tar',len(raw),digest,0)
    assert (root/'source.tar.part').read_bytes()==raw[:6]
    with mock.patch.object(worker.sys,'stdin',SimpleNamespace(buffer=io.BytesIO(raw[6:]))):
        worker.upload(root,'source.tar',len(raw),digest,6)
    assert (root/'source.tar').read_bytes()==raw
    assert not (root/'source.tar.part').exists()


def test_worker_rejects_unowned_job_and_symlink_escape(tmp_path):
    from megcfbt.sts2_backend import module
    worker=module('remote_worker')
    root=tmp_path/'other-directory';root.mkdir()
    (root/'job.json').write_text(json.dumps({'kind':'megcfbt-sts2-job-v1','id':'test'}))
    with pytest.raises(ValueError,match='application-owned'): worker.job_root(root)
    link=tmp_path/'job-test'
    try: link.symlink_to(root,target_is_directory=True)
    except OSError as exc:
        if getattr(exc,'winerror',None)==1314: pytest.skip('Windows symlink privilege unavailable; escape guard tested on Linux')
        raise
    with pytest.raises(ValueError,match='Symbolic link'): worker.job_root(link)


def test_changed_existing_host_identity_cannot_be_overwritten(tmp_path):
    settings=FrameSettings(host='frame')
    (tmp_path/'known_hosts').write_text('existing identity\n')
    from types import SimpleNamespace
    with mock.patch('megcfbt.sts2_remote.settings_directory',return_value=tmp_path), \
         mock.patch('megcfbt.sts2_remote.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=b'known key')):
        with pytest.raises(RemoteError,match='already has a trusted identity'):
            FrameTransport(settings).trust_new_host('new identity')
    assert (tmp_path/'known_hosts').read_text()=='existing identity\n'


def test_original_input_reuse_requires_full_hash_and_owned_job(tmp_path,capsys):
    from megcfbt.sts2_backend import module
    worker=module('remote_worker')
    def job(identity):
        root=tmp_path/('job-'+identity);root.mkdir()
        (root/'job.json').write_text(json.dumps({'kind':'megcfbt-sts2-job-v1','id':identity}))
        return root
    original=job('original');new=job('new')
    raw=b'untouched input archive';(original/'source.tar').write_bytes(raw)
    worker.reuse_input(new,'source.tar',len(raw),'0'*64)
    assert not (new/'source.tar').exists()
    worker.reuse_input(new,'source.tar',len(raw),hashlib.sha256(raw).hexdigest())
    assert (new/'source.tar').read_bytes()==raw
    with pytest.raises(ValueError): worker.reuse_input(new,'prepared-native.so',len(raw),hashlib.sha256(raw).hexdigest())


def test_transport_preserves_remote_worker_diagnostic(tmp_path):
    import subprocess
    transport=FrameTransport(FrameSettings(host='192.168.0.102'))
    result=subprocess.CompletedProcess([],2,b'{"type":"error","message":"Steam library UI debug endpoint is unavailable"}',b'')
    with mock.patch('megcfbt.sts2_remote.ssh_program',return_value='ssh'), mock.patch('megcfbt.sts2_remote.subprocess.run',return_value=result):
        with pytest.raises(RemoteError,match='Steam library UI debug endpoint'):
            transport.run('worker')
