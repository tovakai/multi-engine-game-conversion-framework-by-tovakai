"""Transactional native/original switching with crash-safe restoration.

Preferred path: install a dual-mode wrapper once, then toggle a mode file.
The wrapper forwards original Steam %command% (FEX/Proton included) or starts
the converted package. Steam AppID and launch context stay authentic.

Fallback: consent-gated live Steam launch-option mutation using steam_client,
the same backup/compare/restore discipline as experiments/sts2-steamworks/steam_entry.py.

Never edits original Steam game files. Never leaves a conversion permanently
disabled if restoration can still see the installed wrapper command.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from framebench import SWITCH_KIND, WRAPPER_KIND
from framebench import paths
from framebench.process import game_is_running
from framebench.wrapper import write_mode

WRAPPER_MARKERS = (
    "framebench",
    "dual_mode_launch",
    "play-steam.sh",
    "launch-steam.sh",
    "steam_launch.py",
)


class SwitchError(RuntimeError):
    pass


@dataclass
class SwitchState:
    appid: int
    requested_mode: str
    normal_launch_options: str
    active_launch_options: str
    wrapper_installed: bool
    method: str
    package: str
    status: str

    def as_dict(self) -> dict:
        return {
            "kind": SWITCH_KIND,
            "appid": self.appid,
            "requested_mode": self.requested_mode,
            "normal_launch_options": self.normal_launch_options,
            "active_launch_options": self.active_launch_options,
            "wrapper_installed": self.wrapper_installed,
            "method": self.method,
            "package": self.package,
            "status": self.status,
        }


def wrapper_command(package: Path, appid: int, *, home: Path | None = None, python: str | None = None) -> str:
    script = install_wrapper_copy(home=home)
    interpreter = python or sys.executable
    return f'"{interpreter}" "{script}" --package "{Path(package).resolve()}" --appid {int(appid)} -- %command%'


def looks_like_wrapper(command: str) -> bool:
    blob = (command or "").casefold()
    return any(marker in blob for marker in WRAPPER_MARKERS) and "%command%" in blob


def install_wrapper_copy(*, home: Path | None = None) -> Path:
    destination = paths.wrapper_copy(home=home)
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).with_name("wrapper.py")
    if not destination.is_file() or destination.read_bytes() != source.read_bytes():
        shutil.copy2(source, destination)
    return destination


def load_journal(*, home: Path | None = None) -> dict | None:
    path = paths.journal_path(home=home)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if data.get("kind") != SWITCH_KIND:
        raise SwitchError("Unrecognized FrameBench switch journal")
    return data


def save_journal(record: dict, *, home: Path | None = None) -> Path:
    path = paths.journal_path(home=home)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def clear_journal(*, home: Path | None = None) -> None:
    path = paths.journal_path(home=home)
    try:
        path.unlink()
    except FileNotFoundError:
        return


def recover(*, home: Path | None = None, steam=None, running_check=game_is_running) -> dict:
    record = load_journal(home=home)
    if record is None:
        return {"recovered": False, "reason": "no journal"}
    if record.get("status") == "restored":
        clear_journal(home=home)
        return {"recovered": True, "reason": "already restored"}
    if running_check(int(record["appid"])):
        raise SwitchError("Cannot recover while the game is still running")
    _restore_record(record, steam=steam, home=home)
    return {"recovered": True, "reason": "restored journal"}


def activate(
    appid: int,
    mode: str,
    package: Path,
    *,
    consent: bool = False,
    home: Path | None = None,
    steam=None,
    running_check=game_is_running,
    python: str | None = None,
) -> SwitchState:
    if mode not in {"native", "original"}:
        raise SwitchError(f"Unsupported mode: {mode}")
    if not consent:
        raise SwitchError("Explicit consent is required to switch Steam launch paths")
    if running_check(appid):
        raise SwitchError("Refuse to switch while the game is already running")
    package = Path(package).expanduser().resolve()
    if not package.is_dir():
        raise SwitchError(f"Converted package does not exist: {package}")

    existing = load_journal(home=home)
    if existing and existing.get("status") == "active":
        if int(existing.get("appid")) != int(appid):
            raise SwitchError("Another FrameBench switch journal is active; recover it first")
        write_mode(appid, mode, _environ(home))
        existing["requested_mode"] = mode
        save_journal(existing, home=home)
        return SwitchState(
            appid=appid,
            requested_mode=mode,
            normal_launch_options=existing["normal_launch_options"],
            active_launch_options=existing["active_launch_options"],
            wrapper_installed=bool(existing.get("wrapper_installed")),
            method=existing.get("method") or "dual-mode-wrapper",
            package=existing.get("package") or str(package),
            status="active",
        )

    client = steam or _require_steam()
    state = client.inspect(appid)
    current = state["launch_options"]
    command = wrapper_command(package, appid, home=home, python=python)
    method = "dual-mode-wrapper"
    if looks_like_wrapper(current) and current != command:
        # Keep the already-linked conversion wrapper as the native path by
        # wrapping it: original mode skips it and execs %command%.
        method = "dual-mode-wrapper-over-existing-link"
    if current != command:
        client.set_options(appid, current, command)
        confirmed = client.inspect(appid)["launch_options"]
        if confirmed != command:
            raise SwitchError("Steam launch path was not verified; benchmark will not start")
    write_mode(appid, mode, _environ(home))
    record = {
        "kind": SWITCH_KIND,
        "wrapper_kind": WRAPPER_KIND,
        "appid": int(appid),
        "requested_mode": mode,
        "normal_launch_options": current,
        "active_launch_options": command,
        "wrapper_installed": True,
        "method": method,
        "package": str(package),
        "status": "active",
    }
    save_journal(record, home=home)
    return SwitchState(
        appid=appid,
        requested_mode=mode,
        normal_launch_options=current,
        active_launch_options=command,
        wrapper_installed=True,
        method=method,
        package=str(package),
        status="active",
    )


def restore(
    *,
    home: Path | None = None,
    steam=None,
    running_check=game_is_running,
    preserve_user_edits: bool = True,
) -> dict:
    record = load_journal(home=home)
    if record is None:
        return {"restored": False, "reason": "no journal"}
    if running_check(int(record["appid"])):
        raise SwitchError("Refuse to restore while the game is still running")
    return _restore_record(record, steam=steam, home=home, preserve_user_edits=preserve_user_edits)


def _restore_record(record: dict, *, steam=None, home: Path | None = None, preserve_user_edits: bool = True) -> dict:
    client = steam or _require_steam()
    appid = int(record["appid"])
    current = client.inspect(appid)["launch_options"]
    previous = record["normal_launch_options"]
    installed = record["active_launch_options"]
    if current == previous:
        _finish_restore(record, home=home)
        return {"restored": True, "reason": "already normal"}
    if preserve_user_edits and current != installed:
        raise SwitchError("Steam settings were edited after switching; restore will not overwrite them")
    client.set_options(appid, current, previous)
    confirmed = client.inspect(appid)["launch_options"]
    if confirmed != previous:
        raise SwitchError("Steam launch restoration was not verified")
    _finish_restore(record, home=home)
    return {"restored": True, "reason": "restored normal launch options"}


def _finish_restore(record: dict, *, home: Path | None = None) -> None:
    write_mode(record["appid"], "native" if looks_like_wrapper(record["normal_launch_options"]) else "original", _environ(home))
    record = dict(record)
    record["status"] = "restored"
    save_journal(record, home=home)
    clear_journal(home=home)


def _environ(home: Path | None):
    env = os.environ.copy()
    if home is not None:
        env["FRAMEBENCH_STATE"] = str(paths.state_root(home))
    return env


def _require_steam():
    from framebench import steam_client

    return steam_client
