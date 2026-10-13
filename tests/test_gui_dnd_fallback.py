"""A failed optional native drop extension must not prevent opening the GUI."""
from types import SimpleNamespace

import pytest

from megcfbt import gui


def setup_roots(monkeypatch, require):
    instances = []
    class Root:
        def __init__(self, *args, **kwargs):
            self.destroyed = False
            instances.append(self)
        def destroy(self): self.destroyed = True
        def title(self, *args): pass
        def geometry(self, *args): pass
        def minsize(self, *args): pass
        def configure(self, **kwargs): pass
    monkeypatch.setattr(gui, 'ctk', SimpleNamespace(CTk=Root, set_appearance_mode=lambda value: None))
    monkeypatch.setattr(gui, 'tk', SimpleNamespace(TclError=ValueError))
    monkeypatch.setattr(gui, 'TkinterDnD', SimpleNamespace(DnDWrapper=type('Wrapper', (), {}), _require=require))
    monkeypatch.setattr(gui, '_HAS_DND', True)
    return instances


@pytest.mark.parametrize('error', [RuntimeError('Unable to load tkdnd library.'), ValueError('file name too long')])
def test_native_drop_failure_opens_plain_gui_and_destroys_failed_root(monkeypatch, capsys, error):
    def require(root): raise error
    instances = setup_roots(monkeypatch, require)
    root = gui._make_root()
    assert len(instances) == 2 and instances[0].destroyed
    assert root is instances[1] and not root.destroyed
    assert gui._HAS_DND is False
    assert 'folder picker remains available' in capsys.readouterr().err


def test_working_native_drop_extension_is_preserved(monkeypatch):
    instances = setup_roots(monkeypatch, lambda root: 'tested-version')
    root = gui._make_root()
    assert instances == [root] and not root.destroyed
    assert root.TkdndVersion == 'tested-version' and gui._HAS_DND is True
