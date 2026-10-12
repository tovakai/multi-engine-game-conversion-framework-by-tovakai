from pathlib import Path
import struct

import pytest

from megcfbt.router import ConversionError, build_source, inspect_source
from megcfbt.unity import pe_architecture


def pe(machine=0x8664):
    header = bytearray(64)
    header[:2] = b'MZ'
    struct.pack_into('<I', header, 60, 64)
    return bytes(header) + b'PE\0\0' + struct.pack('<H', machine)


def game(tmp_path):
    (tmp_path / 'UnityPlayer.dll').write_bytes(pe())
    (tmp_path / 'hollow_knight.exe').write_bytes(pe())
    data = tmp_path / 'hollow_knight_Data'
    (data / 'Managed').mkdir(parents=True)
    (data / 'globalgamemanagers').write_bytes(b'\0' * 20 + b'6000.0.61f1\0')
    (data / 'Managed/Assembly-CSharp.dll').write_bytes(b'managed fixture')
    return data


def test_hollow_knight_inventory_and_build_gate(tmp_path):
    data = game(tmp_path)
    plugins = data / 'Plugins/x86_64'
    plugins.mkdir(parents=True)
    (plugins / 'InControlNative.dll').write_bytes(pe())
    result = inspect_source(tmp_path)
    assert result.engine_version == '6000.0.61f1'
    assert result.game_name == 'Hollow Knight'
    assert result.buildable is False
    assert any('InControlNative.dll: x64' in x for x in result.evidence)
    assert any('ARM64 replacement' in x for x in result.warnings)
    with pytest.raises(ConversionError):
        build_source(tmp_path, output=tmp_path / 'out', archive=False)
    assert not (tmp_path / 'out').exists()


def test_il2cpp_overrides_managed_assembly_presence(tmp_path):
    game(tmp_path)
    (tmp_path / 'GameAssembly.dll').write_bytes(pe())
    result = inspect_source(tmp_path)
    assert result.engine_label == 'Unity IL2CPP'
    assert result.runtime_kind is None
    assert any('ARM64 game build' in x for x in result.warnings)


def test_ambiguous_version_is_not_guessed(tmp_path):
    data = game(tmp_path)
    (data / 'globalgamemanagers').write_bytes(b'6000.0.61f1\0' + b'6000.0.50f1\0')
    assert inspect_source(tmp_path).engine_version is None


def test_multiple_exports_are_ambiguous(tmp_path):
    game(tmp_path)
    (tmp_path / 'another_Data').mkdir()
    assert inspect_source(tmp_path).compatibility == 'ambiguous'


@pytest.mark.parametrize('machine,label', [(0x8664, 'x64'), (0xaa64, 'ARM64'),
                                         (0xa641, 'ARM64EC'), (0xa64e, 'ARM64X')])
def test_pe_machine_distinctions(tmp_path, machine, label):
    path = tmp_path / 'test.dll'
    path.write_bytes(pe(machine))
    assert pe_architecture(path) == label


def test_malformed_pe_offset(tmp_path):
    path = tmp_path / 'bad.dll'
    header = bytearray(pe())
    struct.pack_into('<I', header, 60, 0xffffffff)
    path.write_bytes(header)
    assert pe_architecture(path) == 'unknown'


def test_wrapped_export_is_inspected(tmp_path):
    root = tmp_path / 'wrapper/game'
    root.mkdir(parents=True)
    game(root)
    result = inspect_source(tmp_path)
    assert result.source_path == tmp_path
    assert result.engine_version == '6000.0.61f1'
    assert result.game_name == 'Hollow Knight'
