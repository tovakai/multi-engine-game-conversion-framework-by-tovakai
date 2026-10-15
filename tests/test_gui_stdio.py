"""Regression: a dependency's font fallback warning must not crash pythonw."""
import io
import sys

from megcfbt.gui_stdio import ensure_gui_streams


def test_windowed_dependency_warning_is_logged(tmp_path, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(sys, 'stdout', None)
        patch.setattr(sys, 'stderr', None)
        log = ensure_gui_streams(tmp_path)
        try:
            # Same operation CustomTkinter performs when GDI refuses its font.
            sys.stderr.write('Font could not be loaded; using circle_shapes instead.\n')
            print('GUI continues initializing')
            sys.stderr.flush()
            assert 'GUI continues initializing' in log.read_text()
            assert 'using circle_shapes' in log.read_text()
            assert ensure_gui_streams(tmp_path) is None
        finally:
            sys.stderr.close()


def test_existing_console_and_capture_streams_preserved(tmp_path, monkeypatch):
    output, errors = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, 'stdout', output)
    monkeypatch.setattr(sys, 'stderr', errors)
    assert ensure_gui_streams(tmp_path) is None
    assert sys.stdout is output and sys.stderr is errors
    assert not list(tmp_path.iterdir())


def test_unwritable_log_location_still_allows_dependency_warning(tmp_path, monkeypatch):
    blocker = tmp_path / 'file'
    blocker.write_text('not a directory')
    with monkeypatch.context() as patch:
        patch.setattr(sys, 'stderr', None)
        stream = sys.stdout
        assert ensure_gui_streams(blocker / 'logs') is None
        try:
            sys.stderr.write('recoverable warning\n')
            sys.stderr.flush()
            assert sys.stdout is stream
        finally:
            sys.stderr.close()
