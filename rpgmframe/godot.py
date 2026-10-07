"""Conservative Godot export detection and PCK inspection."""

from __future__ import annotations

import struct
from collections import deque
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


_DISCOVERY_SKIP_DIRS = frozenset(
    {
        ".git",
        "__macosx",
        "__pycache__",
        "steam_settings",
    }
)


def _subdirectories(root: Path) -> list[Path]:
    try:
        children = [
            child
            for child in root.iterdir()
            if child.is_dir()
            and not child.name.startswith(".")
            and child.name.casefold() not in _DISCOVERY_SKIP_DIRS
        ]
    except OSError:
        return []
    return sorted(children, key=lambda path: path.name.casefold())


def _discover_pack_roots(
    root: Path,
    *,
    max_depth: int = 5,
    max_directories: int = 128,
) -> list[tuple[int, Path, list[GodotPack]]]:
    """Find the shallowest Godot payload roots below a selected directory.

    Real-world Windows game bundles frequently wrap the actual install under
    paths such as Game/common/Game and place unrelated helper directories
    beside it. The old single-child descent stopped as soon as a sibling such
    as steam_settings existed.

    Discovery is breadth-first, bounded, and conservative: once any Godot
    payload is found at a depth, deeper directories are ignored. Multiple
    payload roots at the same shallowest depth remain ambiguous instead of
    being guessed.
    """
    queue: deque[tuple[Path, int]] = deque([(root, 0)])
    seen: set[Path] = set()
    matches: list[tuple[int, Path, list[GodotPack]]] = []
    shallowest_match: int | None = None
    visited = 0

    while queue and visited < max_directories:
        current, depth = queue.popleft()
        if shallowest_match is not None and depth > shallowest_match:
            break

        try:
            resolved = current.resolve()
        except OSError:
            resolved = current
        if resolved in seen:
            continue
        seen.add(resolved)
        visited += 1

        packs = _candidate_packs(current)
        if packs:
            matches.append((depth, current, packs))
            shallowest_match = depth
            continue

        if depth >= max_depth:
            continue
        for child in _subdirectories(current):
            queue.append((child, depth + 1))

    return matches


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
    matches = _discover_pack_roots(root)
    if not matches:
        return None

    if len(matches) != 1:
        evidence: list[str] = []
        for _, candidate_root, packs in matches:
            for pack in packs:
                try:
                    evidence.append(pack.path.relative_to(root).as_posix())
                except ValueError:
                    evidence.append(pack.path.as_posix())
        return GameInspection(
            source_path=root,
            family=EngineFamily.GODOT,
            evidence=evidence,
            warnings=[
                "Multiple Godot game roots were found at the same directory "
                "depth; refusing to guess which payload is the main game."
            ],
        )

    _, current, packs = matches[0]
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
    if current != root:
        warnings.append(
            "Auto-discovered Godot game root in subfolder: "
            + current.relative_to(root).as_posix()
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
