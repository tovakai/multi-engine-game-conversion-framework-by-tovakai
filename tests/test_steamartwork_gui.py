"""Run with an X display (e.g. xvfb-run) to exercise the full GUI workflow."""
import os
from pathlib import Path
import time

import pytest
from PIL import Image

from steamartwork import backend
from steamartwork.gui import ArtworkApp
from test_steamartwork import vdf_entry


def test_gui_local_and_downloaded_images_apply_and_undo(tmp_path, monkeypatch):
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("GUI smoke test requires a display")
    from tkinter import filedialog
    from steamartwork import steamgriddb
    profile = tmp_path / "123"
    (profile / "config/grid").mkdir(parents=True)
    (profile / "config/shortcuts.vdf").write_bytes(vdf_entry())
    source = tmp_path / "manual.png"
    Image.new("RGBA", (600, 900), "#49d3c6").save(source)
    monkeypatch.setattr(backend, "discover_profiles", lambda: [profile])
    app = ArtworkApp(root)
    errors = []
    monkeypatch.setattr(app, "error", lambda exc: errors.append(str(exc)))
    def wait():
        deadline = time.monotonic() + 10
        while app.busy and time.monotonic() < deadline:
            root.update()
            time.sleep(0.01)
        assert not app.busy, "GUI worker timed out"
        assert not errors
    try:
        app.listbox.selection_set(0)
        app.pick_entry()
        monkeypatch.setattr(filedialog, "askopenfilename", lambda **_: str(source))
        app.browse_image("portrait")
        assert "portrait" in app.pending
        def fetch(key, game_id, directory, *, slots):
            assert key == "test-key" and game_id == "123"
            assert "portrait" not in slots
            image = directory / "hero.png"
            Image.new("RGB", (1920, 620), "#ff8452").save(image)
            return "Example game", {"hero": image}, []
        monkeypatch.setattr(steamgriddb, "fetch_artwork", fetch)
        app.api_key.set("test-key")
        app.game_id.set("123")
        app.fetch()
        wait()
        assert set(app.pending) == {"portrait", "hero"}
        assert "Example game" in app.status.get()
        assert not list((profile / "config/grid").iterdir())
        screenshot = os.environ.get("STEAM_ARTWORK_SCREENSHOT")
        if screenshot:
            from PIL import ImageGrab
            root.update()
            ImageGrab.grab().save(screenshot)
        app.apply()
        wait()
        assert app.last_backup is not None
        assert len(list((profile / "config/grid").iterdir())) == 2
        app.undo()
        wait()
        assert not list((profile / "config/grid").iterdir())
    finally:
        app.busy = False
        app.close()
