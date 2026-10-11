import struct
from pathlib import Path
from rpgmframe.godot import find_godot_pack, inspect_godot
from megcfbt.router import inspect_source


def pack(root, name, version=(4,6,0)):
    root.mkdir(parents=True,exist_ok=True)
    path = root / (name + '.pck')
    path.write_bytes(struct.pack('<5I', 0x43504447, 2, *version))
    (root / (name + '.exe')).write_bytes(b'MZ')
    return path


def test_folder_identity_disambiguates_main_game_from_utility(tmp_path):
    root=tmp_path/'Cassette Beasts'
    selected=pack(root,'CassetteBeasts',(3,5,1))
    pack(root,'WorkshopUtility',(3,5,1))
    assert find_godot_pack(root).path == selected
    assert inspect_source(root).engine_version == '3.5.1'


def test_unrelated_folder_does_not_guess_between_two_games(tmp_path):
    root=tmp_path/'collection'
    pack(root,'GameA')
    pack(root,'GameB')
    assert find_godot_pack(root) is None


def test_stable_godotsteam_export_requires_matching_module_runtime(tmp_path):
    pack(tmp_path,'Game')
    (tmp_path/'Game.exe').write_bytes(b'MZ\0get_godotsteam_version\0')
    result=inspect_godot(tmp_path)
    assert result.engine_version == '4.6.0'
    assert result.runtime == 'godot-custom'
    assert result.compatibility.value == 'unknown'
    unified=inspect_source(tmp_path)
    assert not unified.buildable
    assert any('GodotSteam' in warning for warning in unified.warnings)


def test_plain_stable_export_remains_stock_runtime_candidate(tmp_path):
    pack(tmp_path,'Game')
    result=inspect_source(tmp_path)
    assert result.buildable
    assert result.runtime_kind == 'godot'
