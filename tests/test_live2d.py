from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import json
import struct
import zipfile
import pytest
from renframe import live2d


def elf(machine=183):
    data=bytearray(64);data[:6]=b'\x7fELF\x02\x01';struct.pack_into('<H',data,18,machine)
    return bytes(data)


def sdk(path, machine=183, folder='experimental/linux/arm64', duplicates=False):
    with zipfile.ZipFile(path,'w') as archive:
        archive.writestr('CubismSdkForNative-test/Core/dll/'+folder+'/'+live2d.NAME,elf(machine))
        archive.writestr('CubismSdkForNative-test/Core/LICENSE.md','Test vendor notice')
        if duplicates:archive.writestr('other/Core/dll/'+folder+'/'+live2d.NAME,elf(machine))


def test_import_cache_and_packaging_preserve_source(tmp_path,monkeypatch):
    monkeypatch.setattr(live2d,'cache_root',lambda:tmp_path/'cache')
    archive=tmp_path/'SDK.zip';sdk(archive)
    before=archive.read_bytes()
    core=live2d.import_sdk(archive)
    assert live2d.find_core()==core
    destination=tmp_path/'output';live2d.install(core,destination)
    assert (destination/'lib/py3-linux-aarch64'/live2d.NAME).read_bytes()==elf()
    assert (destination/'LICENSE.Live2D.md').read_text()=='Test vendor notice'
    assert archive.read_bytes()==before
    core.write_bytes(elf()+b'corrupt')
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    assert live2d.find_core() is None


@pytest.mark.parametrize('machine,folder,duplicates',[(62,'experimental/linux/arm64',False),(183,'android/arm64-v8a',False),(183,'experimental/linux/arm64',True)])
def test_incompatible_sdk_is_rejected(tmp_path,monkeypatch,machine,folder,duplicates):
    monkeypatch.setattr(live2d,'cache_root',lambda:tmp_path/'cache')
    archive=tmp_path/'SDK.zip';sdk(archive,machine,folder,duplicates)
    with pytest.raises(ValueError):live2d.import_sdk(archive)


def test_required_models_and_game_engine_are_independent(tmp_path):
    (tmp_path/'game').mkdir()
    assert not live2d.required(tmp_path)
    (tmp_path/'game/model.moc3').write_bytes(b'model')
    assert live2d.required(tmp_path)


def test_gui_missing_core_opens_sdk_popup_before_worker(tmp_path,monkeypatch):
    from megcfbt import gui,live2d_setup
    app=SimpleNamespace(_busy=False,source=tmp_path,renpy_runtime=None,inspection=SimpleNamespace(engine='renpy',renpy_live2d_required=True))
    popup=Mock()
    monkeypatch.setattr(live2d,'find_core',lambda *roots:None)
    monkeypatch.setattr(live2d_setup,'Live2DSdkDialog',popup)
    gui.ConverterApp._start_convert(app)
    popup.assert_called_once_with(app)
