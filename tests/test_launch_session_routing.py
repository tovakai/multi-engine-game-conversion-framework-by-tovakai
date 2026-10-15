"""Execute generated launchers with competing Steam/Frametop environments."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest

from renframe.builder import _launcher_script_body, _write_grafted_launcher
from rpgmframe.launchers import (
    _FRAME_ENV_PREAMBLE, godot_launcher_body, mkxp_launcher_body, nwjs_launcher_body,
)

pytestmark = pytest.mark.skipif(os.name != "posix" or not shutil.which("bash"),
                                reason="Generated Linux launchers require POSIX bash")

GRAPHICS = ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "XAUTHORITY")
STEAM = {"DISPLAY": ":71", "XDG_RUNTIME_DIR": "/run/user/1000",
         "XAUTHORITY": "/run/user/1000/steam-xauth", "SteamGameId": "123456789",
         "SteamAppId": "12345", "SteamLaunchCookie": "test-cookie"}
DESKTOP = {"DISPLAY": ":83", "WAYLAND_DISPLAY": "wayland-frametop",
           "XDG_RUNTIME_DIR": "/run/user/1000/frametop",
           "XAUTHORITY": "/run/user/1000/frametop/xauth"}


@pytest.fixture
def environment(tmp_path):
    base = dict(os.environ)
    for key in (*GRAPHICS, "SteamAppId", "SteamGameId", "SteamLaunchCookie",
                "LD_PRELOAD", "TOVAKAI_FRAME_PRESERVE_GRAPHICS"):
        base.pop(key, None)
    # A live process with a desktop environment reproduces the old /proc import.
    plasma = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                              env={**base, **DESKTOP})
    commands = tmp_path / "commands"
    commands.mkdir()
    marker = tmp_path / "plasma-looked-up"
    pgrep = commands / "pgrep"
    pgrep.write_text(f"#!/usr/bin/env bash\nprintf called > {shlex.quote(str(marker))}\nprintf '%s' {plasma.pid}\n")
    pgrep.chmod(0o755)
    base["PATH"] = str(commands) + os.pathsep + base.get("PATH", os.defpath)
    try:
        yield base, marker
    finally:
        plasma.terminate()
        plasma.wait(timeout=5)


def probe(root):
    path = root / "capture.py"
    path.write_text("import json,os,sys\nprint(json.dumps({'env':dict(os.environ),'args':sys.argv[1:]}))\n")
    return f"#!/usr/bin/env bash\nexec {shlex.quote(sys.executable)} {shlex.quote(str(path))} \"$@\"\n"


def run(path, environment):
    result = subprocess.run(["bash", str(path), "--route-probe"], env=environment,
                            text=True, capture_output=True, timeout=5, check=True)
    return json.loads(result.stdout)


@pytest.mark.parametrize("session", [STEAM, DESKTOP])
@pytest.mark.parametrize("backend", ["nwjs", "mkxp", "godot", "native"])
def test_shared_launchers_follow_caller_even_when_plasma_is_running(tmp_path, environment, backend, session):
    base, marker = environment
    root = tmp_path / "Game with spaces"
    root.mkdir()
    (root / "game").mkdir()
    executable = {"nwjs": "nw", "mkxp": "mkxp-z.aarch64", "godot": "godot.arm64",
                  "native": "runtime/player"}[backend]
    target = root / executable
    target.parent.mkdir(exist_ok=True)
    target.write_text(probe(root))
    target.chmod(0o755)
    body = {"nwjs": nwjs_launcher_body, "mkxp": mkxp_launcher_body,
            "godot": lambda: godot_launcher_body("game/test.pck"),
            "native": lambda: _FRAME_ENV_PREAMBLE + 'exec "$ROOT/runtime/player" "$@"\n'}[backend]()
    launcher = root / "launch.sh"
    launcher.write_text(body)
    result = run(launcher, {**base, **session})
    for key in (*GRAPHICS, "SteamAppId", "SteamGameId", "SteamLaunchCookie"):
        assert result["env"].get(key) == session.get(key)
    assert result["args"][-1] == "--route-probe"
    assert not marker.exists(), "Launchers must not borrow a different process's desktop"


@pytest.mark.parametrize("session", [STEAM, DESKTOP])
@pytest.mark.parametrize("kind", ["full-runtime", "grafted"])
def test_renpy_launchers_already_preserve_caller_session(tmp_path, environment, session, kind):
    base, marker = environment
    if kind == "full-runtime":
        (tmp_path / "renpy.sh").write_text(probe(tmp_path))
        launcher = tmp_path / "launch.sh"
        launcher.write_text(_launcher_script_body("renpy.sh", None, None))
    else:
        runtime = tmp_path / "lib/py3-linux-aarch64"
        runtime.mkdir(parents=True)
        (runtime / "python").write_text(probe(tmp_path))
        (tmp_path / "renpy.py").write_text("import renpy.bootstrap\n")
        launcher = _write_grafted_launcher(tmp_path, source_launcher=None,
                                           platform_name="py3-linux-aarch64")
    result = run(launcher, {**base, **session})
    for key in (*GRAPHICS, "SteamAppId", "SteamGameId", "SteamLaunchCookie"):
        assert result["env"].get(key) == session.get(key)
    assert result["args"][-1] == "--route-probe"
    assert not marker.exists()


@pytest.mark.parametrize("session", [{}, {"SteamGameId": "123456789"},
                                      {"WAYLAND_DISPLAY": "steam-wayland", "XDG_RUNTIME_DIR": "/run/user/1000"}])
def test_no_desktop_fallback_or_mixed_session(tmp_path, environment, session):
    base, marker = environment
    script = tmp_path / "launch.sh"
    script.write_text(_FRAME_ENV_PREAMBLE + probe(tmp_path).split("\n", 1)[1])
    result = run(script, {**base, **session})
    for key in GRAPHICS:
        assert result["env"].get(key) == session.get(key)
    assert not marker.exists()


@pytest.mark.parametrize("session", [STEAM, DESKTOP, {}])
def test_optional_steam_api_guard_covers_both_selected_sessions(tmp_path, environment, session):
    base, _ = environment
    # No child process is started after activation: shell builtins inspect the
    # environment without loading an ARM64 library on an x86 test machine.
    (tmp_path / "libframe_steam_env.so").touch()
    script = tmp_path / "launch.sh"
    script.write_text(_FRAME_ENV_PREAMBLE +
                      'printf "%s\\n" "${TOVAKAI_FRAME_PRESERVE_GRAPHICS-unset}" "${LD_PRELOAD-unset}"\n')
    result = subprocess.run(["bash", str(script)], env={**base, **session},
                            text=True, capture_output=True, timeout=5, check=True)
    if session:
        assert result.stdout.splitlines() == ["1", str(tmp_path / "libframe_steam_env.so")]
    else:
        assert result.stdout.splitlines() == ["unset", "unset"]
