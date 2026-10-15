"""Provide diagnostics when pythonw/PyInstaller has no console streams."""
from __future__ import annotations

import os
from pathlib import Path
import sys


def ensure_gui_streams(directory: Path | None = None) -> Path | None:
    """Preserve real/captured streams; route missing ones to a startup log.

    GUI dependencies can emit warnings during import (for example when Windows
    cannot load a font from a long path). In windowed applications these writes
    must not turn an otherwise recoverable warning into a startup exception.
    """
    missing = [name for name in ('stdout', 'stderr') if getattr(sys, name) is None]
    if not missing:
        return None
    if directory is None:
        base = os.environ.get('LOCALAPPDATA') if sys.platform == 'win32' else os.environ.get('XDG_STATE_HOME')
        directory = (Path(base) if base else Path.home() / '.local/state') / 'megcfbt/logs'
    log = directory / 'gui-startup.log'
    try:
        directory.mkdir(parents=True, exist_ok=True)
        stream = log.open('a', encoding='utf-8', errors='backslashreplace', buffering=1)
    except OSError:
        # Even an unwritable profile must not make a dependency warning fatal.
        stream = open(os.devnull, 'w', encoding='utf-8')
        log = None
    for name in missing:
        setattr(sys, name, stream)
    return log
