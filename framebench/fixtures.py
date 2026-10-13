"""Build simulated sysfs trees and Steam stubs. These are not hardware observations."""

from __future__ import annotations

from pathlib import Path
import json

from framebench import STARDEW_APPID
from framebench.wrapper import parse_steam_chain


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")


def simulated_sysfs(root: Path, *, charging: bool = False, display_on: bool = True, vph_uw: int = 6_200_000) -> Path:
    """Create a Frame-like sysfs layout. Indices are intentionally unstable."""

    hwmon = root / "sys" / "class" / "hwmon"
    # Unstable indices on purpose: discovery must use names/labels.
    device = hwmon / "hwmon9"
    write(device / "name", "max34417_soc")
    write(device / "power1_label", "apc0")
    write(device / "power1_input", "850000")
    write(device / "power2_label", "gfx")
    write(device / "power2_input", "1400000")
    write(device / "power3_label", "vph")
    write(device / "power3_input", str(vph_uw))
    write(device / "power4_label", "apc1")
    write(device / "power4_input", "720000")
    extra = hwmon / "hwmon3"
    write(extra / "name", "slg4ax46073v")
    write(extra / "fan1_input", "8200")

    battery = root / "sys" / "class" / "power_supply" / "max1720x_bat_7-36"
    write(battery / "name", "max1720x_bat_7-36")
    write(battery / "type", "Battery")
    write(battery / "status", "Charging" if charging else "Discharging")
    write(battery / "current_now", "400000" if charging else "-850000")
    write(battery / "voltage_now", "8000000")
    write(battery / "capacity", "72")
    write(battery / "energy_now", "15500000")
    write(battery / "energy_full", "21000000")
    write(battery / "energy_full_design", "21600000")
    write(battery / "time_to_empty_now", "9800")
    write(battery / "present", "1")
    write(battery / "temp", "312")
    mains = root / "sys" / "class" / "power_supply" / "usb-mains"
    write(mains / "name", "usb")
    write(mains / "type", "Mains")
    write(mains / "online", "1" if charging else "0")

    conn = root / "sys" / "class" / "drm" / "card0-HDMI-A-1"
    write(conn / "enabled", "enabled" if display_on else "disabled")
    write(conn / "status", "connected" if display_on else "disconnected")
    write(conn / "modes", "2160x2160@90Hz")
    write(conn / "dpms", "On" if display_on else "Off")
    write(root / "sys" / "class" / "thermal" / "thermal_zone0" / "type", "cpu-0-0-0")
    write(root / "sys" / "class" / "thermal" / "thermal_zone0" / "temp", "41000")
    write(root / "sys" / "class" / "thermal" / "thermal_zone2" / "type", "gpuss-0")
    write(root / "sys" / "class" / "thermal" / "thermal_zone2" / "temp", "43000")
    write(root / "sys" / "class" / "backlight" / "panel" / "brightness", "60")
    write(root / "sys" / "class" / "backlight" / "panel" / "max_brightness", "100")
    write(root / "proc" / "stat", "cpu  100 0 40 800 0 0 0 0\ncpu0 20 0 8 160 0 0 0 0\n")
    write(root / "proc" / "meminfo", "MemAvailable:    8192000 kB\n")
    write(root / "proc" / "net" / "wireless", "Inter-| sta-|   Quality\nwlan0: 0000  50.  0  0\n")
    return root


def add_game_process(
    proc_root: Path,
    pid: int,
    *,
    appid: int = STARDEW_APPID,
    machine: str = "aarch64",
    comm: str = "dotnet",
    fex: bool = False,
    rss_kb: int = 250000,
) -> Path:
    root = proc_root / str(pid)
    root.mkdir(parents=True, exist_ok=True)
    machine_name = "x86_64" if fex or machine == "x86_64" else "aarch64"
    binary = root / ("FEXInterpreter" if fex else comm)
    _write_elf(binary, machine=machine_name)
    _write_elf(root / "exe", machine=machine_name)
    cmdline = f"{binary.name}\0Stardew Valley.dll\0"
    if fex:
        cmdline = f"/usr/bin/FEX\0--\0{binary.name}\0"
    (root / "cmdline").write_bytes(cmdline.encode())
    environ = f"SteamAppId={appid}\0SteamGameId={appid}\0STEAM_COMPAT_APP_ID={appid}\0"
    (root / "environ").write_bytes(environ.encode())
    write(root / "comm", "FEXInterpreter" if fex else comm)
    write(root / "status", f"Name:\t{comm}\nVmRSS:\t{rss_kb} kB\n")
    write(root / "stat", f"{pid} ({comm}) S 1 1 1 0 0 0 0 0 0 0 0 20 10 0 0")
    return root


def converted_package(root: Path, *, appid: int = STARDEW_APPID) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    write(root / "launch.sh", "#!/bin/sh\nexec true\n")
    write(root / "steam_appid.txt", str(appid))
    write(
        root / ".megcfbt" / "package.json",
        json.dumps(
            {
                "schema": "megcfbt.frame-build/v1",
                "name": "Stardew Valley",
                "launcher": "launch.sh",
                "architecture": "aarch64",
                "steam_app_id": str(appid),
            },
            indent=2,
        ),
    )
    write(root / "MONOFRAME-PROFILE.json", json.dumps({"profile": "stardew-steam-1.6.15-net6"}))
    return root


def steam_command(appid: int = STARDEW_APPID, *, fex: bool = True) -> list[str]:
    prefix = [
        "/home/deck/.steam/steam/ubuntu12_32/../linuxarm64/steam-launch-wrapper",
        "--oom-score-adjust",
        "1000",
        "--",
        "/home/deck/.steam/steam/ubuntu12_32/../steamrtarm64/reaper",
        "SteamLaunch",
        f"AppId={appid}",
        "--",
    ]
    if fex:
        prefix += ["/home/deck/.steam/steam/steamapps/common/FEX-Emu/fex-compat-tool", "waitforexitandrun", "--"]
    prefix.append("/home/deck/.steam/steam/steamapps/common/Stardew Valley/StardewValley")
    return prefix


def fake_steam(initial: str = ""):
    class Fake:
        def __init__(self) -> None:
            self.launch_options = initial
            self.launched: list[int] = []

        def inspect(self, appid: int) -> dict:
            return {
                "present": True,
                "installed": True,
                "setter": True,
                "launch_options": self.launch_options,
                "name": "Stardew Valley",
                "appid": appid,
            }

        def set_options(self, appid: int, expected: str, replacement: str) -> None:
            if self.launch_options != expected:
                raise RuntimeError("Steam launch settings changed; inspect again")
            self.launch_options = replacement

        def launch_game(self, appid: int) -> None:
            self.launched.append(appid)

    return Fake()


def _write_elf(path: Path, *, machine: str) -> None:
    data = bytearray(64)
    data[0:4] = b"\x7fELF"
    data[4] = 2
    data[5] = 1
    code = 183 if machine == "aarch64" else 62
    data[18:20] = int(code).to_bytes(2, "little")
    path.write_bytes(data)
    try:
        path.chmod(0o755)
    except OSError:
        pass


def clock_start(start: float = 1_000.0):
    state = {"t": start}

    def now() -> float:
        return state["t"]

    def advance(seconds: float) -> None:
        state["t"] += seconds

    now.advance = advance  # type: ignore[attr-defined]
    return now


# Keep parse_steam_chain imported for fixture tests that build authentic chains.
__all__ = [
    "simulated_sysfs",
    "add_game_process",
    "converted_package",
    "steam_command",
    "fake_steam",
    "clock_start",
    "parse_steam_chain",
    "write",
]
