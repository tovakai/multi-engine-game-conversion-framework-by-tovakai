"""Reproducible Stardew Valley native-versus-FEX protocol."""

from __future__ import annotations

from pathlib import Path

from framebench import STARDEW_APPID
from framebench.compare import compare_runs
from framebench.report import write_report
from framebench.session import Session

PROTOCOL = {
    "id": "framebench-stardew-413150-v1",
    "name": "Stardew Valley native ARM64 vs original Linux x86/FEX",
    "appid": STARDEW_APPID,
    "variants": ("native", "original"),
    "scene": "Title menu idle, then the same farm/map tile if a save is loaded. Do not change in-game settings between variants.",
    "warmup_s": 20,
    "duration_s": 180,
    "interval_s": 1.0,
    "alternating": True,
    "requirements": [
        "Launch both variants through Steam AppID 413150.",
        "Verify architecture before scoring samples.",
        "Unplugged battery power.",
        "Same brightness, refresh rate, FPS cap and SteamOS profile.",
        "Same tracking, passthrough and Wi-Fi.",
        "Similar charge and thermal conditions.",
        "Restore the normal linked Steam configuration after every run.",
    ],
}


def describe() -> str:
    lines = [
        f"{PROTOCOL['name']}",
        f"Protocol {PROTOCOL['id']}  AppID {PROTOCOL['appid']}",
        "",
        f"Warm-up: {PROTOCOL['warmup_s']}s   Scored: {PROTOCOL['duration_s']}s   Interval: {PROTOCOL['interval_s']}s",
        f"Scene: {PROTOCOL['scene']}",
        "",
        "Required conditions:",
    ]
    lines.extend(f"- {item}" for item in PROTOCOL["requirements"])
    lines += [
        "",
        "Run order: native, original, native, original (alternating). Compare only verified pairs.",
        "All endurance numbers are estimates, never full-discharge measurements.",
        "Simulated fixture runs must be labeled simulated and must not be mixed with hardware runs.",
    ]
    return "\n".join(lines)


def run_pair(
    package: Path,
    *,
    home: Path | None = None,
    sys_root: Path | str | None = None,
    steam=None,
    running_check=None,
    find_processes=None,
    launch=None,
    warmup_s: float | None = None,
    duration_s: float | None = None,
    interval_s: float | None = None,
    consent: bool = False,
    simulated: bool = False,
    clock=None,
    sleep=None,
    report_path: Path | None = None,
) -> dict:
    records = []
    for mode in PROTOCOL["variants"]:
        session = Session(
            STARDEW_APPID,
            mode,
            package,
            name="Stardew Valley",
            warmup_s=PROTOCOL["warmup_s"] if warmup_s is None else warmup_s,
            duration_s=PROTOCOL["duration_s"] if duration_s is None else duration_s,
            interval_s=PROTOCOL["interval_s"] if interval_s is None else interval_s,
            consent=consent,
            home=home,
            sys_root=sys_root,
            steam=steam,
            launch=launch,
            running_check=running_check,
            find_processes=find_processes,
            simulated=simulated,
            **({} if clock is None else {"clock": clock}),
            **({} if sleep is None else {"sleep": sleep}),
        )
        records.append(session.run().as_dict())
    comparison = compare_runs(records[0], records[1])
    html = None
    if report_path is not None:
        html = str(write_report(records, Path(report_path), comparison=comparison))
    return {
        "protocol": PROTOCOL["id"],
        "simulated": simulated,
        "runs": records,
        "comparison": comparison,
        "report": html,
    }
