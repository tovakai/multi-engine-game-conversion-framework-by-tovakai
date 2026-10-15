"""Generate original, opt-in Steam Input profiles for converted games."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

ENGINES = frozenset({"renpy", "rpg2k", "xp", "vx", "vxace", "mv", "mz"})
CONTROLLERS = ("controller_steamframe_pair", "controller_triton", "controller_generic", "controller_xboxone",
               "controller_xbox360", "controller_neptune", "controller_ps4", "controller_ps5")
PROFILE_ID = "megcfbt-controller-pointer-v1"


def _quoted(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ') + '"'


def _vdf(pairs, indent=0):
    lines = []
    for key, value in pairs:
        prefix = "\t" * indent
        if isinstance(value, list):
            lines.extend([prefix + _quoted(key), prefix + "{", _vdf(value, indent + 1), prefix + "}"])
        else:
            lines.append(prefix + _quoted(key) + "\t" + _quoted(value))
    return "\n".join(lines)


def _input(binding):
    # Regular press bindings retain button-down until release (no turbo/toggle).
    return [("activators", [("Full_Press", [("bindings", [("binding", binding)])])])]


def profile_text(engine: str, controller_type: str, *, sensitivity=100, deadzone=8000) -> str:
    if engine not in ENGINES or controller_type not in CONTROLLERS:
        raise ValueError("Unsupported controller profile engine or controller type")
    if type(sensitivity) is not int or not 1 <= sensitivity <= 300:
        raise ValueError("Pointer sensitivity must be between 1 and 300")
    if type(deadzone) is not int or not 0 <= deadzone <= 20000:
        raise ValueError("Pointer deadzone must be between 0 and 20000")
    renpy = engine == "renpy"
    name = "RenPy" if renpy else "RPG Maker"
    groups = []
    def group(mode, inputs, settings=None):
        identifier = str(len(groups) + 1)
        values = [("id", identifier), ("mode", mode),
                  ("inputs", [(key, _input(binding)) for key, binding in inputs.items()])]
        if settings:
            values.append(("settings", [(key, str(value)) for key, value in settings.items()]))
        groups.append(("group", values))
        return identifier
    directions = {"dpad_north": "key_press UP_ARROW, Up", "dpad_south": "key_press DOWN_ARROW, Down",
                  "dpad_west": "key_press LEFT_ARROW, Left", "dpad_east": "key_press RIGHT_ARROW, Right"}
    dpad = group("dpad", directions, {"requires_click": 0})
    stick = group("dpad", directions, {"requires_click": 0})
    faces = group("four_buttons", {"button_a": "key_press RETURN, Confirm",
                  "button_b": "key_press ESCAPE, Back",
                  "button_x": "key_press H, Hide dialogue" if renpy else "key_press LEFT_SHIFT, Run",
                  "button_y": "key_press ESCAPE, Menu"})
    switches = group("switches", {"button_escape": "key_press ESCAPE, Menu",
                      "button_menu": "key_press TAB, Skip" if renpy else "key_press ESCAPE, Menu",
                      "left_bumper": "key_press PAGE_UP, Previous" if renpy else "key_press Q, Previous",
                      "right_bumper": "key_press PAGE_DOWN, Next" if renpy else "key_press W, Next"})
    # CHANGE_PRESET uses 1-based action-set indices; preset IDs themselves are 0-based.
    normal_right = group("joystick_move", {"click": "controller_action CHANGE_PRESET 2 0 0, Pointer mode"},
                         {"output_joystick": 1})
    pointer_right = group("joystick_mouse", {"click": "controller_action CHANGE_PRESET 1 0 0, Game controls"},
                          {"sensitivity": sensitivity, "deadzone_inner_radius": deadzone})
    normal_left_trigger = group("trigger", {"click": "xinput_button TRIGGER_LEFT, Native left trigger"},
                                {"output_trigger": 1})
    normal_right_trigger = group("trigger", {"click": "xinput_button TRIGGER_RIGHT, Native right trigger"},
                                 {"output_trigger": 2})
    pointer_left_trigger = group("trigger", {"edge": "mouse_button RIGHT, Right click"},
                                 {"output_trigger": 0})
    pointer_right_trigger = group("trigger", {"edge": "mouse_button LEFT, Left click and drag"},
                                  {"output_trigger": 0})
    common = [(dpad, "dpad active"), (stick, "joystick active"),
              (faces, "button_diamond active"), (switches, "switch active")]
    presets = []
    for identifier, title, right, left_trigger, right_trigger in (
        ("0", "Game controls", normal_right, normal_left_trigger, normal_right_trigger),
        ("1", "Pointer mode", pointer_right, pointer_left_trigger, pointer_right_trigger),
    ):
        presets.append(("preset", [("id", identifier), ("name", title),
                        ("group_source_bindings", common + [(right, "right_joystick active"),
                         (left_trigger, "left_trigger active"), (right_trigger, "right_trigger active")])]))
    values = [("version", "3"), ("title", f"{name}: directions + R3 pointer toggle"),
              ("description", "D-pad/left stick navigate. R3 toggles right-stick pointer; RT clicks/drags, LT right-clicks. R3 again restores native right stick and triggers."),
              ("controller_type", controller_type),
              ("actions", [("Game controls", [("title", "Game controls"), ("legacy_set", "1")]),
                           ("Pointer mode", [("title", "Pointer mode"), ("legacy_set", "1")])])]
    return _vdf([("controller_mappings", values + groups + presets)]) + "\n"


def prepare_profile(build: Path, engine: str, *, sensitivity=100, deadzone=8000) -> Path:
    """Add setup assets only. This neither changes game scripts nor Steam settings."""
    if engine not in ENGINES:
        raise ValueError("Controller profiles currently support Ren'Py and RPG Maker only")
    destination = build / ".megcfbt/controllers"
    script = build / "setup-controller-profile.sh"
    if destination.exists() or script.exists():
        raise ValueError("Controller profile assets already exist; use a fresh conversion output")
    rendered = {kind: profile_text(engine, kind, sensitivity=sensitivity, deadzone=deadzone) for kind in CONTROLLERS}
    destination.mkdir(parents=True)
    files = {}
    for kind, text in rendered.items():
        name = f"{PROFILE_ID}-{engine}-{kind}.vdf"
        (destination / name).write_bytes(text.encode("utf-8"))
        files[kind] = {"file": name, "sha256": hashlib.sha256(text.encode()).hexdigest()}
    resources = Path(__file__).with_name("controller_support")
    for name in ("setup.py", "steam_cdp.py"):
        shutil.copy2(resources / name, destination / name)
    manifest = {"profile": PROFILE_ID, "engine": engine, "experimental": True,
                "activation": "explicit-per-shortcut", "initial_mode": "Game controls",
                "toggle": "R3", "sensitivity": sensitivity, "deadzone": deadzone, "controllers": files}
    (destination / "profile.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    script.write_bytes(('#!/usr/bin/env bash\nset -euo pipefail\nROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\nexec python3 "$ROOT/.megcfbt/controllers/setup.py" "$@"\n').encode("utf-8"))
    script.chmod(0o755)
    return destination
