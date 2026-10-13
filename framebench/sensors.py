"""Read-only Steam Frame power and battery discovery.

Sensors are matched by name and label, never by unstable hwmon indices.
No sysfs writes. Privileged charging controls are out of scope.

Reference (SteamOS 0.4.3 / kernel 6.18, FramePort FRAME_RUNTIME.md):
- hwmon max34417_* powerN_{label,input} in microwatts
  vph = whole-system rail; gfx = GPU; apc0/1/2 = CPU clusters; nsp1/2 = NPU
- power_supply max1720x_* current_now (µA, negative = discharge) × voltage_now (µV)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

from framebench import NOMINAL_BATTERY_WH

SYSTEM_LABELS = frozenset({"vph"})
GPU_LABELS = frozenset({"gfx", "gpu"})
CPU_LABELS = frozenset({"apc0", "apc1", "apc2", "cpu", "cpu0", "cpu1", "cpu2"})
NPU_LABELS = frozenset({"nsp1", "nsp2", "npu"})
HWMON_NAME_RE = re.compile(r"max34417", re.I)
BATTERY_NAME_RE = re.compile(r"max1720x|battery|bat", re.I)


class SensorError(RuntimeError):
    """Raised when a required read-only sensor cannot be used."""


@dataclass(frozen=True)
class PowerChannel:
    """One MAX34417 (or compatible) hwmon power channel."""

    name: str
    label: str
    role: str
    input_path: Path
    device: str

    def read_watts(self) -> float:
        return microwatts_to_watts(_read_int(self.input_path))


@dataclass(frozen=True)
class BatterySensor:
    path: Path
    name: str
    current_path: Path | None
    voltage_path: Path | None
    capacity_path: Path | None
    status_path: Path | None
    energy_now_path: Path | None
    energy_full_path: Path | None
    energy_full_design_path: Path | None
    charge_full_path: Path | None
    charge_now_path: Path | None
    time_to_empty_path: Path | None
    present_path: Path | None
    online_path: Path | None
    temp_path: Path | None

    def read(self) -> "BatteryReading":
        current_ua = _read_optional_int(self.current_path)
        voltage_uv = _read_optional_int(self.voltage_path)
        status = _read_optional_text(self.status_path)
        charging = _is_charging(status, current_ua)
        watts = None
        if current_ua is not None and voltage_uv is not None:
            # Discharge power is the product of instantaneous voltage and the
            # magnitude of a negative (or status-indicated discharging) current.
            amps = current_ua / 1_000_000.0
            volts = voltage_uv / 1_000_000.0
            if charging:
                watts = 0.0
            else:
                watts = abs(amps) * volts
        usable = _usable_capacity_wh(self, voltage_uv)
        return BatteryReading(
            name=self.name,
            path=str(self.path),
            current_a=None if current_ua is None else current_ua / 1_000_000.0,
            voltage_v=None if voltage_uv is None else voltage_uv / 1_000_000.0,
            discharge_w=watts,
            charging=charging,
            status=status,
            capacity_pct=_read_optional_int(self.capacity_path),
            energy_now_wh=_microenergy_to_wh(_read_optional_int(self.energy_now_path)),
            usable_capacity_wh=usable.wh,
            capacity_source=usable.source,
            time_to_empty_s=_read_optional_int(self.time_to_empty_path),
            present=_truthy(_read_optional_text(self.present_path), default=True),
            temperature_c=_decidegrees_to_c(_read_optional_int(self.temp_path)),
        )


@dataclass(frozen=True)
class BatteryReading:
    name: str
    path: str
    current_a: float | None
    voltage_v: float | None
    discharge_w: float | None
    charging: bool
    status: str | None
    capacity_pct: int | None
    energy_now_wh: float | None
    usable_capacity_wh: float | None
    capacity_source: str
    time_to_empty_s: int | None
    present: bool
    temperature_c: float | None


@dataclass(frozen=True)
class _Capacity:
    wh: float | None
    source: str


@dataclass
class SensorMap:
    sys_root: Path
    channels: list[PowerChannel] = field(default_factory=list)
    battery: BatterySensor | None = None
    mains: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def system(self) -> list[PowerChannel]:
        return [c for c in self.channels if c.role == "system"]

    @property
    def cpu(self) -> list[PowerChannel]:
        return [c for c in self.channels if c.role == "cpu"]

    @property
    def gpu(self) -> list[PowerChannel]:
        return [c for c in self.channels if c.role == "gpu"]

    def as_dict(self) -> dict:
        return {
            "sys_root": str(self.sys_root),
            "channels": [
                {"name": c.name, "label": c.label, "role": c.role, "device": c.device}
                for c in self.channels
            ],
            "battery": None if self.battery is None else {"name": self.battery.name, "path": str(self.battery.path)},
            "warnings": list(self.warnings),
            "hardware_observed": self.sys_root == Path("/"),
        }


def microwatts_to_watts(value: int) -> float:
    return value / 1_000_000.0


def discover(sys_root: Path | str | None = None) -> SensorMap:
    """Discover MAX34417 rails and MAX1720x battery under an optional sysfs root."""

    root = Path(sys_root) if sys_root is not None else Path("/")
    found = SensorMap(sys_root=root)
    hwmon = root / "sys" / "class" / "hwmon"
    if hwmon.is_dir():
        for node in sorted(hwmon.iterdir()):
            if not node.is_dir():
                continue
            name = _read_optional_text(node / "name") or ""
            if not HWMON_NAME_RE.search(name):
                continue
            found.channels.extend(_channels_for_hwmon(node, name))
    supply = root / "sys" / "class" / "power_supply"
    if supply.is_dir():
        for node in sorted(supply.iterdir()):
            if not node.is_dir():
                continue
            name = _read_optional_text(node / "name") or node.name
            kind = (_read_optional_text(node / "type") or "").strip().lower()
            if kind == "mains" or "ac" in name.lower() or "usb" in name.lower():
                found.mains.append(node)
            if BATTERY_NAME_RE.search(name) or kind == "battery":
                if found.battery is None or HWMON_NAME_RE.search(name) or "max1720x" in name.lower():
                    found.battery = _battery_from(node, name)
    if not found.system:
        found.warnings.append("No vph/system MAX34417 rail discovered; system power will be unavailable.")
    if found.battery is None:
        found.warnings.append("No MAX1720x/battery power_supply node discovered; battery discharge will be unavailable.")
    if not found.cpu:
        found.warnings.append("No CPU cluster power channels (apc*) discovered.")
    if not found.gpu:
        found.warnings.append("No GPU power channel (gfx) discovered.")
    return found


def classify_label(label: str) -> str:
    key = label.strip().casefold()
    if key in SYSTEM_LABELS:
        return "system"
    if key in GPU_LABELS:
        return "gpu"
    if key in CPU_LABELS:
        return "cpu"
    if key in NPU_LABELS:
        return "npu"
    return "other"


def read_channels(channels: list[PowerChannel]) -> dict[str, float]:
    """Read each channel independently. Never sum overlapping roles here."""

    values: dict[str, float] = {}
    for channel in channels:
        try:
            values[channel.label] = channel.read_watts()
        except (OSError, ValueError):
            continue
    return values


def sum_role(channels: list[PowerChannel], role: str) -> float | None:
    """Sum only same-role component rails. Do not mix with vph/system."""

    selected = [c for c in channels if c.role == role]
    if not selected:
        return None
    total = 0.0
    any_ok = False
    for channel in selected:
        try:
            total += channel.read_watts()
            any_ok = True
        except (OSError, ValueError):
            continue
    return total if any_ok else None


def externally_powered(found: SensorMap, battery: BatteryReading | None = None) -> bool:
    if battery is not None and battery.charging:
        return True
    for node in found.mains:
        online = _read_optional_text(node / "online")
        if online is not None and online.strip() in {"1", "yes", "on"}:
            return True
    if battery is not None and battery.status and battery.status.casefold() in {"charging", "full", "not charging"}:
        # "Not charging" on some gauges still means a charger is attached.
        if battery.status.casefold() != "discharging":
            return battery.status.casefold() in {"charging", "full"}
    return False


def _channels_for_hwmon(node: Path, device_name: str) -> list[PowerChannel]:
    channels: list[PowerChannel] = []
    for input_path in sorted(node.glob("power*_input")):
        match = re.fullmatch(r"power(\d+)_input", input_path.name)
        if not match:
            continue
        index = match.group(1)
        label = _read_optional_text(node / f"power{index}_label") or f"power{index}"
        channels.append(
            PowerChannel(
                name=f"{device_name}:{label}",
                label=label.strip(),
                role=classify_label(label),
                input_path=input_path,
                device=device_name,
            )
        )
    return channels


def _battery_from(node: Path, name: str) -> BatterySensor:
    def maybe(name_: str) -> Path | None:
        path = node / name_
        return path if path.is_file() else None

    return BatterySensor(
        path=node,
        name=name,
        current_path=maybe("current_now"),
        voltage_path=maybe("voltage_now"),
        capacity_path=maybe("capacity"),
        status_path=maybe("status"),
        energy_now_path=maybe("energy_now"),
        energy_full_path=maybe("energy_full"),
        energy_full_design_path=maybe("energy_full_design"),
        charge_full_path=maybe("charge_full"),
        charge_now_path=maybe("charge_now"),
        time_to_empty_path=maybe("time_to_empty_now"),
        present_path=maybe("present"),
        online_path=maybe("online"),
        temp_path=maybe("temp"),
    )


def _usable_capacity_wh(sensor: BatterySensor, voltage_uv: int | None) -> _Capacity:
    energy_full = _read_optional_int(sensor.energy_full_path)
    if energy_full is not None and energy_full > 0:
        return _Capacity(energy_full / 1_000_000.0, "measured_energy_full")
    charge_full = _read_optional_int(sensor.charge_full_path)
    if charge_full is not None and charge_full > 0 and voltage_uv:
        # µAh × µV → Wh
        return _Capacity((charge_full / 1_000_000.0) * (voltage_uv / 1_000_000.0), "measured_charge_full_x_voltage")
    energy_design = _read_optional_int(sensor.energy_full_design_path)
    if energy_design is not None and energy_design > 0:
        return _Capacity(energy_design / 1_000_000.0, "design_energy_full")
    return _Capacity(NOMINAL_BATTERY_WH, "nominal_valve_21_6wh")


def _is_charging(status: str | None, current_ua: int | None) -> bool:
    if status:
        key = status.strip().casefold()
        if key in {"charging", "full"}:
            return True
        if key == "discharging":
            return False
    # MAX1720x: negative current_now means the pack is discharging.
    if current_ua is not None:
        return current_ua > 0
    return False


def _read_int(path: Path) -> int:
    return int(_read_text(path).split()[0])


def _read_optional_int(path: Path | None) -> int | None:
    if path is None:
        return None
    try:
        return _read_int(path)
    except (OSError, ValueError, IndexError):
        return None


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _read_optional_text(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    try:
        return _read_text(path)
    except OSError:
        return None


def _microenergy_to_wh(value: int | None) -> float | None:
    if value is None:
        return None
    return value / 1_000_000.0


def _decidegrees_to_c(value: int | None) -> float | None:
    if value is None:
        return None
    # MAX1720x temp is 0.1 °C; thermal_zone temp is millidegree C.
    if abs(value) > 200:
        return value / 1000.0
    return value / 10.0


def _truthy(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip() not in {"0", "no", "off", "false"}
