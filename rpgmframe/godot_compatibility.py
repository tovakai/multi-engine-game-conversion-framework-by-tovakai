"""Narrow, evidence-backed rendering compatibility for Godot exports."""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rpgmframe.godot import GodotPack

CASSETTE_PROFILE_ID = "cassette-beasts-gles3-zink-norp-depth-v1"
CASSETTE_RUNTIME_ID = "godot-3.5.1-godotsteam-3.30-steamworks-1.62-frame-arm64-v1"


def cassette_rendering_profile(pack: GodotPack, app_id: str | None, runtime: dict) -> str | None:
    if not isinstance(runtime, dict):
        return None
    if (
        app_id == "1321440"
        and pack.path.stem.casefold() == "cassettebeasts"
        and (pack.major, pack.minor, pack.patch) == (3, 5, 1)
        and runtime.get("recipe_id") == CASSETTE_RUNTIME_ID
        and runtime.get("engine_version") == "3.5.1"
        and runtime.get("pack_loading") == "main-pack"
    ):
        return CASSETTE_PROFILE_ID
    return None


def merge_depth_override(text: str) -> str:
    """Preserve Godot Variant values and comments outside the two depth keys."""
    lines = text.splitlines(keepends=True)
    top_level = []
    quote = False
    escaped = False
    nesting = []
    for line in lines:
        top_level.append(not quote and not nesting)
        for character in line:
            if quote:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    quote = False
            elif character in ";#":
                break
            elif character == '"':
                quote = True
            elif character in "([{":
                nesting.append(character)
            elif character in ")]}":
                if not nesting or nesting.pop() != {")": "(", "]": "[", "}": "{"}[character]:
                    raise ValueError("Unbalanced Variant value in override.cfg; review before conversion")
    if quote or nesting:
        raise ValueError("Unbalanced Variant value in override.cfg; review before conversion")
    section_pattern = r"^\s*\[([^]]+)\]\s*(?:;.*)?$"
    sections = [(i, re.match(section_pattern, line.strip()) if top_level[i] else None)
                for i, line in enumerate(lines)]
    rendering = [i for i, match in sections if match and match.group(1) == "rendering"]
    if len(rendering) > 1:
        raise ValueError("Duplicate rendering sections in override.cfg; review before conversion")
    values = {
        "quality/depth_prepass/disable_for_vendors": '""',
        "quality/depth_prepass/enable": "true",
    }
    if not rendering:
        return text.rstrip("\r\n") + '\n\n[rendering]\n' + "".join(
            f"{key}={value}\n" for key, value in values.items())
    start = rendering[0]
    end = next((i for i, match in sections if i > start and match), len(lines))
    seen = set()
    for i in range(start + 1, end):
        match = re.match(r'^\s*(?:"([^"\n]+)"|([A-Za-z0-9_./]+))\s*=', lines[i]) if top_level[i] else None
        key = (match.group(1) or match.group(2)) if match else None
        if key in values:
            if i + 1 < len(lines) and not top_level[i + 1]:
                raise ValueError("Multiline depth setting in override.cfg; review before conversion")
            if key in seen:
                raise ValueError("Duplicate depth setting in override.cfg; review before conversion")
            lines[i] = f"{key}={values[key]}\n"
            seen.add(key)
    if end and not lines[end - 1].endswith("\n"):
        lines[end - 1] += "\n"
    lines[end:end] = [f"{key}={value}\n" for key, value in values.items() if key not in seen]
    return "".join(lines)


def install_cassette_rendering_profile(staging: Path, pack_path: Path) -> None:
    override = pack_path.parent / "override.cfg"
    if override.is_symlink():
        raise ValueError("Cassette override.cfg is a symlink; refusing to modify its target")
    original = override.read_text(encoding="utf-8-sig") if override.exists() else ""
    override.write_text(merge_depth_override(original), encoding="utf-8", newline="\n")
    receipt = {
        "profile_id": CASSETTE_PROFILE_ID,
        "steam_app_id": "1321440",
        "status": "experimental",
        "override_path": override.relative_to(staging).as_posix(),
        "rendering_overrides": {
            "quality/depth_prepass/disable_for_vendors": "",
            "quality/depth_prepass/enable": True,
        },
        "environment_additions": {"ZINK_DEBUG": "norp"},
    }
    (staging / "godot-compatibility.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
