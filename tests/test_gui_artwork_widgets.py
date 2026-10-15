"""Exercise the real optional settings dialog when a display is available."""
import pytest
from megcfbt import gui


def test_artwork_dialog_masks_key_and_reuses_session_fields(monkeypatch):
    tk = pytest.importorskip('tkinter')
    try:
        probe = tk.Tk()
    except tk.TclError:
        pytest.skip('GUI widgets need a display')
    probe.destroy()
    monkeypatch.setenv('STEAMGRIDDB_API_KEY', 'environment-secret')
    app = gui.ConverterApp()
    try:
        app.root.withdraw()
        assert app.steamgriddb_key_var.get() == 'environment-secret'
        app._show_artwork_settings()
        app.artwork_dialog.withdraw()
        app.root.update_idletasks()
        entries = [w for w in app.artwork_dialog.winfo_children() if isinstance(w, gui.ctk.CTkEntry)]
        assert len(entries) == 2 and entries[0].cget('show') == '*'
        app.steamgriddb_key_var.set('session-secret')
        app.steamgriddb_id_var.set('42')
        assert entries[0].get() == 'session-secret' and entries[1].get() == '42'
        assert app._artwork_options() == ('session-secret', 42)
        previous = app.artwork_dialog
        app._show_artwork_settings()
        assert app.artwork_dialog is previous
    finally:
        if app.artwork_dialog is not None:
            app.artwork_dialog.destroy()
        app.root.destroy()
