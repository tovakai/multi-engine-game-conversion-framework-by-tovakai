"""Conservative Godot export detection and PCK inspection."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from rpgmframe.models import (
    Compatibility,
    Confidence,
    EngineFamily,
    EngineVariant,
    GameInspection,
)

PCK_MAGIC = 0x43504447
PCK_MAGIC_BYTES = b"GDPC"


@dataclass(frozen=True)
class GodotPack:
    path: Path
    offset: int
    size: int
    pack_format: int
    major: int
    minor: int
    patch: int
    embedded: bool

    @property
    def version(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


def _read_header(path: Path, offset: int = 0) -> GodotPack | None:
    try:
        file_size = path.stat().st_size
        with path.open("rb") as handle:
            handle.seek(offset)
            header = handle.read(20)
    except OSError:
        return None

    if len(header) != 20:
        return None
    magic, pack_format, major, minor, patch = struct.unpack("<IIIII", header)
    if magic != PCK_MAGIC:
        return None
    if not (1 <= pack_format <= 16):
        return None
    if not (1 <= major <= 99 and 0 <= minor <= 99 and 0 <= patch <= 999):
        return None

    return GodotPack(
        path=path,
        offset=offset,
        size=file_size - offset,
        pack_format=pack_format,
        major=major,
        minor=minor,
        patch=patch,
        embedded=offset != 0,
    )


def _embedded_pack(path: Path) -> GodotPack | None:
    try:
        file_size = path.stat().st_size
        if file_size < 32:
            return None
        with path.open("rb") as handle:
            handle.seek(file_size - 12)
            footer = handle.read(12)
    except OSError:
        return None

    if len(footer) != 12:
        return None
    pack_size, magic = struct.unpack("<QI", footer)
    if magic != PCK_MAGIC:
        return None
    if pack_size < 20 or pack_size > file_size - 12:
        return None

    offset = file_size - 12 - pack_size
    pack = _read_header(path, offset)
    if pack is None:
        return None
    return GodotPack(
        path=path,
        offset=offset,
        size=pack_size,
        pack_format=pack.pack_format,
        major=pack.major,
        minor=pack.minor,
        patch=pack.patch,
        embedded=True,
    )


def _single_wrapper_child(root: Path) -> Path | None:
    try:
        children = [
            child
            for child in root.iterdir()
            if child.is_dir()
            and not child.name.startswith(".")
            and child.name != "__MACOSX"
        ]
    except OSError:
        return None
    return children[0] if len(children) == 1 else None


def _candidate_packs(root: Path) -> list[GodotPack]:
    try:
        files = [path for path in root.iterdir() if path.is_file()]
    except OSError:
        return []

    standalone = [
        pack
        for path in files
        if path.suffix.casefold() == ".pck"
        if (pack := _read_header(path)) is not None
    ]
    if standalone:
        if len(standalone) == 1:
            return standalone

        exe_stems = {
            path.stem.casefold()
            for path in files
            if path.suffix.casefold() == ".exe"
        }
        matching = [
            pack for pack in standalone
            if pack.path.stem.casefold() in exe_stems
        ]
        if len(matching) == 1:
            return matching
        return standalone

    embedded = [
        pack
        for path in files
        if path.suffix.casefold() == ".exe"
        if (pack := _embedded_pack(path)) is not None
    ]
    return embedded


def find_godot_pack(root: Path) -> GodotPack | None:
    packs = _candidate_packs(root)
    return packs[0] if len(packs) == 1 else None


def is_csharp_export(root: Path) -> bool:
    try:
        entries = list(root.rglob("*"))
    except OSError:
        return False

    files = [path for path in entries if path.is_file()]
    if any(path.name.casefold().endswith(".runtimeconfig.json") for path in files):
        return True
    if any(path.name.casefold().endswith(".deps.json") for path in files):
        return True
    return any(
        path.is_dir() and path.name.casefold() == "godotsharp"
        for path in entries
    )


def materialize_pack(pack: GodotPack, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not pack.embedded:
        destination.write_bytes(pack.path.read_bytes())
        return

    remaining = pack.size
    with pack.path.open("rb") as source, destination.open("wb") as target:
        source.seek(pack.offset)
        while remaining:
            chunk = source.read(min(1024 * 1024, remaining))
            if not chunk:
                raise OSError(f"Unexpected end of embedded PCK: {pack.path}")
            target.write(chunk)
            remaining -= len(chunk)


def inspect_godot(path: Path | str) -> GameInspection | None:
    root = Path(path).expanduser().resolve()
    current = root
    wrapper_chain: list[Path] = []
    seen = {root}

    for _ in range(17):
        packs = _candidate_packs(current)
        if packs:
            break
        wrapper = _single_wrapper_child(current)
        if wrapper is None:
            return None
        resolved = wrapper.resolve()
        if resolved in seen:
            return None
        seen.add(resolved)
        wrapper_chain.append(wrapper)
        current = wrapper
    else:
        return None

    packs = _candidate_packs(current)
    if len(packs) != 1:
        evidence = [pack.path.relative_to(root).as_posix() for pack in packs]
        return GameInspection(
            source_path=root,
            family=EngineFamily.GODOT,
            evidence=evidence,
            warnings=[
                "Multiple Godot game packs were found and no unique main PCK "
                "could be selected safely."
            ],
        )

    pack = packs[0]
    try:
        evidence_path = pack.path.relative_to(root).as_posix()
    except ValueError:
        evidence_path = pack.path.as_posix()

    warnings: list[str] = []
    if wrapper_chain:
        warnings.append(
            "Auto-descended through wrapper directories: "
            + wrapper_chain[-1].relative_to(root).as_posix()
        )
    if pack.embedded:
        warnings.append(
            f"Godot PCK is embedded in {pack.path.name}; RPGMFrame will extract "
            "the pack without modifying the source executable."
        )

    csharp = is_csharp_export(current)
    compatibility = Compatibility.NEEDS_TESTING
    if csharp:
        compatibility = Compatibility.UNKNOWN
        warnings.append(
            "Godot C#/.NET export detected. Automatic ARM64 conversion is not "
            "enabled yet because the managed/native runtime bundle is platform-specific."
        )

    return GameInspection(
        source_path=root,
        family=EngineFamily.GODOT,
        engine=EngineVariant.GODOT,
        runtime="godot",
        confidence=Confidence.HIGH,
        game_root=current,
        game_name=pack.path.stem,
        engine_version=pack.version,
        evidence=[evidence_path],
        warnings=warnings,
        compatibility=compatibility,
    )
