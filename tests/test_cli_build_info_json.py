import json
import pytest
from megcfbt import cli


@pytest.mark.parametrize('columns', ['40', '80', '120'])
def test_release_build_info_is_json_at_every_terminal_width(monkeypatch, capsys, columns):
    info = {
        'schema': 'megcfbt.build/v1', 'release_version': '0.1.0.2',
        'version': '0.1.0.2', 'build_kind': 'release',
        'commit': '5e370c68f89bcd79dab63e6f8683b41c13fd1549',
        'architecture': 'aarch64', 'platform': 'linux-aarch64',
        'tracked_changes': False, 'development_id': None,
        'metadata_status': 'complete',
    }
    monkeypatch.setenv('COLUMNS', columns)
    monkeypatch.setattr(cli, 'get_build_info', lambda: info)
    with pytest.raises(SystemExit) as exit:
        cli.main(['--build-info'])
    assert exit.value.code == 0
    captured = capsys.readouterr()
    assert captured.err == ''
    assert json.loads(captured.out) == info
    assert len(captured.out.splitlines()) == 1
