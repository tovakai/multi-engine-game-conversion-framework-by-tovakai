"""Conservative, asset-free original DDLC migration gate.

Layout evidence identifies a candidate, not authenticity or gameplay support.
Never open archives or story scripts to identify a game.
"""
from pathlib import Path

from renframe.models import GameInspection


def original_ddlc_candidate(inspection: GameInspection) -> bool:
    root = inspection.source_path
    if (not inspection.is_renpy or inspection.generation != 6
            or inspection.renpy_version != "6.99.12"):
        return False
    # Require authoritative engine evidence; reject contradictory versions.
    hints = [h for h in inspection.version_hints
             if h.source in {"renpy/__init__.py", "renpy/vc_version.py", "renpy/versions.py"}
             and h.version]
    if (not hints or not any(h.confidence == "high" for h in hints)
            or any(h.version != "6.99.12" for h in hints)):
        return False
    required = ["game", "renpy", "characters", "DDLC.exe", "DDLC.py"]
    required += [f"game/{name}.rpa" for name in ("audio", "images", "scripts", "fonts")]
    try:
        # Exact case and unique names matter on the Linux target. No symlinked
        # payload: character writes must never reach back into the source.
        for relative in required:
            path = root
            for part in Path(relative).parts:
                matches = [p for p in path.iterdir() if p.name.casefold() == part.casefold()]
                if len(matches) != 1 or matches[0].name != part or matches[0].is_symlink():
                    return False
                path = matches[0]
            if relative in {"game", "renpy", "characters"}:
                if not path.is_dir():
                    return False
            elif not path.is_file():
                return False
        # The original Steam layout has no loose game-version marker. If a
        # copy supplies one, require it to agree; do not inspect packed story
        # scripts to authenticate a release. Opt-in confirms user ownership
        # and the 1.1.1 source boundary, not cryptographic game authenticity.
        markers = [p for p in (root / "game").iterdir()
                   if p.name.casefold() == "script_version.txt"]
        if markers:
            marker = markers[0]
            if (len(markers) != 1 or marker.name != "script_version.txt"
                    or marker.is_symlink() or not marker.is_file()
                    or marker.stat().st_size > 64
                    or marker.read_text(encoding="utf-8-sig").strip() != "1.1.1"):
                return False
        if any(p.name.casefold().endswith("_data") or p.name.casefold() == "unityplayer.dll"
               for p in root.iterdir()):
            return False
        # Missing .chr files are legitimate later-act state. Unknown names are
        # not sufficient evidence for this narrowly scoped original profile.
        allowed = {"monika.chr", "sayori.chr", "natsuki.chr", "yuri.chr"}
        return all(p.is_file() and not p.is_symlink() and p.name in allowed
                   for p in (root / "characters").iterdir())
    except (OSError, UnicodeError):
        return False
