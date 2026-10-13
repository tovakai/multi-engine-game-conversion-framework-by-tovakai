"""Timestamped telemetry samples and energy-aware recording loops."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
import time
from typing import Callable

from framebench import metrics as metrics_mod
from framebench.sensors import SensorMap, externally_powered, read_channels, sum_role


@dataclass
class Sample:
    t: float
    system_w: float | None
    battery_w: float | None
    battery_charging: bool
    cpu_w: float | None
    gpu_w: float | None
    npu_w: float | None
    cpu_pct: float | None
    rss_bytes: int | None
    mem_available_bytes: int | None
    fps: float | None
    frame_ms: float | None
    battery_pct: float | None
    voltage_v: float | None
    current_a: float | None
    temperature_c: float | None
    rails_w: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


class Sampler:
    def __init__(
        self,
        sensors: SensorMap,
        *,
        clock: Callable[[], float] = time.time,
        process_reader: Callable[[], dict] | None = None,
        fps_reader: Callable[[], dict] | None = None,
        condition_reader: Callable[[], dict] | None = None,
    ) -> None:
        self.sensors = sensors
        self.clock = clock
        self.process_reader = process_reader
        self.fps_reader = fps_reader
        self.condition_reader = condition_reader
        self.samples: list[Sample] = []
        self.warnings: list[str] = []
        self._last_powered: bool | None = None

    def take(self) -> Sample:
        rails = read_channels(self.sensors.channels)
        system = None
        if self.sensors.system:
            values = [rails[c.label] for c in self.sensors.system if c.label in rails]
            system = values[0] if values else None
        cpu = sum_role(self.sensors.channels, "cpu")
        gpu = sum_role(self.sensors.channels, "gpu")
        npu = sum_role(self.sensors.channels, "npu")
        battery = self.sensors.battery.read() if self.sensors.battery is not None else None
        process = self.process_reader() if self.process_reader else {}
        fps_info = self.fps_reader() if self.fps_reader else {}
        warnings: list[str] = []
        charging = bool(battery.charging) if battery else False
        powered = externally_powered(self.sensors, battery)
        if self._last_powered is None:
            self._last_powered = powered
        elif powered != self._last_powered:
            warnings.append("Power state changed during the benchmark (charger or battery status).")
            self._last_powered = powered
        if self.condition_reader:
            extra = self.condition_reader() or {}
            warnings.extend(extra.get("warnings") or [])
        fps = fps_info.get("fps")
        frame_ms = fps_info.get("frame_ms")
        if frame_ms is None and fps:
            frame_ms = 1000.0 / fps
        sample = Sample(
            t=self.clock(),
            system_w=system,
            battery_w=None if battery is None else battery.discharge_w,
            battery_charging=charging,
            cpu_w=cpu,
            gpu_w=gpu,
            npu_w=npu,
            cpu_pct=process.get("cpu_pct"),
            rss_bytes=process.get("rss_bytes"),
            mem_available_bytes=process.get("mem_available_bytes"),
            fps=fps,
            frame_ms=frame_ms,
            battery_pct=None if battery is None else battery.capacity_pct,
            voltage_v=None if battery is None else battery.voltage_v,
            current_a=None if battery is None else battery.current_a,
            temperature_c=None if battery is None else battery.temperature_c,
            rails_w=rails,
            warnings=warnings,
        )
        self.samples.append(sample)
        self.warnings.extend(warnings)
        return sample

    def summarize(self, *, comparable_battery: bool, capacity_wh: float | None, capacity_source: str) -> metrics_mod.RunMetrics:
        times = [s.t for s in self.samples]
        system = metrics_mod.summarize([s.system_w for s in self.samples if s.system_w is not None])
        battery = metrics_mod.summarize([s.battery_w for s in self.samples if s.battery_w is not None and not s.battery_charging])
        cpu = metrics_mod.summarize([s.cpu_w for s in self.samples if s.cpu_w is not None])
        gpu = metrics_mod.summarize([s.gpu_w for s in self.samples if s.gpu_w is not None])
        fps = metrics_mod.summarize([s.fps for s in self.samples if s.fps is not None])
        frame = metrics_mod.summarize([s.frame_ms for s in self.samples if s.frame_ms is not None])
        cpu_pct = metrics_mod.summarize([s.cpu_pct for s in self.samples if s.cpu_pct is not None])
        rss = metrics_mod.summarize(
            [s.rss_bytes / (1024 * 1024) for s in self.samples if s.rss_bytes]
        )
        system_energy = metrics_mod.integrate_energy_wh(times, [s.system_w for s in self.samples])
        battery_energy = metrics_mod.integrate_energy_wh(
            times,
            [None if s.battery_charging else s.battery_w for s in self.samples],
        )
        notes = list(self.warnings)
        if any(s.battery_charging for s in self.samples):
            notes.append("Charging samples were excluded from battery discharge energy.")
        endurance = metrics_mod.estimate_endurance(
            battery.mean,
            capacity_wh=capacity_wh,
            capacity_source=capacity_source,
            stdev_w=battery.stdev,
        )
        return metrics_mod.RunMetrics(
            system_power=system,
            battery_discharge=battery,
            cpu_power=cpu,
            gpu_power=gpu,
            fps=fps,
            frame_ms=frame,
            cpu_pct=cpu_pct,
            rss_mib=rss,
            system_energy=system_energy,
            battery_energy=battery_energy,
            energy_per_minute_system_wh=metrics_mod.energy_per_minute(system_energy),
            energy_per_minute_battery_wh=metrics_mod.energy_per_minute(battery_energy),
            endurance=endurance,
            comparable_battery=comparable_battery,
            notes=notes,
        )
