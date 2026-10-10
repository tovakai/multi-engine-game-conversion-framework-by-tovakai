"""Automatic Windows provisioning, without relying on native source builds."""
from pathlib import Path
from dataclasses import replace
import hashlib,io,json,struct,tarfile
import pytest
from rpgmframe import godot_runtime_download as download
from rpgmframe.godot_custom_runtime import GODOTSTEAM_351_RECIPE,automatic_recipe_for,RECIPE_ID
from megcfbt.router import automatic_custom_godot_runtime_available,inspect_source,build_source
from megcfbt.models import UnifiedInspection
from megcfbt import gui


def inspection(root,version='3.5.1',evidence=('game.exe: built-in GodotSteam module',)):
    return UnifiedInspection(root,'rpgmframe','godot','Godot',version,'Synthetic export',
                             'unknown','high','godot-custom',False,evidence=evidence)


@pytest.mark.parametrize('version',['3.5.1','3.7.0','4.6.0','4.7.2'])
def test_supported_recipes_are_available_without_windows_compilation(tmp_path,monkeypatch,version):
    monkeypatch.setattr('megcfbt.router.host_can_build_automatic_runtime',lambda:False)
    result=inspection(tmp_path,version)
    assert automatic_recipe_for(version,custom_build=True,godotsteam=True)
    assert automatic_custom_godot_runtime_available(result)


@pytest.mark.parametrize('kind',['godot-encrypted','godot-native-extensions'])
def test_published_recipe_does_not_bypass_pack_requirements(tmp_path,kind):
    assert not automatic_custom_godot_runtime_available(replace(inspection(tmp_path),runtime_kind=kind))


@pytest.mark.parametrize('module',['FMOD','Spine','Threen','UnknownPlugin'])
def test_only_supported_builtin_module_is_eligible(tmp_path,module):
    result=inspection(tmp_path,evidence=('game.exe: built-in GodotSteam module','game.exe: BUILT-IN MODULE '+module))
    assert not automatic_custom_godot_runtime_available(result)
    assert automatic_custom_godot_runtime_available(inspection(tmp_path,evidence=('game.exe: built-in module GodotSteam',)))


def test_gui_enables_convert_and_describes_automatic_runtime(tmp_path,monkeypatch):
    # Reuse the GUI test widget adapter; exercise real eligibility/rendering.
    from test_gui_renpy_fallback import app_for_inspection
    app=app_for_inspection(tmp_path)
    monkeypatch.setattr('megcfbt.router.host_can_build_automatic_runtime',lambda:False)
    app._show_inspection(inspection(app.source))
    assert app._conversion_allowed()
    assert app.convert_btn.values['state']=='normal'
    assert 'AUTO GODOTSTEAM' in app.runtime_button.values['text']
    assert app.drop_label.values['text']=='AUTOMATIC GODOTSTEAM RUNTIME AVAILABLE'
    assert 'No manual runtime selection' in app.notes_box.contents


def archive_fixture(tmp_path,monkeypatch,*,arch=183,manifest_changes=None,corrupt_tar=False):
    elf=bytearray(64);elf[:6]=b'\x7fELF\x02\x01';elf[18:20]=arch.to_bytes(2,'little')
    files={'godot.arm64':bytes(elf),'LICENSE-Godot.txt':b'synthetic notice'}
    manifest={'recipe_id':GODOTSTEAM_351_RECIPE,'engine_version':'3.5.1',
        'capabilities':{'legacy_steam_init_dictionary':True},
        'steam_api_dependency':{'provider':'steam-frame-installed'},
        'files':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()}}
    manifest.update(manifest_changes or {})
    files['runtime.json']=json.dumps(manifest).encode()
    packed=io.BytesIO()
    with tarfile.open(fileobj=packed,mode='w:gz') as tar:
        for name,data in files.items():
            info=tarfile.TarInfo(name);info.size=len(data);tar.addfile(info,io.BytesIO(data))
    data=b'not a tar archive' if corrupt_tar else packed.getvalue()
    entry={'url':'https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/releases/download/test/runtime.tar.gz',
        'sha256':hashlib.sha256(data).hexdigest(),'archive_files':list(files)}
    index=tmp_path/'index.json';index.write_text(json.dumps({'recipes':{GODOTSTEAM_351_RECIPE:entry}}))
    monkeypatch.setattr(download,'INDEX_PATH',index)
    monkeypatch.setattr(download,'_cache_root',lambda:tmp_path/'cache')
    calls=[]
    class Response(io.BytesIO):headers={'Content-Length':str(len(data))}
    monkeypatch.setattr(download.urllib.request,'urlopen',lambda *a,**k:(calls.append(a),Response(data))[1])
    return entry,calls


def test_download_cache_reuse_and_tampered_cache_repair(tmp_path,monkeypatch):
    entry,calls=archive_fixture(tmp_path,monkeypatch)
    progress=[]
    result=download.ensure_downloaded_runtime(GODOTSTEAM_351_RECIPE,download_progress=lambda *v:progress.append(v))
    assert progress[-1][0]==progress[-1][1]
    assert (result/'LICENSE-Godot.txt').read_bytes()==b'synthetic notice'
    assert not (result/'libsteam_api.so').exists()
    assert download.ensure_downloaded_runtime(GODOTSTEAM_351_RECIPE)==result and len(calls)==1
    (result/'godot.arm64').write_bytes((result/'godot.arm64').read_bytes()+b'corrupt')
    assert not download._validate(result,GODOTSTEAM_351_RECIPE)
    download.ensure_downloaded_runtime(GODOTSTEAM_351_RECIPE)
    assert len(calls)==2 and download._validate(result,GODOTSTEAM_351_RECIPE)


@pytest.mark.parametrize('change',[{'recipe_id':RECIPE_ID},{'capabilities':[]},{'capabilities':{}},
                                  {'steam_api_dependency':[]},{'files':{}},{'engine_version':'3.7.0'}])
def test_rejects_wrong_recipe_or_missing_legacy_capability(tmp_path,monkeypatch,change):
    archive_fixture(tmp_path,monkeypatch,manifest_changes=change)
    with pytest.raises(download.RuntimeDownloadError,match='validation'):
        download.ensure_downloaded_runtime(GODOTSTEAM_351_RECIPE)
    assert not (tmp_path/'cache/runtimes/godot-custom'/GODOTSTEAM_351_RECIPE).exists()


def test_rejects_x86_runtime(tmp_path,monkeypatch):
    archive_fixture(tmp_path,monkeypatch,arch=62)
    with pytest.raises(download.RuntimeDownloadError,match='ARM64'):
        download.ensure_downloaded_runtime(GODOTSTEAM_351_RECIPE)


def test_rejects_351_archive_checksum_mismatch(tmp_path,monkeypatch):
    archive_fixture(tmp_path,monkeypatch)
    index=tmp_path/'index.json'
    data=json.loads(index.read_text());data['recipes'][GODOTSTEAM_351_RECIPE]['sha256']='0'*64
    index.write_text(json.dumps(data))
    with pytest.raises(download.RuntimeDownloadError,match='SHA-256 mismatch'):
        download.ensure_downloaded_runtime(GODOTSTEAM_351_RECIPE)


def test_failed_cache_publish_restores_previous_directory(tmp_path,monkeypatch):
    archive_fixture(tmp_path,monkeypatch)
    target=download.ensure_downloaded_runtime(GODOTSTEAM_351_RECIPE)
    (target/'godot.arm64').write_bytes(b'previous cache')
    rename=Path.rename
    def fail_publish(path,destination):
        if path.name=='extracted':raise OSError('simulated filesystem failure')
        return rename(path,destination)
    monkeypatch.setattr(Path,'rename',fail_publish)
    with pytest.raises(download.RuntimeDownloadError,match='install verified runtime cache'):
        download.ensure_downloaded_runtime(GODOTSTEAM_351_RECIPE)
    assert (target/'godot.arm64').read_bytes()==b'previous cache'


def test_reports_corrupted_archive_with_verified_checksum(tmp_path,monkeypatch):
    archive_fixture(tmp_path,monkeypatch,corrupt_tar=True)
    with pytest.raises(download.RuntimeDownloadError,match='unpack verified runtime archive'):
        download.ensure_downloaded_runtime(GODOTSTEAM_351_RECIPE)


def test_failed_download_preserves_existing_cache(tmp_path,monkeypatch):
    archive_fixture(tmp_path,monkeypatch)
    result=download.ensure_downloaded_runtime(GODOTSTEAM_351_RECIPE)
    (result/'godot.arm64').write_bytes(b'previous damaged runtime')
    def fail(*a,**k):raise OSError('offline')
    monkeypatch.setattr(download.urllib.request,'urlopen',fail)
    with pytest.raises(download.RuntimeDownloadError,match='offline'):
        download.ensure_downloaded_runtime(GODOTSTEAM_351_RECIPE)
    assert (result/'godot.arm64').read_bytes()==b'previous damaged runtime'


@pytest.mark.parametrize('unsafe',['output','receipt'])
def test_frozen_gui_verification_refuses_writing_into_source(tmp_path,monkeypatch,unsafe):
    from megcfbt.gui_verification import main
    source=tmp_path/'source';source.mkdir()
    output=source/'output' if unsafe=='output' else tmp_path/'output'
    output.mkdir()
    receipt=source/'receipt.json' if unsafe=='receipt' else tmp_path/'receipt.json'
    monkeypatch.setattr(gui,'ConverterApp',lambda:pytest.fail('Must reject before creating GUI'))
    with pytest.raises(SystemExit):
        main(['--verify-gui-conversion',str(source),'--output-dir',str(output),'--receipt',str(receipt)])
    assert not receipt.exists()


def test_conversion_packages_published_engine_notices_and_guard(tmp_path,monkeypatch):
    archive_fixture(tmp_path,monkeypatch)
    source=tmp_path/'source';source.mkdir()
    (source/'game.exe').write_bytes(b'MZ\0modules/godotsteam/godotsteam.cpp\0')
    (source/'game.pck').write_bytes(struct.pack('<IIIII',0x43504447,1,3,5,1)+b'\0'*64+struct.pack('<I',0))
    (source/'steam_appid.txt').write_text('12345\n')
    before={p.name:p.read_bytes() for p in source.iterdir()}
    monkeypatch.setattr('megcfbt.router.host_can_build_automatic_runtime',lambda:False)
    monkeypatch.setattr('megcfbt.router.complete_frame_artwork',lambda *a,**k:None)
    result=build_source(source,output=tmp_path/'output',archive=False)
    assert (result.output_path/'godot.arm64').is_file()
    assert (result.output_path/'LICENSE-Godot.txt').is_file()
    assert (result.output_path/'libframe_steam_env.so').is_file()
    assert not (result.output_path/'libsteam_api.so').exists()
    assert '/opt/steamvr/bin/linuxarm64' in result.launcher_path.read_text()
    assert (result.output_path/'game/game.pck').read_bytes()==before['game.pck']
    assert {p.name:p.read_bytes() for p in source.iterdir()}==before
