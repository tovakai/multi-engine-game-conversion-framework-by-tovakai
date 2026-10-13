"""Power, energy and endurance statistics. Estimates are never claimed as full-discharge measurements."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import statistics

from framebench import NOMINAL_BATTERY_WH


@dataclass(frozen=True)
class SeriesStats:
    count: int
    mean: float | None
    median: float | None
    peak: float | None
    minimum: float | None
    stdev: float | None
    p95: float | None

    def as_dict(self) -> dict:
        return {
            "count": self.count,
            "mean": self.mean,
            "median": self.median,
            "peak": self.peak,
            "minimum": self.minimum,
            "stdev": self.stdev,
            "p95": self.p95,
        }


@dataclass(frozen=True)
class EnergyIntegral:
    watt_hours: float
    duration_s: float
    gap_count: int
    gap_seconds: float
    sample_count: int
    method: str = "trapezoidal_timestamped_power"

    def as_dict(self) -> dict:
        return {
            "watt_hours": self.watt_hours,
            "duration_s": self.duration_s,
            "gap_count": self.gap_count,
            "gap_seconds": self.gap_seconds,
            "sample_count": self.sample_count,
            "method": self.method,
        }


@dataclass(frozen=True)
class EnduranceEstimate:
    hours: float | None
    minutes: float | None
    capacity_wh: float
    capacity_source: str
    mean_discharge_w: float | None
    low_hours: float | None
    high_hours: float | None
    label: str
    measured_full_discharge: bool = False

    def as_dict(self) -> dict:
        return {
            "hours": self.hours,
            "minutes": self.minutes,
            "capacity_wh": self.capacity_wh,
            "capacity_source": self.capacity_source,
            "mean_discharge_w": self.mean_discharge_w,
            "low_hours": self.low_hours,
            "high_hours": self.high_hours,
            "label": self.label,
            "measured_full_discharge": False,
        }


@dataclass
class RunMetrics:
    system_power: SeriesStats
    battery_discharge: SeriesStats
    cpu_power: SeriesStats
    gpu_power: SeriesStats
    fps: SeriesStats
    frame_ms: SeriesStats
    cpu_pct: SeriesStats
    rss_mib: SeriesStats
    system_energy: EnergyIntegral
    battery_energy: EnergyIntegral
    energy_per_minute_system_wh: float | None
    energy_per_minute_battery_wh: float | None
    endurance: EnduranceEstimate
    comparable_battery: bool
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "system_power": self.system_power.as_dict(),
            "battery_discharge": self.battery_discharge.as_dict(),
            "cpu_power": self.cpu_power.as_dict(),
            "gpu_power": self.gpu_power.as_dict(),
            "fps": self.fps.as_dict(),
            "frame_ms": self.frame_ms.as_dict(),
            "cpu_pct": self.cpu_pct.as_dict(),
            "rss_mib": self.rss_mib.as_dict(),
            "system_energy": self.system_energy.as_dict(),
            "battery_energy": self.battery_energy.as_dict(),
            "energy_per_minute_system_wh": self.energy_per_minute_system_wh,
            "energy_per_minute_battery_wh": self.energy_per_minute_battery_wh,
            "endurance": self.endurance.as_dict(),
            "comparable_battery": self.comparable_battery,
            "notes": list(self.notes),
        }


def summarize(values: list[float]) -> SeriesStats:
    clean = [float(v) for v in values if v is not None and math.isfinite(v)]
    if not clean:
        return SeriesStats(0, None, None, None, None, None, None)
    clean.sort()
    stdev = statistics.pstdev(clean) if len(clean) > 1 else 0.0
    index = min(len(clean) - 1, max(0, math.ceil(0.95 * len(clean)) - 1))
    return SeriesStats(
        count=len(clean),
        mean=statistics.fmean(clean),
        median=statistics.median(clean),
        peak=clean[-1],
        minimum=clean[0],
        stdev=stdev,
        p95=clean[index],
    )


def integrate_energy_wh(
    times: list[float],
    watts: list[float | None],
    *,
    max_gap_s: float = 5.0,
) -> EnergyIntegral:
    """Trapezoidal integration of timestamped power. Large gaps are excluded, not interpolated."""

    energy = 0.0
    duration = 0.0
    gaps = 0
    gap_seconds = 0.0
    used = 0
    previous: tuple[float, float] | None = None
    for time_s, power in zip(times, watts):
        if power is None or not math.isfinite(power) or power < 0:
            previous = None
            continue
        if previous is None:
            previous = (time_s, power)
            used += 1
            continue
        dt = time_s - previous[0]
        if dt <= 0:
            previous = (time_s, power)
            continue
        if dt > max_gap_s:
            gaps += 1
            gap_seconds += dt
            previous = (time_s, power)
            used += 1
            continue
        energy += ((previous[1] + power) / 2.0) * (dt / 3600.0)
        duration += dt
        previous = (time_s, power)
        used += 1
    return EnergyIntegral(energy, duration, gaps, gap_seconds, used)


def energy_per_minute(energy: EnergyIntegral) -> float | None:
    if energy.duration_s <= 0:
        return None
    return energy.watt_hours / (energy.duration_s / 60.0)


def estimate_endurance(
    mean_discharge_w: float | None,
    *,
    capacity_wh: float | None,
    capacity_source: str,
    stdev_w: float | None = None,
) -> EnduranceEstimate:
    capacity = float(capacity_wh) if capacity_wh and capacity_wh > 0 else NOMINAL_BATTERY_WH
    source = capacity_source if capacity_wh and capacity_wh > 0 else "nominal_valve_21_6wh"
    if source == "nominal_valve_21_6wh":
        label = (
            f"Estimated from Valve's nominal {NOMINAL_BATTERY_WH:g} Wh capacity; "
            "not a measured full-discharge result."
        )
    elif source.startswith("measured"):
        label = (
            f"Estimated from measured usable capacity {capacity:.2f} Wh; "
            "not a measured full-discharge result."
        )
    else:
        label = (
            f"Estimated from {source.replace('_', ' ')} {capacity:.2f} Wh; "
            "not a measured full-discharge result."
        )
    if mean_discharge_w is None or mean_discharge_w <= 0:
        return EnduranceEstimate(None, None, capacity, source, mean_discharge_w, None, None, label)
    hours = capacity / mean_discharge_w
    low = high = None
    if stdev_w and stdev_w > 0:
        high_w = mean_discharge_w + stdev_w
        low_w = max(mean_discharge_w - stdev_w, 1e-6)
        low = capacity / high_w
        high = capacity / low_w
    return EnduranceEstimate(hours, hours * 60.0, capacity, source, mean_discharge_w, low, high, label)


def relative_improvement(native_hours: float | None, original_hours: float | None) -> dict:
    if native_hours is None or original_hours is None or original_hours <= 0:
        return {
            "ratio": None,
            "percent": None,
            "label": "Insufficient validated endurance estimates for a native-versus-original comparison.",
        }
    ratio = native_hours / original_hours
    percent = (ratio - 1.0) * 100.0
    direction = "longer" if percent >= 0 else "shorter"
    return {
        "ratio": ratio,
        "percent": percent,
        "label": (
            f"Estimated native battery life is {abs(percent):.1f}% {direction} than the emulated run "
            f"({native_hours:.2f} h vs {original_hours:.2f} h). Projection only; not a full-discharge measurement."
        ),
    }
