import json
import shlex
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import zipfile

import pytest

from megcfbt import sts2
from megcfbt.sts2_backend import module


@pytest.fixture
def conversion():
    # Reuse the standalone converter's synthetic archives/pack; no game fixtures.
    case = module('test_convert_sts2').ConversionTests()
    case.setUp()
    try:
        yield case
    finally:
        case.doCleanups()


def test_zip_transfer_extracts_and_finishes_without_ssh(conversion, tmp_path):
    case = conversion
    handoff = module('prepare_handoff')
    installer = module('frame_install')
    converter = module('convert_sts2')
    transform = module('test_patch_pack').adapt
    output = tmp_path / 'transfer with spaces'
    sdk = tmp_path / 'selected-sdk.tar.gz'; sdk.write_bytes(b'fixture sdk')
    before = case.snapshot(case.source)

    def prepare_sdk(source, target):
        target.mkdir()
        for section, name in [('core', 'libfmod.so.14'), ('studio', 'libfmodstudio.so.14')]:
            path = target / f'api/{section}/lib/arm64/{name}'
            path.parent.mkdir(parents=True)
            path.write_bytes((case.native / name).read_bytes())
        return target

    original_convert = converter.convert
    def prepare_convert(*args, **kwargs):
        return original_convert(*args, **kwargs, _pack_transform=transform)

    with mock.patch.object(handoff, 'inspect_source', return_value={'errors': []}), \
         mock.patch.object(handoff, 'load_profile', return_value=case.profile), \
         mock.patch.object(handoff, 'prepare_sdk', side_effect=prepare_sdk), \
         mock.patch.object(handoff, 'sdk_headers', return_value={}), \
         mock.patch.object(handoff, 'fetch', return_value=case.archives), \
         mock.patch.object(handoff, 'convert', side_effect=prepare_convert), \
         mock.patch('megcfbt.sts2_remote.FrameTransport', side_effect=AssertionError('SSH used')):
        report = handoff.prepare(case.source, output, sdk=sdk, cache=tmp_path/'runtime-cache')
    assert case.snapshot(case.source) == before
    assert Path(report['archive']).suffix == '.zip'
    extracted = tmp_path / 'frame storage'; extracted.mkdir()
    with zipfile.ZipFile(report['archive']) as package:
        assert package.getinfo(output.name + '/install.sh').external_attr >> 16 & 0o111
        package.extractall(extracted)
    root = extracted / output.name
    assert installer.verify_package(root)['kind'] == installer.KIND
    assert (root/'backend/frame_install.py').is_file()
    cli = subprocess.run([sys.executable, '-S', str(root/'backend/frame_install.py'), '--help'],
                         capture_output=True, text=True, timeout=20)
    assert cli.returncode == 0, cli.stderr
    assert not (root/'backend/__pycache__').exists()
    assert not (root/'game').exists()
    (root/'backend/converter_profile_v1.json').write_text(json.dumps(case.profile))
    # The fixture profile needs fixture pins; reseal this synthetic test payload.
    manifest = json.loads((root/installer.HANDOFF).read_bytes())
    for item in manifest['files']:
        if item['path'] == 'backend/converter_profile_v1.json':
            item.update(module('verify_output').inspect(root/item['path']))
    (root/installer.HANDOFF).write_text(json.dumps(manifest))
    runtime = tmp_path/'.local/share/Steam/steamapps/common/SteamLinuxRuntime_4/pressure-vessel-arm64/bin/pressure-vessel-unruntime'
    runtime.parent.mkdir(parents=True); runtime.write_bytes(b'fixture'); runtime.chmod(0o755)
    steamapps = tmp_path/'.local/share/Steam/steamapps'
    (steamapps/'appmanifest_2868840.acf').write_text(
        '"AppState" { "appid" "2868840" "StateFlags" "4" "installdir" "Slay the Spire 2" }')
    steam_game = steamapps/'common/Slay the Spire 2'
    steam_game.mkdir(); (steam_game/'SlayTheSpire2.pck').write_bytes(b'Steam installation fixture')
    with mock.patch.object(installer.platform, 'system', return_value='Linux'), \
         mock.patch.object(installer.platform, 'machine', return_value='aarch64'), \
         mock.patch.object(installer, '__file__', str(root/'backend/frame_install.py')), \
         mock.patch.object(installer, 'STEAM_API', case.native/'libsteam_api64.so'), \
         mock.patch.object(Path, 'home', return_value=tmp_path), \
         mock.patch.object(installer.shutil, 'which', side_effect=lambda name:name), \
         mock.patch.object(installer.shutil, 'disk_usage', return_value=SimpleNamespace(free=20*1024**3)), \
         mock.patch.object(installer, 'sdk_headers', return_value={}), \
         mock.patch.object(installer, 'tools', return_value=Path('/fixture/scons')), \
         mock.patch.object(installer, 'cached_build', return_value=(case.native, case.profile, {'recipe':'fixture'})) as compile_native, \
         mock.patch.object(installer, 'validate_native_bindings', return_value=[]):
        result = installer.install(root, progress=lambda message:None)
        assert result['validation']['errors'] == []
        assert shlex.split(result['launch_command']) == [str(root/'game/play-steam.sh'), '%command%']
        assert module('verify_output').verify(root/'game', check_modes=True)['errors'] == []
        diagnostics = root/'prepared/diagnostics'
        diagnostics.mkdir()
        (diagnostics/'20261011T174734Z-dispatch-509215.json').write_text('{"stage":"steam-dispatch"}')
        (diagnostics/'startup.log').write_text('Launcher diagnostics fixture')
        installer.install(root, progress=lambda message:None)
        backup_folder = root/'steam-integration'
        backup_folder.mkdir()
        (backup_folder/'launch-backup.json').write_text('{"kind":"megcfbt-owned-steam-launch-v1"}')
        installer.install(root, progress=lambda message:None)
        assert compile_native.call_count == 1  # Rerun verifies the completed output.

    unexpected = root/'prepared/untracked.dll'
    unexpected.write_bytes(b'Unexpected game dependency')
    with pytest.raises(ValueError, match='Unexpected transfer file: prepared/untracked.dll'):
        installer.verify_package(root)
    unexpected.unlink()
    (root/'prepared/SlayTheSpire2.pck').write_bytes(b'corrupt transfer')
    with pytest.raises(ValueError, match='wrong-sized|SHA-256'):
        installer.verify_package(root)


def test_installer_refuses_windows_before_any_compilation(tmp_path):
    installer = module('frame_install')
    with mock.patch.object(installer.platform, 'system', return_value='Windows'), \
         mock.patch.object(installer, 'cached_build', side_effect=AssertionError('Compilation attempted')):
        with pytest.raises(ValueError, match='Steam Frame'):
            installer.install(tmp_path)


def test_sdk_discovery_and_saved_selection(tmp_path):
    with mock.patch.object(sts2, 'sdk_directory', return_value=tmp_path/'dependencies'), \
         mock.patch.object(Path, 'home', return_value=tmp_path), \
         mock.patch.dict(sts2.os.environ, {'MEGCFBT_STS2_FMOD_SDK': ''}), \
         mock.patch.object(module('sdk_archive'), 'PIN', dict(size_bytes=7, sha256=__import__('hashlib').sha256(b'fixture').hexdigest())):
        assert sts2.find_sdk() is None
        downloads = tmp_path/'Downloads'; downloads.mkdir()
        archive = downloads/sts2.FMOD_FILENAME; archive.write_bytes(b'fixture')
        assert sts2.find_sdk() == archive
        custom = tmp_path/'my-sdk.tar.gz'; custom.write_bytes(b'fixture')
        sts2.save_sdk(custom)
        assert sts2.find_sdk() == custom


def test_handoff_rejects_overlapping_output_before_work(tmp_path):
    handoff = module('prepare_handoff')
    source = tmp_path/'game'; source.mkdir()
    sdk = tmp_path/'sdk.tar.gz'; sdk.write_bytes(b'fixture')
    with mock.patch.object(handoff, 'fetch', side_effect=AssertionError('Network requested')):
        with pytest.raises(ValueError, match='separate'):
            handoff.prepare(source, source/'output', sdk=sdk, cache=tmp_path/'cache')


def test_steam_launch_command_quotes_frame_storage_path(tmp_path):
    installer = module('frame_install')
    output = tmp_path / "game with 'quotes' and $characters"
    result = installer.installation_result(tmp_path, output, {'errors': []})
    assert shlex.split(result['launch_command']) == [str(output/'play-steam.sh'), '%command%']
