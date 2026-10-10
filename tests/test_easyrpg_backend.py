from pathlib import Path
import json
import pytest
from megcfbt.router import build_source, inspect_source, ConversionError
from rpgmframe.easyrpg_backend import find_easyrpg_root


def game(root):
    root.mkdir(parents=True)
    (root / 'RPG_RT.ldb').write_bytes(b'\x0bLcfDataBase' + b'\0' * 20)
    (root / 'RPG_RT.lmt').write_bytes(b'\x0aLcfMapTree' + b'\0' * 20)
    (root / 'RPG_RT.exe').write_bytes(b'MZ')
    (root / 'Map0001.lmu').write_bytes(b'map fixture')
    return root


def test_easyrpg_nested_source_build_is_relocatable(tmp_path, monkeypatch):
    source = game(tmp_path / 'source/game')
    monkeypatch.setattr('megcfbt.router.complete_frame_artwork', lambda *a, **k: {})
    inspection = inspect_source(source.parent)
    assert inspection.engine == 'rpg2k' and inspection.buildable
    result = build_source(source.parent, output=tmp_path / 'output', archive=False)
    assert (result.output_path / 'game/Map0001.lmu').read_bytes() == b'map fixture'
    assert (result.output_path / 'game/RPG_RT.exe').read_bytes() == b'MZ'
    assert (source / 'RPG_RT.exe').exists()
    launcher = result.launcher_path.read_text()
    assert '--arch=aarch64' in launcher and '--filesystem="$ROOT/game"' in launcher
    assert json.loads((result.output_path / '.megcfbt/package.json').read_text())['engine'] == 'rpg2k'


def test_easyrpg_requires_real_lcf_signatures(tmp_path):
    root = game(tmp_path / 'source')
    (root / 'RPG_RT.ldb').write_bytes(b'not a database')
    assert find_easyrpg_root(root) is None


def test_easyrpg_ambiguous_roots_are_not_guessed(tmp_path):
    game(tmp_path / 'a')
    game(tmp_path / 'b')
    assert find_easyrpg_root(tmp_path) is None


def test_easyrpg_refuses_source_overlap(tmp_path):
    source = game(tmp_path / 'source')
    with pytest.raises(ConversionError, match='separate'):
        build_source(source, output=source / 'output', archive=False)
