"""Headless GUI checks for legacy Ren'Py runtime UX and explicit consent."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from megcfbt import gui
from megcfbt.models import UnifiedInspection


class Widget:
    def __init__(self):
        self.values = {}
        self.contents = ""

    def configure(self, **kwargs):
        self.values.update(kwargs)

    def delete(self, *args):
        self.contents = ""

    def insert(self, *args):
        self.contents += args[-1]

    def stop(self):
        pass


def inspection(source: Path, version="7.4.11", generation=7) -> UnifiedInspection:
    return UnifiedInspection(
        source_path=source,
        backend="renframe",
        engine="renpy",
        engine_label="Ren'Py",
        engine_version=version,
        game_name="Everlasting Summer",
        compatibility="NEEDS_TESTING",
        confidence="high",
        runtime_kind=f"official Ren'Py {version} sdkarm platform (automatic)",
        buildable=True,
        renpy_generation=generation,
    )


def app_for_inspection(tmp_path: Path):
    app = gui.ConverterApp.__new__(gui.ConverterApp)
    app._busy = False
    app.source = tmp_path / "source-game"
    app.source.mkdir()
    app.inspection = None
    app.renpy_runtime = None
    app.backend_runtime = None
    app.steam_cover = None
    app.output_dir = tmp_path
    app.last_result = None
    app.force_var = SimpleNamespace(get=lambda: False)
    app.archive_var = SimpleNamespace(get=lambda: False)
    app._dispatch = lambda cb: cb()
    app._set_status = lambda *args: None
    app._set_busy = lambda busy: None
    app._set_progress = lambda *args: None
    app._progress_log = lambda *args: None
    app._download_progress = lambda *args: None
    app._log = lambda *args: None
    app._done = lambda result: None
    app._fail = lambda message: pytest.fail(message)

    for name in (
        "activity_progress", "activity_label", "game_label",
        "engine_label", "backend_label", "compat_label", "runtime_button",
        "convert_btn", "drop_label", "notes_box", "log_box",
    ):
        setattr(app, name, Widget())
    return app


def synchronous_threads(monkeypatch):
    class ImmediateThread:
        def __init__(self, *, target, daemon):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(gui.threading, "Thread", ImmediateThread)


def test_legacy_gui_displays_experimental_option_and_warning(tmp_path):
    app = app_for_inspection(tmp_path)
    app._show_inspection(inspection(app.source))
    assert "7.5.0 EXPERIMENTAL // OVERRIDE" in app.runtime_button.values["text"]
    assert "EXPERIMENTAL" in app.runtime_button.values["text"]
    assert app.convert_btn.values["state"] == "normal"
    assert "EXPERIMENTAL ARM64" in app.drop_label.values["text"]
    assert "predates official ARM64" in app.notes_box.contents
    assert "not yet verified" in app.notes_box.contents


def test_legacy_gui_requires_manual_runtime_if_no_verified_fallback(tmp_path):
    app = app_for_inspection(tmp_path)
    app._show_inspection(inspection(app.source, version="7.3.4"))
    assert app.runtime_button.values["text"] == "RUNTIME // MANUAL ARM64 REQUIRED…"
    assert "MANUAL ARM64 REQUIRED" in app.drop_label.values["text"]


def test_current_renpy_still_displays_automatic_runtime(tmp_path):
    app = app_for_inspection(tmp_path)
    app._show_inspection(inspection(app.source, version="8.5.3", generation=8))
    assert "AUTO REN'PY 8.5.3" in app.runtime_button.values["text"]


@pytest.mark.parametrize("choice,expected_runtime,expected_fallback", [
    (True, None, True),
    (False, "manual", False),
])
def test_gui_consent_paths_use_only_selected_runtime(
    tmp_path, monkeypatch, choice, expected_runtime, expected_fallback,
):
    app = app_for_inspection(tmp_path)
    app.inspection = inspection(app.source)
    decisions = []
    monkeypatch.setattr(gui, "messagebox", SimpleNamespace(
        askyesnocancel=lambda *args, **kwargs: decisions.append((args, kwargs)) or choice,
    ))
    manual = tmp_path / "manual-runtime"
    manual.mkdir()
    app._pick_renpy_runtime = lambda: setattr(app, "renpy_runtime", manual)
    seen = []

    def fake_build_source(source, **kwargs):
        seen.append(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(gui, "build_source", fake_build_source)
    synchronous_threads(monkeypatch)
    app._start_convert()
    assert len(decisions) == 1
    assert "checksum-verified" in decisions[0][0][1]
    assert len(seen) == 1
    assert seen[0]["renpy_legacy_arm64_fallback"] is expected_fallback
    if expected_runtime:
        assert seen[0]["renpy_runtime"] == manual
    else:
        assert seen[0]["renpy_runtime"] is None


def test_gui_cancel_does_not_build_or_pick_runtime(tmp_path, monkeypatch):
    app = app_for_inspection(tmp_path)
    app.inspection = inspection(app.source)
    monkeypatch.setattr(gui, "messagebox", SimpleNamespace(
        askyesnocancel=lambda *a, **kw: None,
    ))
    app._pick_renpy_runtime = lambda: pytest.fail("should not prompt for folder")
    monkeypatch.setattr(gui, "build_source", lambda *a, **kw: pytest.fail("build started"))
    app._start_convert()


def test_gui_renpy8_never_prompts_for_legacy_fallback(tmp_path, monkeypatch):
    app = app_for_inspection(tmp_path)
    app.inspection = inspection(app.source, version="8.5.3", generation=8)
    monkeypatch.setattr(gui, "messagebox", SimpleNamespace(
        askyesnocancel=lambda *a, **kw: pytest.fail("unexpected legacy prompt"),
    ))
    seen = []
    monkeypatch.setattr(gui, "build_source", lambda source, **kw: seen.append(kw) or None)
    synchronous_threads(monkeypatch)
    app._start_convert()
    assert seen[0]["renpy_legacy_arm64_fallback"] is False
    assert seen[0]["renpy_runtime"] is None


def test_gui_unsupported_7_3_requires_manual_runtime(tmp_path, monkeypatch):
    app = app_for_inspection(tmp_path)
    app.inspection = inspection(app.source, version="7.3.4")
    events = []
    monkeypatch.setattr(gui, "messagebox", SimpleNamespace(
        showinfo=lambda *a, **kw: events.append("needs manual"),
    ))
    app._pick_renpy_runtime = lambda: events.append("picker cancelled")
    monkeypatch.setattr(gui, "build_source", lambda *a, **kw: pytest.fail("no runtime"))
    app._start_convert()
    assert events == ["needs manual", "picker cancelled"]
