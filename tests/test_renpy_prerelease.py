from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
import pytest
from megcfbt.router import inspect_source
from renframe.prerelease import prerelease_853_candidate
from renframe.builder import build_game, BuildError
from test_gui_renpy_fallback import app_for_inspection, synchronous_threads, inspection
from megcfbt import gui


def nightly(root, version='8.5.0.25082602', is_nightly=True):
    (root / 'game').mkdir(parents=True)
    (root / 'renpy').mkdir()
    (root / 'renpy/__init__.py').write_text('# engine')
    (root / 'renpy/vc_version.py').write_text(f"nightly = {is_nightly}\nversion = '{version}'\n")
    (root / 'lib/python3.12').mkdir(parents=True)
    (root / 'lib/py3-windows-x86_64').mkdir()
    return root


def test_prerelease_grafting_requires_explicit_migration(tmp_path):
    source = nightly(tmp_path / 'source')
    result = inspect_source(source)
    assert result.renpy_prerelease_853_candidate
    with pytest.raises(BuildError, match='nightly'):
        build_game(source, output=tmp_path / 'output')
    assert not (tmp_path / 'output').exists()


def test_stable_release_does_not_enable_prerelease_migration(tmp_path):
    source = nightly(tmp_path / 'source', version='8.5.3.26051504', is_nightly=False)
    assert not prerelease_853_candidate(source)
    with pytest.raises(BuildError, match='identified'):
        build_game(source, output=tmp_path / 'output', prerelease_853_migration=True)


@pytest.mark.parametrize('choice', [True, False, None])
def test_prerelease_gui_choice_is_forwarded(tmp_path, monkeypatch, choice):
    app = app_for_inspection(tmp_path)
    app.inspection = replace(inspection(app.source, version='8.5.0', generation=8), renpy_prerelease_853_candidate=True)
    seen = []
    monkeypatch.setattr(gui, 'messagebox', SimpleNamespace(askyesnocancel=lambda *a, **k: choice))
    monkeypatch.setattr(gui, 'build_source', lambda *a, **k: seen.append(k))
    app._pick_renpy_runtime = lambda: setattr(app, 'renpy_runtime', tmp_path / 'manual')
    synchronous_threads(monkeypatch)
    app._start_convert()
    if choice is None:
        assert not seen
    else:
        assert seen[0]['renpy_prerelease_853_migration'] is choice
        assert bool(seen[0]['renpy_runtime']) is (not choice)
