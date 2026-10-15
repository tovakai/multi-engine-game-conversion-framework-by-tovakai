from pathlib import Path
import hashlib,io,json,struct,tarfile
from unittest.mock import Mock
import pytest
from monoframe import profiles,runtime,backend
from megcfbt.runtime_download import ensure_bundle,RuntimeDownloadError


def elf(machine=183):
    data=bytearray(64);data[:6]=b'\x7fELF\x02\x01';struct.pack_into('<H',data,18,machine)
    return bytes(data)


def pe(machine=0x8664):
    data=bytearray(512);data[:2]=b'MZ';struct.pack_into('<I',data,60,128);data[128:132]=b'PE\0\0';struct.pack_into('<H',data,132,machine)
    return bytes(data)


def game(tmp_path,monkeypatch):
    root=tmp_path/'source';root.mkdir();(root/'Content').mkdir()
    hashes={}
    for name in profiles.STARDEW_HASHES:
        data=b'MZfixture-'+name.encode();(root/name).write_bytes(data);hashes[name]=hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(profiles,'STARDEW_HASHES',hashes)
    (root/'Stardew Valley.runtimeconfig.json').write_text(json.dumps({'runtimeOptions':{'tfm':'net6.0','includedFrameworks':[{'name':'Microsoft.NETCore.App','version':'6.0.32'}]}}))
    return root


def sdk(tmp_path):
    root=tmp_path/'sdk';root.mkdir()
    files={'dotnet/dotnet':elf(),'native/libshim.so':elf(),'managed/MonoGame.Framework.dll':b'MZmanaged',
           'prepare/windows-x64/MainlineGameDataPatcher.exe':pe(),'prepare/managed/MainlineGameDataPatcher.dll':b'MZpreparer'}
    for name,data in files.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    manifest={'profile':profiles.STARDEW_PROFILE,'architecture':'aarch64','recipe_id':'monoframe-test',
              'files':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()},
              'runtime_files':[name for name in files if not name.startswith('prepare/')]}
    (root/'engine-capabilities.json').write_text(json.dumps(manifest))
    return root


def test_guarded_identity_and_smapi_rejection(tmp_path,monkeypatch):
    root=game(tmp_path,monkeypatch)
    assert profiles.matches_stardew(root)
    assert backend.inspect_game(root).buildable
    (root/'StardewModdingAPI.dll').write_bytes(b'modloader')
    assert not profiles.matches_stardew(root)
    assert not backend.inspect_game(root).buildable


def test_published_recipe_enables_automatic_windows_conversion(tmp_path,monkeypatch):
    from megcfbt.router import automatic_native_runtime_available
    root=game(tmp_path,monkeypatch)
    inspection=backend.inspect_game(root)
    assert inspection.buildable
    assert runtime.recipe_entry()['recipe_id']=='monoframe-stardew-1615-net6032-arm64-v1'
    assert automatic_native_runtime_available(inspection)


def test_modified_game_and_malformed_runtimeconfig_rejected(tmp_path,monkeypatch):
    root=game(tmp_path,monkeypatch)
    (root/'Stardew Valley.dll').write_bytes(b'altered')
    assert not profiles.matches_stardew(root)
    (root/'Stardew Valley.runtimeconfig.json').write_text('{"runtimeOptions":[]}')
    assert not profiles.matches_stardew(root)


def test_sdk_architecture_integrity_and_target_only_copy(tmp_path):
    root=sdk(tmp_path)
    assert runtime.validate_sdk(root)
    target=tmp_path/'game-runtime';runtime.copy_game_runtime(root,target)
    assert (target/'dotnet/dotnet').is_file()
    assert not (target/'prepare').exists()
    (root/'native/libshim.so').write_bytes(elf(62))
    assert not runtime.validate_sdk(root)


def test_windows_preparer_architecture_is_checked(tmp_path):
    root=sdk(tmp_path)
    path=root/'prepare/windows-x64/MainlineGameDataPatcher.exe';path.write_bytes(pe(0xaa64))
    manifest=json.loads((root/'engine-capabilities.json').read_text());manifest['files']['prepare/windows-x64/MainlineGameDataPatcher.exe']=hashlib.sha256(path.read_bytes()).hexdigest()
    (root/'engine-capabilities.json').write_text(json.dumps(manifest))
    assert not runtime.validate_sdk(root)


def test_nested_download_cache_and_digest(tmp_path,monkeypatch):
    raw=io.BytesIO()
    with tarfile.open(fileobj=raw,mode='w:gz') as archive:
        member=tarfile.TarInfo('dotnet/dotnet');data=elf();member.size=len(data);archive.addfile(member,io.BytesIO(data))
    payload=raw.getvalue();requests=[]
    class Response(io.BytesIO):headers={}
    monkeypatch.setattr('urllib.request.urlopen',lambda *a,**kw:requests.append(a) or Response(payload))
    entry={'url':'https://example.invalid/sdk','sha256':hashlib.sha256(payload).hexdigest(),'archive_files':['dotnet/dotnet'],'executable':'dotnet/dotnet'}
    target=tmp_path/'cache'
    valid=lambda folder:(folder/'dotnet/dotnet').is_file()
    assert ensure_bundle(entry,target,validate=valid)==target
    assert ensure_bundle(entry,target,validate=valid)==target
    assert len(requests)==1
    entry['sha256']='0'*64
    with pytest.raises(RuntimeDownloadError,match='SHA-256'):
        ensure_bundle(entry,tmp_path/'other',validate=valid)


@pytest.mark.parametrize('name',['../escape','/absolute','a/../escape','a\\escape','C:/escape','a//file','a/./file'])
def test_nested_manifest_path_escape_rejected(tmp_path,name):
    with pytest.raises(RuntimeDownloadError,match='manifest'):
        ensure_bundle({'archive_files':[name]},tmp_path/'cache',validate=lambda p:False)


def test_backend_uses_host_preparer_and_preserves_original(tmp_path,monkeypatch):
    root=game(tmp_path,monkeypatch);bundle=sdk(tmp_path)
    original=(root/'Stardew Valley.dll').read_bytes()
    calls=[]
    def prepare(command,**kwargs):
        calls.append(command)
        target=Path(command[command.index('--game-dir')+1]);(target/'Stardew Valley.dll').write_bytes(b'prepared')
        return type('Result',(),{'returncode':0,'stdout':'Prepared managed game'})()
    monkeypatch.setattr(backend.subprocess,'run',prepare)
    monkeypatch.setattr(backend,'preparation_command',lambda sdk,tool:['synthetic-preparer',str(sdk/'prepare/managed'/(tool+'.dll'))])
    result=backend.build_game(root,output=tmp_path/'output',runtime=bundle)
    assert (root/'Stardew Valley.dll').read_bytes()==original
    assert (result.output_path/'game/Stardew Valley.dll').read_bytes()==b'prepared'
    assert not (result.output_path/'runtime/prepare').exists()
    assert 'DOTNET_ROOT' in result.launcher_path.read_text()
    assert calls
