import json
from pathlib import Path
from unittest import mock
import pytest
from megcfbt.sts2_backend import module


def test_configuration_requires_consent_before_any_probe(tmp_path):
    entry=module('steam_entry')
    with mock.patch.object(entry,'inspect') as probe:
        with pytest.raises(RuntimeError,match='consent'):
            entry.configure(tmp_path)
        probe.assert_not_called()


def test_backup_and_restore_preserve_intervening_user_edits(tmp_path):
    entry=module('steam_entry')
    verifier=module('verify_output')
    output=tmp_path/'native-output';output.mkdir()
    state={'launch_options':'original user setting'}
    def set_options(expected,new):
        assert state['launch_options']==expected
        state['launch_options']=new
    with mock.patch.object(verifier,'verify',return_value={'errors':[]}), mock.patch.object(entry,'inspect',side_effect=lambda:state.copy()), mock.patch.object(entry,'set_options',side_effect=set_options):
        result=entry.configure(output,consent=True)
        backup=json.loads((tmp_path/'steam-integration/launch-backup.json').read_bytes())
        assert backup['previous']=='original user setting'
        assert state['launch_options']=='"'+str(output/'play-steam.sh')+'" %command%'
        entry.configure(output,consent=True) # idempotent; retains original backup
        state['launch_options']='later user edit'
        with pytest.raises(RuntimeError,match='edited'):
            entry.restore(output,consent=True)
        assert state['launch_options']=='later user edit'
        state['launch_options']=backup['installed']
        assert entry.restore(output,consent=True)['restored']
        assert state['launch_options']==backup['previous']


def test_invalid_output_never_changes_steam(tmp_path):
    entry=module('steam_entry');verifier=module('verify_output')
    with mock.patch.object(verifier,'verify',return_value={'errors':['bad hash']}), mock.patch.object(entry,'set_options') as setter:
        with pytest.raises(RuntimeError,match='verification'):
            entry.configure(tmp_path,consent=True)
        setter.assert_not_called()


def test_connect_only_configures_completed_game_without_compilation(tmp_path):
    installer = module('frame_install')
    entry = module('steam_entry')
    with mock.patch.object(installer, 'require_installed', return_value={}), \
         mock.patch.object(installer, 'install', side_effect=AssertionError('Compilation attempted')), \
         mock.patch.object(entry, 'configure', return_value={'configured':True}) as configure:
        assert installer.main([str(tmp_path), '--connect-steam']) == 0
    configure.assert_called_once_with(tmp_path/'game', consent=True)


@pytest.mark.parametrize('answer,configured', [('yes', True), ('', True), ('n', False)])
def test_installer_offers_steam_configuration_and_respects_decline(tmp_path, answer, configured):
    installer = module('frame_install')
    with mock.patch.object(installer, 'install', return_value={'launch_command':'fixture command'}), \
         mock.patch.object(installer.sys.stdin, 'isatty', return_value=True), \
         mock.patch('builtins.input', return_value=answer), \
         mock.patch.object(installer, 'connect_steam') as connect:
        assert installer.main([str(tmp_path)]) == 0
    assert connect.call_count == int(configured)


def test_unavailable_steam_api_does_not_trigger_recompilation(tmp_path, capsys):
    installer = module('frame_install')
    with mock.patch.object(installer, 'install', return_value={'launch_command':'fixture command'}) as build, \
         mock.patch.object(installer.sys.stdin, 'isatty', return_value=True), \
         mock.patch('builtins.input', return_value='y'), \
         mock.patch.object(installer, 'connect_steam', side_effect=RuntimeError('Steam library UI debug endpoint is unavailable')):
        assert installer.main([str(tmp_path)]) == 2
    assert build.call_count == 1
    assert '--connect-steam; no recompilation' in capsys.readouterr().err


def test_restore_only_uses_backup_without_compiling(tmp_path):
    installer = module('frame_install')
    entry = module('steam_entry')
    with mock.patch.object(installer, 'require_installed', return_value={}), \
         mock.patch.object(installer, 'install', side_effect=AssertionError('Compilation attempted')), \
         mock.patch.object(entry, 'restore', return_value={'restored':True}) as restore:
        assert installer.main([str(tmp_path), '--restore-steam']) == 0
    restore.assert_called_once_with(tmp_path/'game', consent=True)
