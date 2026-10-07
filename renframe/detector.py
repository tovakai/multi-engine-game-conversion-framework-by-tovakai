"""Ren'Py game directory and version detection."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from pathlib import Path

from renframe.models import VersionHint
from renframe.utils import guess_game_name

_VERSION_RE = re.compile(
    r"""(?P<version>\d+\.\d+(?:\.\d+)?(?:\.\d+)?)""",
)
_ASSIGN_VERSION_RE = re.compile(
    r"""(?:^|\n)\s*(?:version|vc_version|Version)\s*=\s*['"](?P<version>\d+\.\d+(?:\.\d+)?)""",
    re.IGNORECASE,
)
_RENPY_VERSION_LINE_RE = re.compile(
    r"""renpy\s*(?:version)?\s*[:=]\s*['"]?(?P<version>\d+\.\d+(?:\.\d+)?)""",
    re.IGNORECASE,
)


def looks_like_renpy_game(path: Path) -> bool:
    """Return True if the directory shows common Ren'Py layout signals."""
    if not path.is_dir():
        return False

    game_dir = path / "game"
    renpy_dir = path / "renpy"
    has_game = game_dir.is_dir()
    has_renpy = renpy_dir.is_dir() and (renpy_dir / "__init__.py").is_file()

    if has_game and has_renpy:
        return True

    if has_renpy and _has_game_scripts(game_dir if has_game else path):
        return True

    if has_game and _has_game_scripts(game_dir):
        # Distributed games sometimes omit a full SDK-style renpy/ tree naming,
        # but still ship scripts plus a launcher.
        if any(path.glob("*.sh")) or any(path.glob("*.exe")) or (path / "lib").is_dir():
            return True
        return _has_game_scripts(game_dir)

    return False


def _has_game_scripts(directory: Path) -> bool:
    if not directory.is_dir():
        return False
    for pattern in ("*.rpa", "*.rpy", "*.rpyc"):
        if any(directory.rglob(pattern)):
            return True
    return False


def detect_layout_flags(path: Path) -> dict[str, bool]:
    """Return presence flags for common Ren'Py top-level entries."""
    return {
        "has_game_dir": (path / "game").is_dir(),
        "has_renpy_dir": (path / "renpy").is_dir(),
        "has_lib_dir": (path / "lib").is_dir(),
    }


def detect_runtime_architectures(path: Path) -> list[str]:
    """
    Infer bundled runtime architectures from lib/ directory names and binaries.
    """
    found: set[str] = set()
    lib = path / "lib"
    if not lib.is_dir():
        return []

    name_map = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "i686": "x86",
        "i386": "x86",
        "aarch64": "aarch64",
        "arm64": "aarch64",
        "armv7l": "arm",
        "windows-x86_64": "x86_64",
        "windows-i686": "x86",
        "linux-x86_64": "x86_64",
        "linux-aarch64": "aarch64",
        "py3-linux-x86_64": "x86_64",
        "py3-linux-aarch64": "aarch64",
        "py2-linux-x86_64": "x86_64",
        "python3.9": "unknown",
        "python3.10": "unknown",
        "python3.12": "unknown",
    }

    for child in lib.iterdir():
        lower = child.name.lower()
        for key, arch in name_map.items():
            if key in lower and arch != "unknown":
                found.add(arch)

    return sorted(found)


VersionStrategy = Callable[[Path], VersionHint | None]


def _read_text_head(path: Path, limit: int = 65536) -> str | None:
    try:
        data = path.read_bytes()[:limit]
    except OSError:
        return None
    for encoding in ("utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def strategy_versions_py(root: Path) -> VersionHint | None:
    """Parse renpy/versions.py (common in modern SDKs)."""
    candidate = root / "renpy" / "versions.py"
    if not candidate.is_file():
        return None
    text = _read_text_head(candidate)
    if not text:
        return None

    # Prefer an explicit version = "x.y.z" assignment over vc_version integers.
    match = re.search(
        r"""^\s*version\s*=\s*['"](?P<version>\d+\.\d+(?:\.\d+)?)""",
        text,
        re.MULTILINE,
    )
    if not match:
        match = _ASSIGN_VERSION_RE.search(text)
    if not match:
        return None

    version = match.group("version")
    return VersionHint(
        version=version,
        generation=_generation_from_version(version),
        source="renpy/versions.py",
        confidence="high",
    )


def strategy_renpy_init(root: Path) -> VersionHint | None:
    """Parse version constants from renpy/__init__.py."""
    candidate = root / "renpy" / "__init__.py"
    if not candidate.is_file():
        return None
    text = _read_text_head(candidate)
    if not text:
        return None

    match = re.search(
        r"""(?:version_tuple|version)\s*=\s*\(?(?P<body>[^\n]+)""",
        text,
    )
    if match:
        body = match.group("body")
        nums = re.findall(r"\d+", body)
        if len(nums) >= 2:
            version = ".".join(nums[:3]) if len(nums) >= 3 else ".".join(nums[:2])
            return VersionHint(
                version=version,
                generation=_generation_from_version(version),
                source="renpy/__init__.py",
                confidence="high",
            )

    match = _VERSION_RE.search(text)
    if match and "renpy" in text.lower():
        version = match.group("version")
        return VersionHint(
            version=version,
            generation=_generation_from_version(version),
            source="renpy/__init__.py",
            confidence="low",
            details="fallback regex match",
        )
    return None


def strategy_script_version(root: Path) -> VersionHint | None:
    """Look for version comments/strings in game/script_version*.txt or similar."""
    game = root / "game"
    search_roots = [game, root] if game.is_dir() else [root]
    patterns = (
        "script_version.txt",
        "script_version*.txt",
        "*version*.txt",
    )
    for base in search_roots:
        for pattern in patterns:
            for path in sorted(base.glob(pattern)):
                if not path.is_file():
                    continue
                text = _read_text_head(path, limit=4096)
                if not text:
                    continue
                match = _VERSION_RE.search(text)
                if match:
                    version = match.group("version")
                    return VersionHint(
                        version=version,
                        generation=_generation_from_version(version),
                        source=str(path.relative_to(root)),
                        confidence="medium",
                    )
    return None


def strategy_launcher_scripts(root: Path) -> VersionHint | None:
    """Scan top-level .sh launchers for Ren'Py version strings."""
    for path in sorted(root.glob("*.sh")):
        text = _read_text_head(path, limit=16384)
        if not text:
            continue
        match = _RENPY_VERSION_LINE_RE.search(text) or _VERSION_RE.search(text)
        if match and ("renpy" in text.lower() or "lib/py" in text.lower()):
            version = match.group("version")
            # Avoid treating shell utility versions as Ren'Py.
            if version.startswith("0.") and "renpy" not in text.lower():
                continue
            return VersionHint(
                version=version,
                generation=_generation_from_version(version),
                source=path.name,
                confidence="low",
                details="launcher script string",
            )
    return None


def strategy_lib_python_generation(root: Path) -> VersionHint | None:
    """
    Infer Ren'Py generation from lib/ layout when an exact version is missing.

    py3-* / python3.* => generation 8 (Python 3)
    py2-* / python2.* => generation 7 (Python 2)
    """
    lib = root / "lib"
    if not lib.is_dir():
        return None

    names = [p.name.lower() for p in lib.iterdir()]
    joined = " ".join(names)
    if "py3-" in joined or "python3" in joined:
        return VersionHint(
            version=None,
            generation=8,
            source="lib/",
            confidence="medium",
            details="Python 3 runtime layout suggests Ren'Py 8.x",
        )
    if "py2-" in joined or "python2" in joined:
        return VersionHint(
            version=None,
            generation=7,
            source="lib/",
            confidence="medium",
            details="Python 2 runtime layout suggests Ren'Py 7.x",
        )
    return None


DEFAULT_VERSION_STRATEGIES: tuple[VersionStrategy, ...] = (
    strategy_versions_py,
    strategy_renpy_init,
    strategy_script_version,
    strategy_launcher_scripts,
    strategy_lib_python_generation,
)


def _generation_from_version(version: str) -> int | None:
    try:
        major = int(version.split(".", 1)[0])
    except (ValueError, IndexError):
        return None
    if major >= 8:
        return 8
    if major == 7:
        return 7
    if major <= 6:
        return major
    return None


def collect_version_hints(
    root: Path,
    strategies: Iterable[VersionStrategy] | None = None,
) -> list[VersionHint]:
    """Run modular version detectors and return all non-empty hints."""
    hints: list[VersionHint] = []
    for strategy in strategies or DEFAULT_VERSION_STRATEGIES:
        try:
            hint = strategy(root)
        except OSError:
            continue
        if hint is not None:
            hints.append(hint)
    return hints


def select_best_version(hints: list[VersionHint]) -> VersionHint | None:
    """Pick the most trustworthy hint that includes a version string when possible."""
    if not hints:
        return None

    confidence_rank = {"high": 3, "medium": 2, "low": 1}
    with_version = [h for h in hints if h.version]
    pool = with_version or hints
    return sorted(
        pool,
        key=lambda h: (
            confidence_rank.get(h.confidence, 0),
            1 if h.version else 0,
            1 if h.generation else 0,
        ),
        reverse=True,
    )[0]


def detect_game_name(root: Path) -> str:
    """Derive a human-readable game name."""
    # Prefer a similarly named .sh launcher if present.
    for script in sorted(root.glob("*.sh")):
        stem = script.stem
        if stem.lower() in {"renpy", "linux-x86_64", "linux-aarch64"}:
            continue
        return stem.replace("-", " ").replace("_", " ")
    return guess_game_name(root)
