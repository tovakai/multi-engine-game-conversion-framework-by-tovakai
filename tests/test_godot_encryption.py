import struct
import pytest
from rpgmframe.godot import find_godot_pack, pack_requires_encryption_key, inspect_godot, pack_native_extensions


def pack(root, *, format=2, directory_flags=0, file_flags=0, name=b'res://test.gd'):
    header = struct.pack('<IIIII', 0x43504447, format, 4 if format >= 2 else 3, 1, 4)
    if format >= 2:
        header += struct.pack('<IQ', directory_flags, 0)
    if format >= 3:
        header += struct.pack('<Q', 104)
        header += b'\0' * (104 - len(header))
    else:
        header += b'\0' * 64
    header += struct.pack('<I', 1)
    header += struct.pack('<I', len(name)) + name + b'\0' * 32
    if format >= 2:
        header += struct.pack('<I', file_flags)
    (root / 'game.pck').write_bytes(header)
    return find_godot_pack(root)


def test_encrypted_directory_requires_manual_runtime(tmp_path):
    assert pack_requires_encryption_key(pack(tmp_path, directory_flags=1))
    result = inspect_godot(tmp_path)
    assert result.runtime == 'godot-encrypted' and result.compatibility.value == 'unknown'


def test_encrypted_file_requires_key(tmp_path):
    assert pack_requires_encryption_key(pack(tmp_path, file_flags=1))


@pytest.mark.parametrize('format', [3, 4])
def test_new_pack_formats_detect_encryption(tmp_path, format):
    assert pack_requires_encryption_key(pack(tmp_path, format=format, directory_flags=1))
    assert pack_requires_encryption_key(pack(tmp_path, format=format, file_flags=1))
    assert not pack_requires_encryption_key(pack(tmp_path, format=format))


def test_godot3_encrypted_script_requires_key(tmp_path):
    assert pack_requires_encryption_key(pack(tmp_path, format=1, name=b'res://autoload/test.gde\0'))


def test_unencrypted_pack_remains_buildable(tmp_path):
    assert not pack_requires_encryption_key(pack(tmp_path))
    assert inspect_godot(tmp_path).compatibility.value == 'needs_testing'


def test_packed_native_extension_disables_stock_runtime(tmp_path):
    pck = pack(tmp_path, name=b'res://addons/fmod/fmod.gdextension')
    assert pack_native_extensions(pck) == ('res://addons/fmod/fmod.gdextension',)
    result = inspect_godot(tmp_path)
    assert result.runtime == 'godot-native-extensions'
    assert result.compatibility.value == 'unknown'
    assert 'fmod.gdextension' in result.warnings[0]


def test_godotsteam_recipe_is_not_reused_for_other_modules(tmp_path, monkeypatch):
    from megcfbt.models import UnifiedInspection
    from megcfbt.router import automatic_custom_godot_runtime_available
    monkeypatch.setattr('megcfbt.router.downloadable', lambda recipe: True)
    inspection = UnifiedInspection(source_path=tmp_path, backend='rpgmframe', engine='godot',
                                    engine_label='Godot', engine_version='3.7.0', game_name='test',
                                    compatibility='unknown', confidence='high', runtime_kind='godot-custom',
                                    buildable=False, evidence=('game.exe: built-in GodotSteam module', 'game.exe: built-in module Spine'))
    assert not automatic_custom_godot_runtime_available(inspection)
