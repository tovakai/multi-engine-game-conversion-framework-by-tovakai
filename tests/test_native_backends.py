from pathlib import Path
import struct
import zipfile
import pytest

from megcfbt.router import inspect_source, build_source, ConversionError
from megcfbt.native_backend import NativeBuildError, validate_runtime
from gamemakerframe.backend import build_game
from rpgmframe.source import _safe_extract_zip, SourceError
from megcfbt.steam_context import steam_app_id_for_source


def gm_data(path, *, code=True, wad=17):
    gen = bytearray(60)
    gen[1] = wad
    struct.pack_into('<4I', gen, 44, 2, 0, 0, 0)
    chunks = b'GEN8' + struct.pack('<I', len(gen)) + gen
    if code:
        chunk = struct.pack('<II', 1, 0)
        chunks += b'CODE' + struct.pack('<I', len(chunk)) + chunk
    path.write_bytes(b'FORM' + struct.pack('<I',len(chunks)) + chunks)


def elf(path, machine=183):
    data = bytearray(20)
    data[:6] = b'\x7fELF\x02\x01'
    struct.pack_into('<H', data,18,machine)
    path.write_bytes(data)


def test_gamemaker_routes_and_rejects_yyc(tmp_path):
    gm_data(tmp_path/'data.win')
    assert inspect_source(tmp_path).backend == 'gamemakerframe'
    gm_data(tmp_path/'data.win', code=False)
    assert not inspect_source(tmp_path).buildable


def test_gamemaker_preserves_external_assets_and_source(tmp_path):
    source = tmp_path/'source'
    source.mkdir()
    gm_data(source/'data.win')
    (source/'music.ogg').write_bytes(b'music')
    runtime = tmp_path/'runtime'
    runtime.mkdir()
    elf(runtime/'butterscotch')
    output = tmp_path/'output'
    result = build_game(source,output=output,runtime=runtime)
    assert (output/'game/music.ogg').read_bytes() == b'music'
    assert (source/'data.win').exists()
    assert 'exec "$ROOT/runtime/butterscotch" data.win' in result.launcher_path.read_text()


def test_wrong_runtime_rejected_before_replacing_output(tmp_path):
    source = tmp_path/'source'
    source.mkdir()
    gm_data(source/'data.win')
    output = tmp_path/'output'
    output.mkdir()
    (output/'keep').write_text('previous successful conversion')
    runtime = tmp_path/'runtime'
    runtime.mkdir()
    elf(runtime/'butterscotch',62)
    with pytest.raises(NativeBuildError,match='ARM64'):
        build_game(source,output=output,runtime=runtime,force=True)
    assert (output/'keep').exists()


def test_fused_love_export_detected(tmp_path):
    path = tmp_path/'Game.exe'
    path.write_bytes(b'MZ fake launcher')
    with zipfile.ZipFile(path,'a') as archive:
        archive.writestr('main.lua','function love.draw() end')
        archive.writestr('conf.lua','function love.conf(t) t.version="11.4" end')
    result = inspect_source(tmp_path)
    assert result.backend == 'loveframe' and result.engine_version == '11.4'


def test_love_platform_wrapper_with_sibling_metadata(tmp_path):
    wrapper = tmp_path/'win64_steam'
    wrapper.mkdir()
    with zipfile.ZipFile(wrapper/'Game.exe','w') as archive:
        archive.writestr('main.lua','function love.draw() end')
    (tmp_path/'steam_appid.txt').write_text('123456')
    assert inspect_source(tmp_path).backend == 'loveframe'


def test_ags_embedded_clib_detected(tmp_path):
    (tmp_path/'Game.exe').write_bytes(b'MZ'+b'\0'*50+b'CLIB\x01\x02\x03\x04SIGE')
    assert inspect_source(tmp_path).backend == 'agsframe'


@pytest.mark.parametrize('names',[
    ['../escape','main.lua'], ['C:/escape','main.lua'],
    ['main.lua','MAIN.LUA'], ['game','game/main.lua'],
    ['game\\main.lua','game/main.lua'],
])
def test_archive_collisions_rejected_before_extracting(tmp_path,names):
    path = tmp_path/'input.zip'
    with zipfile.ZipFile(path,'w') as archive:
        for name in names:
            archive.writestr(name,'test')
    destination = tmp_path/'unpacked'
    with pytest.raises(SourceError):
        _safe_extract_zip(path,destination)
    assert not list(destination.iterdir())


def test_force_cannot_replace_original_archive(tmp_path):
    path = tmp_path/'input.zip'
    path.write_bytes(b'original archive bytes')
    with pytest.raises(ConversionError,match='original source'):
        build_source(path,output=path,force=True)
    assert path.read_bytes() == b'original archive bytes'


def test_generated_zip_cannot_replace_original_archive(tmp_path):
    path = tmp_path/'Game-linux-aarch64.zip'
    path.write_bytes(b'original archive bytes')
    with pytest.raises(ConversionError,match='original source archive'):
        build_source(path,output=tmp_path/'Game-frame',force=True)
    assert path.read_bytes() == b'original archive bytes'


def test_steam_manifest_matches_export_inside_platform_wrapper(tmp_path):
    steam = tmp_path/'steamapps'
    source = steam/'common/My Game/win64'
    source.mkdir(parents=True)
    (steam/'appmanifest_12345.acf').write_text('"AppState" { "appid" "12345" "installdir" "My Game" }')
    (steam/'appmanifest_999.acf').write_text('"AppState" { "appid" "999" "installdir" "Different Game" }')
    assert steam_app_id_for_source(source) == '12345'


def test_source_zip_is_extracted_once_for_native_build(tmp_path,monkeypatch):
    from megcfbt import router
    from contextlib import contextmanager
    original = router.prepare_source
    archive = tmp_path/'Original.zip'
    with zipfile.ZipFile(archive,'w') as zipped:
        zipped.writestr('main.lua','function love.draw() end')
    runtime = tmp_path/'runtime'
    runtime.mkdir()
    elf(runtime/'love')
    extracted = []
    @contextmanager
    def tracked(path,**kwargs):
        if path.is_file():
            extracted.append(path)
        with original(path,**kwargs) as result:
            yield result
    monkeypatch.setattr(router,'prepare_source',tracked)
    monkeypatch.setattr(router,'complete_frame_artwork',lambda *args,**kwargs:None)
    result = build_source(archive,output=tmp_path/'output',backend_runtime=runtime,archive=False)
    assert extracted == [archive]
    assert result.source_path == archive and result.launcher_path.is_file()
