"""XDG-style FrameBench state locations. Never writes under Steam game install trees."""

from __future__ import annotations

import os
from pathlib import Path


def state_root(home: Path | None = None) -> Path:
    if override := os.environ.get("FRAMEBENCH_STATE"):
        return Path(override)
    base = Path(home) if home is not None else Path.home()
    xdg = os.environ.get("XDG_STATE_HOME")
    root = Path(xdg) if xdg else base / ".local" / "state"
    return root / "framebench"


def mode_path(appid: int, *, home: Path | None = None) -> Path:
    return state_root(home) / "mode" / f"{int(appid)}.mode"


def journal_path(*, home: Path | None = None) -> Path:
    return state_root(home) / "journal.json"


def runs_dir(*, home: Path | None = None) -> Path:
    return state_root(home) / "runs"


def wrapper_copy(*, home: Path | None = None) -> Path:
    return state_root(home) / "dual_mode_launch.py"


def catalog_cache(*, home: Path | None = None) -> Path:
    return state_root(home) / "catalog.json"
