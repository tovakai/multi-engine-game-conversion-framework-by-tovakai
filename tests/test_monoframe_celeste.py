from dataclasses import replace
import pytest
from celesteframe import backend as legacy
from monoframe import backend, celeste
from monoframe.profiles import is_celeste_inspection
from megcfbt.steam_library import identity, capability
from megcfbt import asset_dedup
from test_celesteframe import source


def test_legacy_backend_import_retains_same_implementation():
    assert legacy is celeste


def test_shared_managed_backend_selects_celeste_with_original_hash_gate(tmp_path, monkeypatch):
    game = source(tmp_path, monkeypatch)
    result = backend.inspect_game(game)
    assert result.backend == 'monoframe' and is_celeste_inspection(result)
    assert result.engine == 'fna' and result.buildable
    (game / 'Celeste.exe').write_bytes(b'MZ changed')
    assert not backend.inspect_game(game).buildable
    with pytest.raises(RuntimeError, match='verified vanilla'):
        backend.build_game(game, output=tmp_path / 'output')
    assert not (tmp_path / 'output').exists()


@pytest.mark.parametrize('backend_name', ['celesteframe', 'monoframe'])
def test_old_and_new_celeste_metadata_keep_audited_identity(backend_name):
    meta = {'backend': backend_name, 'engine': 'fna', 'architecture': 'aarch64',
            'target_platform': 'linux-aarch64', 'compatibility_profile': 'celeste-steam-xna-1.4.0.0'}
    assert identity(meta) == 504230 and capability(meta)[0]
    assert (backend_name, meta['compatibility_profile']) in asset_dedup.PROFILES
    meta['steam_runtime_appid'] = 413150
    with pytest.raises(ValueError, match='conflicts'):
        identity(meta)
