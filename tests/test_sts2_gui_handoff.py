from pathlib import Path
from unittest import mock

from megcfbt import gui, sts2
from megcfbt.models import UnifiedBuildResult, UnifiedInspection


def app_without_window():
    app = gui.ConverterApp.__new__(gui.ConverterApp)
    for name in ('activity_progress', 'activity_label', 'game_label', 'engine_label',
                 'backend_label', 'compat_label', 'runtime_button', 'convert_btn', 'drop_label', 'notes_box'):
        setattr(app, name, mock.Mock())
    for name in ('_log', '_set_status', '_pick_runtime', '_set_progress', '_set_busy'):
        setattr(app, name, mock.Mock())
    app.sts2_sdk = None
    return app


def test_supported_sts2_detection_opens_download_guidance_when_sdk_missing():
    app = app_without_window()
    inspection = UnifiedInspection(source_path=Path('game'), backend='sts2', engine='godot',
        engine_label='STS2', engine_version='4.5.1', game_name='Slay the Spire 2',
        compatibility='needs_testing', confidence='high', runtime_kind='sts2-native-source',
        buildable=False, evidence=('STS2 v0.107.1 / 59260271',))
    with mock.patch.object(sts2, 'find_sdk', return_value=None):
        app._show_inspection(inspection)
    app._pick_runtime.assert_called_once()
    assert app._conversion_allowed()  # Convert opens download guidance before any work.


def test_prepared_result_explains_manual_transfer_and_installation(tmp_path):
    app = app_without_window()
    result = UnifiedBuildResult(source_path=tmp_path/'original', output_path=tmp_path/'transfer',
        launcher_path=tmp_path/'transfer/install.sh', archive_path=tmp_path/'transfer.zip',
        backend='sts2', engine='godot', engine_version='4.5.1', game_name='Slay the Spire 2',
        requires_frame_install=True)
    with mock.patch.object(gui, 'messagebox', mock.Mock()) as dialogs:
        app._done(result)
    message = dialogs.showinfo.call_args.args[1]
    assert str(result.archive_path) in message
    assert 'sh ./install.sh' in message
    assert 'Additional compilation is required on the Frame' in message
    dialogs.askyesno.assert_not_called()


def test_convert_rechecks_missing_deleted_and_corrupt_sdk():
    for sdk in (None, Path('deleted.tar.gz'), Path('corrupt.tar.gz')):
        app = app_without_window()
        app._busy = False
        app.source = Path('game')
        app.inspection = mock.Mock(backend='sts2', compatibility='needs_testing')
        app.sts2_sdk = sdk
        with mock.patch.object(sts2, 'find_sdk', return_value=None), mock.patch.object(sts2, 'validate_sdk', side_effect=ValueError('invalid')):
            app._start_convert()
        app._pick_runtime.assert_called_once()
        app._set_busy.assert_not_called()
        assert app.sts2_sdk is None


def test_sdk_digest_validation(tmp_path):
    import hashlib
    import pytest
    from megcfbt.sts2_backend import module
    archive = tmp_path / 'sdk.tar.gz'
    archive.write_bytes(b'test SDK')
    pin = dict(size_bytes=8, sha256=hashlib.sha256(b'test SDK').hexdigest())
    with mock.patch.object(module('sdk_archive'), 'PIN', pin):
        assert sts2.validate_sdk(archive) == archive
        archive.write_bytes(b'bad SDK!')
        with pytest.raises(ValueError):
            sts2.validate_sdk(archive)
        archive.unlink()
        with pytest.raises(OSError):
            sts2.validate_sdk(archive)
