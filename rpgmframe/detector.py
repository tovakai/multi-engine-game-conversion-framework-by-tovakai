"""Conservative game engine detection for RPG Maker and Godot."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rpgmframe.models import (
    Compatibility,
    Confidence,
    EngineVariant,
    GameInspection,
)
from rpgmframe.rgss import (
    archive_suffix_for_engine,
    choose_rgss_ini,
    engine_from_archive,
    engine_from_library,
    engine_from_scripts,
    find_rgss_inis,
    script_suffix_for_engine,
)

_VERSION_RE = re.compile(
    r"""RPGMAKER_VERSION\s*=\s*["'](?P<version>[^"']+)["']""",
    re.IGNORECASE,
)

_LEGACY_ENGINES = (
    EngineVariant.XP,
    EngineVariant.VX,
    EngineVariant.VX_ACE,
)


@dataclass(frozen=True)
class _Candidate:
    engine: EngineVariant
    source_root: Path
    game_root: Path
    marker_file: Path
    score: int
    evidence: tuple[str, ...]


def _normalize_path(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _read_text_head(path: Path, limit: int = 131072) -> str | None:
    try:
        data = path.read_bytes()[:limit]
    except OSError:
        return None
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def _casefold_child(root: Path, name: str) -> Path:
    direct = root / name
    if direct.exists():
        return direct
    try:
        matches = [
            child for child in root.iterdir()
            if child.name.casefold() == name.casefold()
        ]
    except OSError:
        return direct
    return matches[0] if len(matches) == 1 else direct


def _score_web_candidate(
    evidence_root: Path,
    source_root: Path,
    *,
    engine: EngineVariant,
    game_root: Path,
    core_name: str,
) -> _Candidate | None:
    core = game_root / "js" / core_name
    if not core.is_file():
        return None

    evidence: list[str] = [_relative(core, evidence_root)]
    score = 6

    system_json = game_root / "data" / "System.json"
    if system_json.is_file():
        score += 3
        evidence.append(_relative(system_json, evidence_root))

    index_html = game_root / "index.html"
    if index_html.is_file():
        score += 1
        evidence.append(_relative(index_html, evidence_root))

    package_candidates = (source_root / "package.json", game_root / "package.json")
    package = next((p for p in package_candidates if p.is_file()), None)
    if package is not None:
        score += 1
        evidence.append(_relative(package, evidence_root))

    return _Candidate(
        engine=engine,
        source_root=source_root,
        game_root=game_root,
        marker_file=core,
        score=score,
        evidence=tuple(dict.fromkeys(evidence)),
    )


def _score_rgss_candidate(
    evidence_root: Path,
    source_root: Path,
    *,
    engine: EngineVariant,
) -> _Candidate | None:
    evidence: list[str] = []
    score = 0
    marker: Path | None = None

    data_dir = _casefold_child(source_root, "Data")
    suffix = script_suffix_for_engine(engine)

    try:
        data_files = [path for path in data_dir.iterdir() if path.is_file()]
    except OSError:
        data_files = []

    scripts = next(
        (
            path for path in data_files
            if path.name.casefold() == f"scripts{suffix}".casefold()
        ),
        None,
    )
    if scripts is not None:
        score += 7
        marker = scripts
        evidence.append(_relative(scripts, evidence_root))

    system = next(
        (
            path for path in data_files
            if path.name.casefold() == f"system{suffix}".casefold()
        ),
        None,
    )
    if system is not None:
        score += 2
        evidence.append(_relative(system, evidence_root))

    archive_suffix = archive_suffix_for_engine(engine)
    try:
        archives = [
            path
            for path in source_root.iterdir()
            if path.is_file() and path.suffix.casefold() == archive_suffix
        ]
    except OSError:
        archives = []
    if archives:
        score += 6
        marker = marker or archives[0]
        evidence.extend(_relative(path, evidence_root) for path in archives[:3])

    for ini in find_rgss_inis(source_root):
        scripts_engine = engine_from_scripts(ini.scripts)
        library_engine = engine_from_library(ini.library)
        if scripts_engine is engine:
            score += 4
            marker = marker or ini.path
            evidence.append(_relative(ini.path, evidence_root))
        elif library_engine is engine:
            score += 3
            marker = marker or ini.path
            evidence.append(_relative(ini.path, evidence_root))

    if score == 0 or marker is None:
        return None

    return _Candidate(
        engine=engine,
        source_root=source_root,
        game_root=source_root,
        marker_file=marker,
        score=score,
        evidence=tuple(dict.fromkeys(evidence)),
    )


def _collect_candidates(source_root: Path, *, evidence_root: Path) -> list[_Candidate]:
    candidates: list[_Candidate] = []

    for candidate in (
        _score_web_candidate(
            evidence_root,
            source_root,
            engine=EngineVariant.MV,
            game_root=source_root / "www",
            core_name="rpg_core.js",
        ),
        _score_web_candidate(
            evidence_root,
            source_root,
            engine=EngineVariant.MV,
            game_root=source_root,
            core_name="rpg_core.js",
        ),
        _score_web_candidate(
            evidence_root,
            source_root,
            engine=EngineVariant.MZ,
            game_root=source_root,
            core_name="rmmz_core.js",
        ),
        _score_web_candidate(
            evidence_root,
            source_root,
            engine=EngineVariant.MZ,
            game_root=source_root / "www",
            core_name="rmmz_core.js",
        ),
    ):
        if candidate:
            candidates.append(candidate)

    for engine in _LEGACY_ENGINES:
        candidate = _score_rgss_candidate(
            evidence_root,
            source_root,
            engine=engine,
        )
        if candidate:
            candidates.append(candidate)

    return candidates


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


def _find_package_json(source_root: Path, game_root: Path) -> Path | None:
    for candidate in (source_root / "package.json", game_root / "package.json"):
        if candidate.is_file():
            return candidate
    return None


def _detect_web_game_name(game_root: Path, package_json: Path | None) -> str | None:
    system = _read_json(game_root / "data" / "System.json")
    if system:
        title = system.get("gameTitle")
        if isinstance(title, str) and title.strip():
            return title.strip()

    if package_json:
        package = _read_json(package_json)
        if package:
            window = package.get("window")
            if isinstance(window, dict):
                title = window.get("title")
                if isinstance(title, str) and title.strip():
                    return title.strip()
            name = package.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return None


def _detect_engine_version(core_file: Path) -> str | None:
    text = _read_text_head(core_file)
    if not text:
        return None
    match = _VERSION_RE.search(text)
    return match.group("version").strip() if match else None


def _confidence_for_score(score: int) -> Confidence:
    if score >= 9:
        return Confidence.HIGH
    if score >= 7:
        return Confidence.MEDIUM
    return Confidence.LOW


def inspect_game(path: Path | str) -> GameInspection:
    """
    Detect Godot plus RPG Maker XP/VX/VX Ace/MV/MZ signatures.

    Wrapper descent remains conservative: RPGMFrame only descends while there
    is exactly one obvious child directory.
    """
    root = _normalize_path(path)

    if not root.exists():
        return GameInspection(
            source_path=root,
            warnings=[f"Path does not exist: {root}"],
        )
    if not root.is_dir():
        return GameInspection(
            source_path=root,
            warnings=[f"Path is not a directory: {root}"],
        )

    from rpgmframe.godot import inspect_godot

    godot = inspect_godot(root)
    if godot is not None and (godot.recognized or godot.family.value == "godot"):
        return godot

    current_root = root
    wrapper_chain: list[Path] = []
    seen_roots = {root}
    candidates = _collect_candidates(current_root, evidence_root=root)

    while not candidates and len(wrapper_chain) < 16:
        wrapper = _single_wrapper_child(current_root)
        if wrapper is None:
            break
        resolved_wrapper = wrapper.resolve()
        if resolved_wrapper in seen_roots:
            break
        seen_roots.add(resolved_wrapper)
        wrapper_chain.append(wrapper)
        current_root = wrapper
        candidates = _collect_candidates(current_root, evidence_root=root)

    if not candidates:
        return GameInspection(
            source_path=root,
            warnings=[
                "No supported game engine signature was found "
                "(Godot PCK, XP/VX/VX Ace RGSS data, or MV/MZ JavaScript core)."
            ],
        )

    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    best = candidates[0]

    if len(candidates) > 1:
        runner_up = candidates[1]
        if runner_up.score == best.score and runner_up.engine is not best.engine:
            evidence = list(dict.fromkeys(best.evidence + runner_up.evidence))
            engines = {best.engine, runner_up.engine}
            if engines == {EngineVariant.MV, EngineVariant.MZ}:
                warning = (
                    "Conflicting MV and MZ engine signatures have equal "
                    "confidence; refusing to guess."
                )
            else:
                warning = (
                    "Conflicting RPG Maker generation signatures have equal "
                    "confidence; refusing to guess."
                )
            return GameInspection(
                source_path=root,
                evidence=evidence,
                warnings=[warning],
            )

    warnings: list[str] = []
    if wrapper_chain:
        warnings.append(
            "Auto-descended through wrapper directories: "
            f"{_relative(wrapper_chain[-1], root)}"
        )

    if best.engine in {EngineVariant.MV, EngineVariant.MZ}:
        package_json = _find_package_json(best.source_root, best.game_root)
        if not (best.game_root / "data" / "System.json").is_file():
            warnings.append(
                "Engine core found, but data/System.json is missing; "
                "this may be an incomplete game directory."
            )
        return GameInspection(
            source_path=root,
            engine=best.engine,
            runtime="nwjs",
            confidence=_confidence_for_score(best.score),
            game_root=best.game_root,
            game_name=_detect_web_game_name(best.game_root, package_json)
            or best.source_root.name,
            engine_version=_detect_engine_version(best.marker_file),
            package_json=package_json,
            evidence=list(best.evidence),
            warnings=warnings,
            compatibility=Compatibility.SUPPORTED,
        )

    ini = choose_rgss_ini(best.game_root, best.engine)
    if ini is None:
        warnings.append(
            "RGSS generation was detected from game data, but no unambiguous "
            "RPG Maker [Game] INI was found. mkxp-z can still try its defaults."
        )

    data_dir = _casefold_child(best.game_root, "Data")
    try:
        has_script_data = any(
            path.is_file() and engine_from_scripts(path.name) is best.engine
            for path in data_dir.iterdir()
        )
    except OSError:
        has_script_data = False
    try:
        has_archive = any(
            path.is_file() and engine_from_archive(path) is best.engine
            for path in best.game_root.iterdir()
        )
    except OSError:
        has_archive = False
    if not has_script_data and not has_archive:
        warnings.append(
            "RGSS metadata was found, but neither the expected Scripts data "
            "nor encrypted game archive was found."
        )

    version = None
    if ini and ini.library:
        version = Path(ini.library.replace("\\", "/")).stem

    return GameInspection(
        source_path=root,
        engine=best.engine,
        runtime="mkxp-z",
        confidence=_confidence_for_score(best.score),
        game_root=best.game_root,
        game_name=(ini.title if ini and ini.title else best.source_root.name),
        engine_version=version,
        package_json=None,
        evidence=list(best.evidence),
        warnings=warnings,
        compatibility=Compatibility.NEEDS_TESTING,
    )
