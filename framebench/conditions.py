"""Capture recommended benchmark conditions. Read-only; never changes charging or power policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
import re

from framebench.sensors import BatteryReading, SensorMap, externally_powered


RECOMMENDATIONS = (
    "Battery-powered, unplugged testing.",
    "Same headset brightness.",
    "Same refresh rate and FPS cap.",
    "Same SteamOS performance/power profile.",
    "Same scene and game settings.",
    "Same headset tracking, passthrough and Wi-Fi conditions.",
    "Similar battery charge and thermal conditions.",
    "Warm-up before measurements.",
    "Repeated alternating native/FEX runs.",
)


@dataclass
class Conditions:
    unplugged: bool
    externally_powered: bool
    charging: bool
    battery_pct: int | None
    battery_temp_c: float | None
    refresh_hz: float | None
    brightness: str | None
    performance_profile: str | None
    wifi: str | None
    display_active: bool | None
    thermal_c: dict[str, float]
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommendations: tuple[str, ...] = RECOMMENDATIONS

    def as_dict(self) -> dict:
        return {
            "unplugged": self.unplugged,
            "externally_powered": self.externally_powered,
            "charging": self.charging,
            "battery_pct": self.battery_pct,
            "battery_temp_c": self.battery_temp_c,
            "refresh_hz": self.refresh_hz,
            "brightness": self.brightness,
            "performance_profile": self.performance_profile,
            "wifi": self.wifi,
            "display_active": self.display_active,
            "thermal_c": dict(self.thermal_c),
            "notes": list(self.notes),
            "warnings": list(self.warnings),
            "recommendations": list(self.recommendations),
        }


def snapshot(
    sensors: SensorMap,
    *,
    battery: BatteryReading | None = None,
    sys_root: Path | str | None = None,
) -> Conditions:
    root = Path(sys_root) if sys_root is not None else sensors.sys_root
    reading = battery if battery is not None else (sensors.battery.read() if sensors.battery else None)
    powered = externally_powered(sensors, reading)
    charging = bool(reading.charging) if reading else powered
    warnings: list[str] = []
    notes: list[str] = []
    if powered or charging:
        warnings.append(
            "Headset is charging or externally powered. Battery discharge figures "
            "must not be compared with unplugged runs."
        )
        notes.append("Run labeled externally powered / charging.")
    display_active, refresh = _display_state(root)
    if display_active is False:
        warnings.append("Display appears off or disconnected. Power figures will not represent worn-headset gameplay.")
    thermal = _thermals(root)
    wifi = _wifi(root)
    profile = os.environ.get("STEAMOS_POWER_PROFILE") or os.environ.get("GAMESCOPE_POWER_PROFILE")
    brightness = _brightness(root)
    return Conditions(
        unplugged=not powered and not charging,
        externally_powered=powered,
        charging=charging,
        battery_pct=None if reading is None else reading.capacity_pct,
        battery_temp_c=None if reading is None else reading.temperature_c,
        refresh_hz=refresh,
        brightness=brightness,
        performance_profile=profile,
        wifi=wifi,
        display_active=display_active,
        thermal_c=thermal,
        notes=notes,
        warnings=warnings,
    )


def drift_warnings(start: Conditions, current: Conditions) -> list[str]:
    warnings: list[str] = []
    if start.unplugged != current.unplugged or start.charging != current.charging:
        warnings.append("Power/charging state changed during the benchmark.")
    if start.display_active is True and current.display_active is False:
        warnings.append("Display turned off or the headset entered a sleep-like state during the benchmark.")
    if start.refresh_hz and current.refresh_hz and abs(start.refresh_hz - current.refresh_hz) > 1:
        warnings.append(f"Refresh rate changed from {start.refresh_hz:g} Hz to {current.refresh_hz:g} Hz.")
    if start.performance_profile and current.performance_profile and start.performance_profile != current.performance_profile:
        warnings.append("SteamOS performance/power profile changed during the benchmark.")
    if start.battery_pct is not None and current.battery_pct is not None and current.battery_pct - start.battery_pct >= 2:
        warnings.append("Battery percentage rose during the run; charger attachment is likely.")
    return warnings


def _display_state(root: Path) -> tuple[bool | None, float | None]:
    drm = root / "sys" / "class" / "drm"
    if not drm.is_dir():
        return None, None
    active = None
    refresh = None
    for node in sorted(drm.glob("card*-*")):
        enabled = _text(node / "enabled")
        status = _text(node / "status")
        if enabled:
            if enabled.strip() == "enabled":
                active = True
            elif enabled.strip() == "disabled" and active is not True:
                active = False
        if status and status.strip() == "disconnected" and active is not True:
            active = False
        modes = _text(node / "modes")
        if modes:
            match = re.search(r"(\d+(?:\.\d+)?)Hz", modes.splitlines()[0], re.I)
            if match:
                try:
                    refresh = float(match.group(1))
                except ValueError:
                    pass
        dpms = _text(node / "dpms")
        if dpms and dpms.strip().casefold() in {"off", "suspend", "standby"}:
            active = False
    return active, refresh


def _thermals(root: Path) -> dict[str, float]:
    values: dict[str, float] = {}
    thermal = root / "sys" / "class" / "thermal"
    if not thermal.is_dir():
        return values
    wanted = ("cpu", "gpuss", "max1720x", "ddr")
    for zone in sorted(thermal.glob("thermal_zone*")):
        kind = _text(zone / "type") or zone.name
        if not any(token in kind.casefold() for token in wanted):
            continue
        raw = _text(zone / "temp")
        if not raw:
            continue
        try:
            values[kind.strip()] = int(raw.split()[0]) / 1000.0
        except ValueError:
            continue
    return values


def _wifi(root: Path) -> str | None:
    wireless = root / "proc" / "net" / "wireless"
    text = _text(wireless)
    if not text:
        return None
    for line in text.splitlines()[2:]:
        if ":" in line:
            return line.split(":", 1)[0].strip()
    return None


def _brightness(root: Path) -> str | None:
    backlight = root / "sys" / "class" / "backlight"
    if not backlight.is_dir():
        return None
    for node in sorted(backlight.iterdir()):
        current = _text(node / "brightness")
        maximum = _text(node / "max_brightness")
        if current and maximum:
            return f"{current.strip()}/{maximum.strip()}"
    return None


def _text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
