import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from megcfbt import fmod_sdk, fmod_sdk_setup, gui, sts2
from megcfbt.models import UnifiedInspection
from celesteframe import runtime

@pytest.mark.parametrize('backend', ['sts2', 'celesteframe'])
def test_runtime_button_uses_shared_guided_dialog(monkeypatch, backend):
    app = SimpleNamespace(inspection=SimpleNamespace(backend=backend))
    dialog = Mock()
    monkeypatch.setattr(fmod_sdk_setup, 'FmodSdkDialog', dialog)
    gui.ConverterApp._pick_runtime(app)
    dialog.assert_called_once_with(app, backend)

def test_missing_celeste_sdk_opens_guide_before_conversion(tmp_path, monkeypatch):
    app = SimpleNamespace(_busy=False, source=tmp_path, backend_runtime=None, celeste_sdk=None,
        inspection=UnifiedInspection(tmp_path, 'celesteframe', 'fna', 'Celeste', '1.4.0.0',
            'Celeste', 'needs_testing', 'high', 'celeste', True), _pick_runtime=Mock())
    monkeypatch.setattr(runtime, 'find_fmod_sdk', lambda: None)
    gui.ConverterApp._start_convert(app)
    app._pick_runtime.assert_called_once()

@pytest.mark.parametrize('backend,attribute', [('sts2','sts2_sdk'),('celesteframe','celeste_sdk')])
def test_dialog_validates_before_remembering_or_enabling(tmp_path, monkeypatch, backend, attribute):
    archive = tmp_path/'SDK.tar.gz'
    archive.write_bytes(b'fixture')
    record = tmp_path/'config/megcfbt/fmod/sdk.json'
    monkeypatch.setattr(fmod_sdk, 'settings_path', lambda: record)
    app = SimpleNamespace(runtime_button=Mock(), convert_btn=Mock(), _conversion_allowed=lambda: True)
    setattr(app, attribute, None)
    popup = object.__new__(fmod_sdk_setup.FmodSdkDialog)
    popup.app, popup.window = app, Mock()
    validate = Mock(side_effect=ValueError('Wrong SDK'))
    save = Mock()
    popup.requirement = dict(attribute=attribute, validate=validate, save=save)
    errors = Mock()
    monkeypatch.setattr(gui, 'messagebox', SimpleNamespace(showerror=errors))
    popup.use(archive)
    assert getattr(app, attribute) is None
    assert not record.exists()
    save.assert_not_called()
    app.convert_btn.configure.assert_not_called()
    popup.window.destroy.assert_not_called()
    errors.assert_called_once()
    validate.side_effect = None
    validate.return_value = archive
    popup.use(archive)
    assert getattr(app, attribute) == archive
    assert fmod_sdk.remembered_sdk() == archive
    save.assert_called_once_with(archive)
    popup.window.destroy.assert_called_once()

def test_shared_selection_is_revalidated_by_each_backend(tmp_path, monkeypatch):
    record = tmp_path/'config/megcfbt/fmod/sdk.json'
    monkeypatch.setattr(fmod_sdk, 'settings_path', lambda: record)
    archive = tmp_path/'custom.tar.gz'
    archive.write_bytes(b'fixture')
    fmod_sdk.remember_sdk(archive)
    monkeypatch.delenv('MEGCFBT_CELESTE_FMOD_SDK', raising=False)
    monkeypatch.delenv('MEGCFBT_STS2_FMOD_SDK', raising=False)
    celeste_gate, sts2_gate = Mock(return_value=archive), Mock(return_value=archive)
    monkeypatch.setattr(runtime, 'validate_fmod_sdk', celeste_gate)
    monkeypatch.setattr(sts2, 'validate_sdk', sts2_gate)
    assert runtime.find_fmod_sdk() == archive
    assert sts2.find_sdk() == archive
    celeste_gate.assert_called_once_with(archive)
    sts2_gate.assert_called_once_with(archive)

def test_legacy_sts2_selection_remains_discoverable(tmp_path, monkeypatch):
    record = tmp_path/'megcfbt/fmod/sdk.json'
    legacy = tmp_path/'megcfbt/sts2/sdk.json'
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({'sdk_file': str(tmp_path/'old-sdk.tar.gz')}))
    monkeypatch.setattr(fmod_sdk, 'settings_path', lambda: record)
    assert fmod_sdk.remembered_sdk() == tmp_path/'old-sdk.tar.gz'
