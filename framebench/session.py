"""Orchestrate a single FrameBench run: switch, launch, verify, sample, restore."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json
import time
import uuid

from framebench import SCHEMA, STARDEW_APPID
from framebench import conditions as conditions_mod
from framebench import metrics as metrics_mod
from framebench import paths
from framebench import process as process_mod
from framebench import sample as sample_mod
from framebench import sensors as sensors_mod
from framebench import switch as switch_mod


class SessionError(RuntimeError):
    pass


@dataclass
class RunRecord:
    id: str
    schema: str
    appid: int
    name: str
    mode: str
    package: str
    started_utc: str
    ended_utc: str | None
    warmup_s: float
    duration_s: float
    simulated: bool
    hardware_observed: bool
    conditions: dict
    verification: dict
    switch: dict
    sensors: dict
    samples: list[dict]
    metrics: dict
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "schema": self.schema,
            "appid": self.appid,
            "name": self.name,
            "mode": self.mode,
            "package": self.package,
            "started_utc": self.started_utc,
            "ended_utc": self.ended_utc,
            "warmup_s": self.warmup_s,
            "duration_s": self.duration_s,
            "simulated": self.simulated,
            "hardware_observed": self.hardware_observed,
            "conditions": self.conditions,
            "verification": self.verification,
            "switch": self.switch,
            "sensors": self.sensors,
            "samples": list(self.samples),
            "metrics": self.metrics,
            "warnings": list(self.warnings),
            "notes": list(self.notes),
        }


def save_run(record: RunRecord, *, home: Path | None = None) -> Path:
    directory = paths.runs_dir(home=home)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record.id}.json"
    path.write_text(json.dumps(record.as_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def load_run(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA:
        raise SessionError(f"Unsupported run schema in {path}")
    return data


class Session:
    def __init__(
        self,
        appid: int,
        mode: str,
        package: Path,
        *,
        name: str = "",
        interval_s: float = 1.0,
        warmup_s: float = 15.0,
        duration_s: float = 180.0,
        consent: bool = False,
        home: Path | None = None,
        sys_root: Path | str | None = None,
        steam=None,
        launch=None,
        running_check=None,
        find_processes=None,
        clock=time.time,
        sleep=time.sleep,
        simulated: bool = False,
    ) -> None:
        if mode not in {"native", "original"}:
            raise SessionError(f"Unsupported mode: {mode}")
        self.appid = int(appid)
        self.mode = mode
        self.package = Path(package)
        self.name = name or f"App {appid}"
        self.interval_s = interval_s
        self.warmup_s = warmup_s
        self.duration_s = duration_s
        self.consent = consent
        self.home = home
        self.sys_root = Path(sys_root) if sys_root is not None else Path("/")
        self.steam = steam
        self.launch = launch
        self.running_check = running_check or (lambda appid: process_mod.game_is_running(appid))
        self.find_processes = find_processes or (lambda appid: process_mod.find_game_processes(appid))
        self.clock = clock
        self.sleep = sleep
        self.simulated = simulated
        self._stop = False
        self.sensors = sensors_mod.discover(self.sys_root)
        self.sampler: sample_mod.Sampler | None = None
        self.record: RunRecord | None = None

    def request_stop(self) -> None:
        self._stop = True

    def run(self, *, collect: bool = True) -> RunRecord:
        warnings: list[str] = []
        notes: list[str] = list(self.sensors.warnings)
        battery = self.sensors.battery.read() if self.sensors.battery else None
        start_conditions = conditions_mod.snapshot(self.sensors, battery=battery, sys_root=self.sys_root)
        warnings.extend(start_conditions.warnings)
        comparable = start_conditions.unplugged and not start_conditions.charging
        switch_state = None
        verification = process_mod.Verification(self.mode, False, "not started")
        started = datetime.now(timezone.utc).isoformat()
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        meter = process_mod.CpuMeter(self.sys_root / "proc" if (self.sys_root / "proc").is_dir() else "/proc")

        try:
            switch_state = switch_mod.activate(
                self.appid,
                self.mode,
                self.package,
                consent=self.consent,
                home=self.home,
                steam=self.steam,
                running_check=self.running_check,
            )
            if self.launch:
                self.launch(self.appid)
            elif self.steam is not None and hasattr(self.steam, "launch_game"):
                self.steam.launch_game(self.appid)
            else:
                from framebench import steam_client

                steam_client.launch_game(self.appid)
            verification = self._wait_for_verified()
            if not verification.matched:
                raise SessionError(
                    "Execution architecture does not match the requested mode. "
                    + verification.reason
                    + " Benchmark data was not collected."
                )
            if collect:
                self.sampler = sample_mod.Sampler(
                    self.sensors,
                    clock=self.clock,
                    process_reader=lambda: self._process_sample(meter),
                    fps_reader=self._fps_sample,
                    condition_reader=lambda: {
                        "warnings": conditions_mod.drift_warnings(
                            start_conditions,
                            conditions_mod.snapshot(self.sensors, sys_root=self.sys_root),
                        )
                    },
                )
                deadline_warmup = self.clock() + self.warmup_s
                while self.clock() < deadline_warmup and not self._stop:
                    self.sleep(min(self.interval_s, 1.0))
                notes.append(f"Warm-up {self.warmup_s:g}s completed before scored samples.")
                deadline = self.clock() + self.duration_s
                while self.clock() < deadline and not self._stop:
                    self.sampler.take()
                    self.sleep(self.interval_s)
        finally:
            try:
                switch_mod.restore(home=self.home, steam=self.steam, running_check=lambda _appid: False)
            except switch_mod.SwitchError as exc:
                warnings.append(f"Automatic restoration failed: {exc}")

        end_conditions = conditions_mod.snapshot(self.sensors, sys_root=self.sys_root)
        warnings.extend(conditions_mod.drift_warnings(start_conditions, end_conditions))
        capacity_wh = battery.usable_capacity_wh if battery else None
        capacity_source = battery.capacity_source if battery else "nominal_valve_21_6wh"
        if self.sampler and self.sampler.samples:
            run_metrics = self.sampler.summarize(
                comparable_battery=comparable,
                capacity_wh=capacity_wh,
                capacity_source=capacity_source,
            )
            samples = [item.as_dict() for item in self.sampler.samples]
            warnings.extend(run_metrics.notes)
        else:
            run_metrics = _empty_metrics(comparable, capacity_wh, capacity_source)
            samples = []
        self.record = RunRecord(
            id=run_id,
            schema=SCHEMA,
            appid=self.appid,
            name=self.name,
            mode=self.mode,
            package=str(self.package),
            started_utc=started,
            ended_utc=datetime.now(timezone.utc).isoformat(),
            warmup_s=self.warmup_s,
            duration_s=self.duration_s,
            simulated=self.simulated,
            hardware_observed=self.sys_root == Path("/") and not self.simulated,
            conditions=start_conditions.as_dict(),
            verification=verification.as_dict(),
            switch=switch_state.as_dict() if switch_state else {},
            sensors=self.sensors.as_dict(),
            samples=samples,
            metrics=run_metrics.as_dict(),
            warnings=list(dict.fromkeys(warnings)),
            notes=notes,
        )
        save_run(self.record, home=self.home)
        return self.record

    def _wait_for_verified(self, *, attempts: int = 30) -> process_mod.Verification:
        last = process_mod.Verification(self.mode, False, "Game process did not appear.")
        for _ in range(attempts):
            processes = self.find_processes(self.appid)
            last = process_mod.verify_mode(self.mode, processes)
            if last.matched:
                return last
            if processes and not last.matched:
                return last
            self.sleep(0.2)
        return last

    def _process_sample(self, meter: process_mod.CpuMeter) -> dict:
        processes = self.find_processes(self.appid)
        pid = processes[0].pid if processes else None
        reading = meter.read(pid)
        if processes and processes[0].rss_bytes and not reading.get("rss_bytes"):
            reading["rss_bytes"] = processes[0].rss_bytes
        return reading

    def _fps_sample(self) -> dict:
        # Best-effort: SteamVR compositor summaries are end-of-session only.
        # Live FrameBridge lines apply to Quest/Lepton titles, not Stardew.
        log = Path.home() if self.home is None else Path(self.home)
        candidates = [
            log / ".local" / "share" / "Steam" / "logs" / "vrcompositor.txt",
            Path("/tmp/framebench-fps"),
        ]
        for path in candidates:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in reversed(text.splitlines()):
                if "fps" in line.casefold():
                    parts = line.replace(",", " ").split()
                    for index, part in enumerate(parts):
                        if part.casefold() == "fps" and index:
                            try:
                                return {"fps": float(parts[index - 1])}
                            except ValueError:
                                continue
        return {}


def _empty_metrics(comparable: bool, capacity_wh, capacity_source):
    empty = metrics_mod.summarize([])
    energy = metrics_mod.integrate_energy_wh([], [])
    return metrics_mod.RunMetrics(
        system_power=empty,
        battery_discharge=empty,
        cpu_power=empty,
        gpu_power=empty,
        fps=empty,
        frame_ms=empty,
        cpu_pct=empty,
        rss_mib=empty,
        system_energy=energy,
        battery_energy=energy,
        energy_per_minute_system_wh=None,
        energy_per_minute_battery_wh=None,
        endurance=metrics_mod.estimate_endurance(None, capacity_wh=capacity_wh, capacity_source=capacity_source),
        comparable_battery=comparable,
        notes=["No scored power samples were recorded."],
    )


def run_once(
    appid: int = STARDEW_APPID,
    mode: str = "native",
    package: Path | str = "",
    **kwargs,
) -> RunRecord:
    session = Session(appid, mode, Path(package), **kwargs)
    return session.run()
