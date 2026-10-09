import json
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
