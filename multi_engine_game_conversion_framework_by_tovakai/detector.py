"""One detector facade over RenFrame and RPGMFrame."""

from __future__ import annotations

from pathlib import Path

from renframe.inspect_service import inspect_game as inspect_renpy
from renpy_arm.convert import detect_profile, detect_version, is_renpy_game
from rpgmframe.detector import inspect_game as inspect_rpgm
from rpgmframe.models import EngineVariant

from .models import Backend, UnifiedInspection
from .source import SourceError, candidate_roots, prepare_for_inspection


def _renpy_result(root: Path) -> UnifiedInspection | None:
    for candidate in candidate_roots(root):
        if not is_renpy_game(candidate):
            continue

        info = inspect_renpy(candidate)
        profile = detect_profile(candidate)
        version = info.renpy_version
        if version is None:
            try:
                version = detect_version(candidate)
            except Exception:
                version = None

        evidence: list[str] = []
        if (candidate / "game").is_dir():
            evidence.append("game/")
        if (candidate / "renpy").is_dir():
            evidence.append("renpy/")
        if (candidate / "lib").is_dir():
            evidence.append("lib/")
        if info.version_source:
            evidence.append(f"version: {info.version_source}")
        if profile is not None:
            evidence.append(f"compatibility profile: {profile.profile.id}")

        compatibility = info.compatibility.value.lower()
        if profile is not None and compatibility in {
            "unknown_renpy_version",
            "needs_testing",
        }:
            compatibility = "supported_profile"

        return UnifiedInspection(
            source_path=candidate,
            recognized=True,
            backend=Backend.RENPY,
            family="renpy",
            engine="Ren'Py",
            engine_version=version,
            runtime="Ren'Py sdkarm",
            game_name=info.game_name or candidate.name,
            confidence="high" if version or profile is not None else "medium",
            compatibility=compatibility,
            evidence=tuple(evidence),
            warnings=tuple(info.warnings),
        )
    return None


def _rpgm_result(root: Path) -> UnifiedInspection | None:
    info = inspect_rpgm(root)
    if not info.recognized:
        return None

    if info.engine is EngineVariant.GODOT:
        family = "godot"
        engine = "Godot"
    else:
        family = "rpgmaker"
        labels = {
            EngineVariant.XP: "RPG Maker XP",
            EngineVariant.VX: "RPG Maker VX",
            EngineVariant.VX_ACE: "RPG Maker VX Ace",
            EngineVariant.MV: "RPG Maker MV",
            EngineVariant.MZ: "RPG Maker MZ",
        }
        engine = labels.get(info.engine, f"RPG Maker {info.engine.value.upper()}")

    return UnifiedInspection(
        source_path=info.source_path,
        recognized=True,
        backend=Backend.RPGMFRAME,
        family=family,
        engine=engine,
        engine_version=info.engine_version,
        runtime=info.runtime,
        game_name=info.game_name,
        confidence=info.confidence.value,
        compatibility=info.compatibility.value,
        evidence=tuple(info.evidence),
        warnings=tuple(info.warnings),
    )


def inspect_source(path: Path | str) -> UnifiedInspection:
    source = Path(path).expanduser().resolve()
    try:
        with prepare_for_inspection(source) as root:
            renpy = _renpy_result(root)
            rpgm = _rpgm_result(root)
    except SourceError as exc:
        return UnifiedInspection(
            source_path=source,
            recognized=False,
            backend=Backend.UNKNOWN,
            family="unknown",
            engine="Unknown",
            warnings=(str(exc),),
        )

    if renpy is not None and rpgm is not None:
        return UnifiedInspection(
            source_path=source,
            recognized=False,
            backend=Backend.AMBIGUOUS,
            family="ambiguous",
            engine="Ambiguous",
            confidence="low",
            compatibility="unknown",
            evidence=tuple(dict.fromkeys((*renpy.evidence, *rpgm.evidence))),
            warnings=(
                "Both Ren'Py and RPG Maker/Godot detectors matched. "
                "Refusing to choose a backend automatically.",
                *renpy.warnings,
                *rpgm.warnings,
            ),
        )

    chosen = renpy or rpgm
    if chosen is None:
        return UnifiedInspection(
            source_path=source,
            recognized=False,
            backend=Backend.UNKNOWN,
            family="unknown",
            engine="Unknown",
            compatibility="unknown",
            warnings=("No supported engine signature was found.",),
        )

    return UnifiedInspection(
        source_path=source,
        recognized=chosen.recognized,
        backend=chosen.backend,
        family=chosen.family,
        engine=chosen.engine,
        engine_version=chosen.engine_version,
        runtime=chosen.runtime,
        game_name=chosen.game_name,
        confidence=chosen.confidence,
        compatibility=chosen.compatibility,
        evidence=chosen.evidence,
        warnings=chosen.warnings,
    )
