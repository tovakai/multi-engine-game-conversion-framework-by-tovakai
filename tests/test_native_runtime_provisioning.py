from pathlib import Path
import io,json,hashlib,tarfile
import pytest
from megcfbt import native_runtime as runtime
from megcfbt.native_backend import NativeBuildError
from megcfbt.router import automatic_native_runtime_available,build_source
from megcfbt.models import UnifiedInspection


def fixture(tmp_path,monkeypatch,engine='gamemaker',machine=183):
    exe=runtime.EXECUTABLES[engine]
    elf=bytearray(64);elf[:6]=b'\x7fELF\x02\x01';elf[18:20]=machine.to_bytes(2,'little')
    files={exe:bytes(elf),'LICENSE.txt':b'synthetic open source notice'}
    manifest={'recipe_id':engine+'-test-v1','architecture':'aarch64',
              'files':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()}}
    files['engine-capabilities.json']=json.dumps(manifest).encode()
    packed=io.BytesIO()
    with tarfile.open(fileobj=packed,mode='w:gz') as tar:
        for name,data in files.items():
            info=tarfile.TarInfo(name);info.size=len(data);tar.addfile(info,io.BytesIO(data))
    data=packed.getvalue();entry={'recipe_id':manifest['recipe_id'],'executable':exe,'archive_files':list(files),
        'url':'https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/releases/download/test/'+engine+'.tar.gz',
        'sha256':hashlib.sha256(data).hexdigest()}
    index=tmp_path/'index.json';index.write_text(json.dumps({'recipes':{engine:entry}}))
    monkeypatch.setattr(runtime,'INDEX_PATH',index)
    monkeypatch.setenv('RPGMFRAME_CACHE_DIR',str(tmp_path/'cache'))
    monkeypatch.delenv('MEGCFBT_NATIVE_RUNTIME_DIR',raising=False)
    monkeypatch.delenv(engine.upper()+'FRAME_RUNTIME',raising=False)
    class Response(io.BytesIO):headers={'Content-Length':str(len(data))}
    calls=[]
    monkeypatch.setattr('megcfbt.runtime_download.urllib.request.urlopen',lambda *a,**k:(calls.append(a),Response(data))[1])
    return entry,calls


@pytest.mark.parametrize('engine',['gamemaker','love','ags','easyrpg'])
def test_download_cache_and_repair_are_shared(tmp_path,monkeypatch,engine):
    entry,calls=fixture(tmp_path,monkeypatch,engine)
    events=[]
    result=runtime.resolve_runtime(engine,download_progress=lambda *event:events.append(event))
    assert events[-1][0]==events[-1][1]
    assert runtime.resolve_runtime(engine)==result and len(calls)==1
    (result/entry['executable']).write_bytes(b'corrupted')
    runtime.resolve_runtime(engine)
    assert len(calls)==2 and runtime._validate(result,entry)


def test_no_unrelated_runtime_for_unknown_engine(tmp_path):
    assert runtime.recipe_entry('unity') is None
    with pytest.raises(NativeBuildError,match='No published'):
        runtime.resolve_runtime('unity')


def test_explicit_override_precedes_download(tmp_path,monkeypatch):
    _,calls=fixture(tmp_path,monkeypatch)
    override=tmp_path/'manual'
    assert runtime.resolve_runtime('gamemaker',override)==override
    assert calls==[]


def test_wrong_architecture_is_not_cached(tmp_path,monkeypatch):
    fixture(tmp_path,monkeypatch,machine=62)
    with pytest.raises(NativeBuildError,match='ARM64'):
        runtime.resolve_runtime('gamemaker')


def test_checksum_failure_is_actionable(tmp_path,monkeypatch):
    fixture(tmp_path,monkeypatch)
    index=tmp_path/'index.json';data=json.loads(index.read_text())
    data['recipes']['gamemaker']['sha256']='0'*64;index.write_text(json.dumps(data))
    with pytest.raises(NativeBuildError,match='SHA-256 mismatch'):
        runtime.resolve_runtime('gamemaker')


@pytest.mark.parametrize('field,value',[('url','https://example.org/untrusted'),('archive_files',['../escape']),
                                      ('executable','wrong'),('recipe_id','../../escape')])
def test_untrusted_index_entries_are_rejected(tmp_path,monkeypatch,field,value):
    fixture(tmp_path,monkeypatch)
    index=tmp_path/'index.json';data=json.loads(index.read_text());data['recipes']['gamemaker'][field]=value
    index.write_text(json.dumps(data));assert not runtime.automatic_runtime_available('gamemaker')


def test_native_gui_indicates_automatic_provisioning(tmp_path,monkeypatch):
    from test_gui_renpy_fallback import app_for_inspection
    fixture(tmp_path,monkeypatch)
    app=app_for_inspection(tmp_path)
    inspected=UnifiedInspection(app.source,'gamemakerframe','gamemaker','GameMaker','2.0.0.0','test',
                               'needs_testing','high','gamemaker-vm',True)
    assert automatic_native_runtime_available(inspected)
    app._show_inspection(inspected)
    assert app.runtime_button.values['text']=='RUNTIME // AUTOMATIC ARM64  //  OVERRIDE…'
    assert app.convert_btn.values['state']=='normal'


def test_native_build_downloads_without_override_and_preserves_source(tmp_path,monkeypatch):
    from test_native_backends import gm_data
    _,calls=fixture(tmp_path,monkeypatch)
    source=tmp_path/'game';source.mkdir();gm_data(source/'data.win')
    before=(source/'data.win').read_bytes()
    monkeypatch.setattr('megcfbt.router.complete_frame_artwork',lambda *a,**k:None)
    result=build_source(source,output=tmp_path/'output',archive=False)
    assert len(calls)==1 and (result.output_path/'runtime/butterscotch').is_file()
    assert (result.output_path/'runtime/LICENSE.txt').exists()
    assert (source/'data.win').read_bytes()==before
