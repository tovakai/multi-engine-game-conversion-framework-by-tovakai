"""Helpers for identifying RPG Maker XP/VX/VX Ace RGSS projects."""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path

from rpgmframe.models import EngineVariant


@dataclass(frozen=True)
class RgssIni:
    path: Path
    title: str | None
    library: str | None
    scripts: str | None
    exec_name: str
    rtps: tuple[str, ...]


_SCRIPT_SUFFIX_TO_ENGINE = {
    ".rxdata": EngineVariant.XP,
    ".rvdata": EngineVariant.VX,
    ".rvdata2": EngineVariant.VX_ACE,
}

_ARCHIVE_SUFFIX_TO_ENGINE = {
    ".rgssad": EngineVariant.XP,
    ".rgss2a": EngineVariant.VX,
    ".rgss3a": EngineVariant.VX_ACE,
}


def engine_from_scripts(value: str | None) -> EngineVariant | None:
    if not value:
        return None
    normalized = value.replace("\\", "/").lower()
    for suffix, engine in _SCRIPT_SUFFIX_TO_ENGINE.items():
        if normalized.endswith(suffix):
            return engine
    return None


def engine_from_library(value: str | None) -> EngineVariant | None:
    if not value:
        return None
    name = Path(value.replace("\\", "/")).name.upper()
    if name.startswith("RGSS1"):
        return EngineVariant.XP
    if name.startswith("RGSS2"):
        return EngineVariant.VX
    if name.startswith("RGSS3"):
        return EngineVariant.VX_ACE
    return None


def engine_from_archive(path: Path) -> EngineVariant | None:
    return _ARCHIVE_SUFFIX_TO_ENGINE.get(path.suffix.casefold())


def rgss_version_for_engine(engine: EngineVariant) -> int:
    return {
        EngineVariant.XP: 1,
        EngineVariant.VX: 2,
        EngineVariant.VX_ACE: 3,
    }[engine]


def script_suffix_for_engine(engine: EngineVariant) -> str:
    return {
        EngineVariant.XP: ".rxdata",
        EngineVariant.VX: ".rvdata",
        EngineVariant.VX_ACE: ".rvdata2",
    }[engine]


def archive_suffix_for_engine(engine: EngineVariant) -> str:
    return {
        EngineVariant.XP: ".rgssad",
        EngineVariant.VX: ".rgss2a",
        EngineVariant.VX_ACE: ".rgss3a",
    }[engine]


def _read_ini(path: Path) -> RgssIni | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None

    raw: str | None = None
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            raw = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if raw is None:
        return None

    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(raw)
    except configparser.Error:
        return None

    section_name = next(
        (name for name in parser.sections() if name.casefold() == "game"),
        None,
    )
    if section_name is None:
        return None

    section = parser[section_name]

    def value(name: str) -> str | None:
        found = section.get(name, fallback=None)
        if found is None:
            return None
        found = found.strip()
        return found or None

    rtps = tuple(
        item
        for item in (value("RTP1"), value("RTP2"), value("RTP3"))
        if item
    )
    return RgssIni(
        path=path,
        title=value("Title"),
        library=value("Library"),
        scripts=value("Scripts"),
        exec_name=path.stem,
        rtps=rtps,
    )


def find_rgss_inis(root: Path) -> list[RgssIni]:
    try:
        files = sorted(
            (
                path
                for path in root.iterdir()
                if path.is_file() and path.suffix.casefold() == ".ini"
            ),
            key=lambda path: (
                path.name.casefold() != "game.ini",
                path.name.casefold(),
            ),
        )
    except OSError:
        return []

    return [ini for path in files if (ini := _read_ini(path)) is not None]


def choose_rgss_ini(root: Path, engine: EngineVariant) -> RgssIni | None:
    inis = find_rgss_inis(root)
    if not inis:
        return None

    matching_scripts = [
        ini for ini in inis if engine_from_scripts(ini.scripts) is engine
    ]
    if len(matching_scripts) == 1:
        return matching_scripts[0]

    matching_library = [
        ini for ini in inis if engine_from_library(ini.library) is engine
    ]
    if len(matching_library) == 1:
        return matching_library[0]

    suffix = archive_suffix_for_engine(engine)
    try:
        archive_stems = {
            path.stem.casefold()
            for path in root.iterdir()
            if path.is_file() and path.suffix.casefold() == suffix
        }
    except OSError:
        archive_stems = set()

    matching_archive = [
        ini for ini in inis if ini.exec_name.casefold() in archive_stems
    ]
    if len(matching_archive) == 1:
        return matching_archive[0]

    return inis[0] if len(inis) == 1 else None
