"""Shared path and filesystem helpers."""

from __future__ import annotations

import re
from pathlib import Path


def normalize_path(path: Path | str) -> Path:
    """Return a resolved absolute path without requiring the target to exist."""
    return Path(path).expanduser().resolve(strict=False)


_FORBIDDEN_OUTPUT_ROOTS = frozenset(
    {
        Path("/"),
        Path("/root"),
        Path("/home"),
        Path("/usr"),
        Path("/etc"),
        Path("/var"),
        Path("/tmp"),
        Path("/opt"),
        Path("/boot"),
        Path("/dev"),
        Path("/proc"),
        Path("/sys"),
    }
)


def is_dangerous_output_path(path: Path) -> bool:
    """Return True for paths that must never be used as build output."""
    resolved = normalize_path(path)
    if resolved in _FORBIDDEN_OUTPUT_ROOTS:
        return True
    # Refuse filesystem / drive roots (parent == self).
    if resolved.parent == resolved:
        return True
    return False


def is_path_inside(inner: Path, outer: Path) -> bool:
    """True if *inner* equals *outer* or is nested under it."""
    inner_r = normalize_path(inner)
    outer_r = normalize_path(outer)
    if inner_r == outer_r:
        return True
    try:
        inner_r.relative_to(outer_r)
        return True
    except ValueError:
        return False


def is_ancestor(ancestor: Path, descendant: Path) -> bool:
    """True if *ancestor* is a strict parent of *descendant*."""
    anc = normalize_path(ancestor)
    desc = normalize_path(descendant)
    if anc == desc:
        return False
    try:
        desc.relative_to(anc)
        return True
    except ValueError:
        return False


def paths_conflict(source: Path, output: Path) -> bool:
    """True if output equals source or either path nests under the other."""
    src = normalize_path(source)
    out = normalize_path(output)
    if out == src:
        return True
    return is_path_inside(out, src) or is_path_inside(src, out)


def guess_game_name(source: Path) -> str:
    """Best-effort display name from directory name."""
    name = source.name.strip()
    return name or "Unknown Game"


def sanitize_fs_name(name: str, *, fallback: str = "Game") -> str:
    """
    Sanitize a human name for filesystem / launcher use.

    Keeps letters, digits, dashes, and underscores. Spaces are removed so
    ``Example Game`` becomes ``ExampleGame``.
    """
    cleaned = name.strip().replace(" ", "")
    cleaned = re.sub(r"[^\w\-]+", "", cleaned, flags=re.UNICODE)
    cleaned = cleaned.strip("._-")
    return cleaned or fallback


RUNTIME_DIR_NAMES = frozenset(
    {
        "renpy",
        "lib",
        "rapt",
        "renios",
        "update",
    }
)

RUNTIME_FILE_NAMES = frozenset(
    {
        "renpy.py",
        "renpy.sh",
        "renpy.app",
    }
)


def is_runtime_owned_path(relative: Path) -> bool:
    """
    Classify a path relative to the game root as stock Ren'Py runtime.

    Game content lives primarily under game/. Stock runtime binaries live under
    renpy/, lib/, and top-level launcher wrappers.
    """
    parts = relative.parts
    if not parts:
        return False

    first = parts[0].lower()
    if first in RUNTIME_DIR_NAMES:
        return True

    name = relative.name.lower()
    if len(parts) == 1 and (
        name in RUNTIME_FILE_NAMES
        or name.endswith(".sh")
        or name.endswith(".exe")
        or name.endswith(".app")
        or name.endswith(".py")
    ):
        # Top-level launchers and renpy.py are runtime/distribution wrappers.
        return True

    return False
