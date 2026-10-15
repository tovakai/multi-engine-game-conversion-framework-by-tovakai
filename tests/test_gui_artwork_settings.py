"""Session-only artwork settings must reach the worker without leaking keys."""
import json
from types import SimpleNamespace

import pytest

from megcfbt import gui, steamgriddb
from megcfbt.artwork import complete_frame_artwork
from test_gui_renpy_fallback import app_for_inspection, inspection, synchronous_threads
from test_steamgriddb import setup_build, PNG, JPEG


@pytest.mark.parametrize('value', ['', '0', '-1', 'https://steamgriddb.com/game/42', 'abc', '12345678901'])
def test_manual_id_validation(tmp_path, value):
    app = app_for_inspection(tmp_path)
    app.steamgriddb_key_var = SimpleNamespace(get=lambda: 'session-secret')
    app.steamgriddb_id_var = SimpleNamespace(get=lambda: value)
    if value:
        with pytest.raises(ValueError, match='positive numeric'):
            app._artwork_options()
    else:
        assert app._artwork_options() == ('session-secret', None)


def test_id_requires_key_and_header_newlines_are_rejected(tmp_path):
    app = app_for_inspection(tmp_path)
    app.steamgriddb_id_var = SimpleNamespace(get=lambda: '42')
    with pytest.raises(ValueError, match='key is required'):
        app._artwork_options()
    app.steamgriddb_key_var = SimpleNamespace(get=lambda: 'bad\nsecret')
    with pytest.raises(ValueError, match='single line') as error:
        app._artwork_options()
    assert 'secret' not in str(error.value)


def test_gui_passes_key_and_id_to_conversion_without_environment_changes(tmp_path, monkeypatch):
    app = app_for_inspection(tmp_path)
    app.inspection = inspection(app.source, version='8.5.3', generation=8)
    app.steamgriddb_key_var = SimpleNamespace(get=lambda: ' session-secret ')
    app.steamgriddb_id_var = SimpleNamespace(get=lambda: ' 42 ')
    monkeypatch.setenv('STEAMGRIDDB_API_KEY', 'environment-secret')
    seen = []
    monkeypatch.setattr(gui, 'build_source', lambda source, **kw: seen.append(kw))
    synchronous_threads(monkeypatch)
    app._start_convert()
    assert seen[0]['steamgriddb_api_key'] == 'session-secret'
    assert seen[0]['steamgriddb_game_id'] == 42
    import os
    assert os.environ['STEAMGRIDDB_API_KEY'] == 'environment-secret'
    assert 'secret' not in app.log_box.contents


def test_explicit_key_and_id_reach_api_but_not_metadata(tmp_path, monkeypatch):
    root = setup_build(tmp_path)
    monkeypatch.setenv('STEAMGRIDDB_API_KEY', 'wrong-key')
    requests = []
    def api(path, key):
        requests.append((path, key))
        if path == 'games/id/42':
            return {'data': {'id': 42, 'name': 'Chosen game'}}
        return {'data': []}
    monkeypatch.setattr(steamgriddb, '_api_json', api)
    complete_frame_artwork(root, game_name='Different title', steamgriddb_game_id=42,
                           steamgriddb_api_key='session-secret')
    assert requests[0] == ('games/id/42', 'session-secret')
    assert all(key == 'session-secret' for _, key in requests)
    assert 'session-secret' not in (root / '.megcfbt/package.json').read_text()


def test_errors_redact_key_and_explicit_empty_key_disables_environment(tmp_path, monkeypatch):
    root = setup_build(tmp_path)
    monkeypatch.setenv('STEAMGRIDDB_API_KEY', 'environment-secret')
    calls = []
    def fail(path, key):
        calls.append(key)
        raise OSError('Could not use ' + key)
    monkeypatch.setattr(steamgriddb, '_api_json', fail)
    logs = []
    steamgriddb.fetch_steamgriddb_artwork(root, game_name='Test', api_key='', progress=logs.append)
    assert not calls
    steamgriddb.fetch_steamgriddb_artwork(root, game_name='Test', api_key='session-secret', progress=logs.append)
    assert calls == ['session-secret']
    assert 'session-secret' not in '\n'.join(logs)
    assert '[redacted]' in '\n'.join(logs)
