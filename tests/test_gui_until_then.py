"""Until Then uses the shared FMOD flow, not a manual runtime selection."""
from types import SimpleNamespace

from megcfbt import gui
from megcfbt.models import UnifiedInspection
from rpgmframe import until_then
from test_gui_renpy_fallback import app_for_inspection


def test_inspection_enables_conversion_and_selects_correct_sdk(tmp_path, monkeypatch):
    app = app_for_inspection(tmp_path)
    sdk = tmp_path / until_then.FMOD_FILENAME
    monkeypatch.setattr(until_then, "find_fmod_sdk", lambda: sdk)
    result = UnifiedInspection(app.source, "rpgmframe", "godot", "Godot", "4.1.4",
        "Until Then", "needs_testing", "high", until_then.RUNTIME_KIND, True)
    app._show_inspection(result)
    assert app.until_then_sdk == sdk
    assert app.convert_btn.values["state"] == "normal"
    assert app.runtime_button.values["text"] == "FMOD SDK SELECTED"
    assert "2.02.35" in app.notes_box.contents
    assert "non-Steam" in app.notes_box.contents


def test_missing_sdk_button_opens_until_then_shared_dialog(tmp_path, monkeypatch):
    app = app_for_inspection(tmp_path)
    app.inspection = SimpleNamespace(runtime_kind=until_then.RUNTIME_KIND, backend="rpgmframe")
    from megcfbt import fmod_sdk_setup
    seen = []
    monkeypatch.setattr(fmod_sdk_setup, "FmodSdkDialog", lambda app, backend: seen.append(backend))
    app._pick_runtime()
    assert seen == ["until-then"]
