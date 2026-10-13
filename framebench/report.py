"""Self-contained HTML reports that put power and battery endurance first."""

from __future__ import annotations

from html import escape
from pathlib import Path
import json

from framebench.compare import compare_runs


def write_report(runs: list[dict], destination: Path, *, comparison: dict | None = None) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if comparison is None and len(runs) >= 2:
        comparison = compare_runs(runs[0], runs[1])
    destination.write_text(render_html(runs, comparison), encoding="utf-8")
    return destination


def render_html(runs: list[dict], comparison: dict | None = None) -> str:
    title = escape(str((runs[0].get("name") if runs else "FrameBench") or "FrameBench"))
    sim = any(run.get("simulated") for run in runs)
    hw = all(run.get("hardware_observed") for run in runs) if runs else False
    banner = (
        "SIMULATED FIXTURE DATA — not a Steam Frame hardware observation."
        if sim
        else (
            "Steam Frame hardware observation."
            if hw
            else "Mixed or host-local telemetry. Treat power figures as unverified off-device data."
        )
    )
    cards = "".join(_run_card(run) for run in runs)
    compare = _compare_block(comparison) if comparison else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>FrameBench — {title}</title>
<style>
:root {{
  --bg:#05070b; --panel:#101722; --panel2:#0b1119; --text:#f1e8d8; --muted:#9babb3;
  --teal:#49d3c6; --accent:#ff8452; --ok:#70d995; --warn:#ffb86c; --err:#ff667c; --border:#29485a;
}}
html,body {{ background:var(--bg); color:var(--text); font-family: Segoe UI, system-ui, sans-serif; margin:0; }}
main {{ max-width: 1100px; margin: 0 auto; padding: 28px 20px 64px; }}
h1 {{ font-size: 2rem; margin: 0 0 8px; }}
.tag {{ color: var(--teal); font-family: ui-monospace, Consolas, monospace; letter-spacing: .04em; }}
.banner {{
  margin: 16px 0 24px; padding: 12px 14px; border: 1px solid var(--border); background: var(--panel2);
  color: var(--warn); font-weight: 700;
}}
.hero {{
  display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-bottom: 24px;
}}
.hero .cell {{
  background: linear-gradient(180deg, #172232, #101722); border: 2px solid var(--teal); border-radius: 10px;
  padding: 16px 18px;
}}
.hero .label {{ color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .08em; }}
.hero .value {{ font-size: 1.8rem; font-weight: 800; color: var(--teal); margin-top: 6px; }}
.hero .sub {{ color: var(--muted); font-size: .85rem; margin-top: 8px; }}
.grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }}
.card {{ background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px; }}
.card h2 {{ margin: 0 0 10px; font-size: 1.15rem; }}
.mode {{ display:inline-block; padding: 2px 8px; border-radius: 4px; background:#172232; color: var(--accent); font-size: .8rem; }}
table {{ width:100%; border-collapse: collapse; font-size: .92rem; }}
th,td {{ text-align:left; padding: 6px 4px; border-bottom: 1px solid #1d2a36; }}
th {{ color: var(--muted); font-weight: 600; }}
.ok {{ color: var(--ok); }} .warn {{ color: var(--warn); }} .err {{ color: var(--err); }}
.fineprint {{ color: var(--muted); font-size: .82rem; margin-top: 18px; line-height: 1.45; }}
</style>
</head>
<body>
<main>
<p class="tag">FRAMEBENCH // POWER · BATTERY · NATIVE VS FEX</p>
<h1>{title} efficiency report</h1>
<div class="banner">{escape(banner)}</div>
{compare}
<div class="grid">{cards}</div>
<p class="fineprint">
Projected endurance uses timestamped power integration and a labeled battery capacity.
Valve's nominal Steam Frame pack is 21.6 Wh; measured usable capacity is preferred when the gauge exposes it.
These projections are <strong>not</strong> physically measured full-discharge results.
System power is the vph rail only. CPU/GPU rails are reported separately and are never added onto vph.
Battery discharge is independent of hardware rail power.
</p>
</main>
</body>
</html>
"""


def _compare_block(comparison: dict) -> str:
    improvement = comparison.get("battery_life_improvement") or {}
    percent = improvement.get("percent")
    percent_txt = "n/a" if percent is None else f"{percent:+.1f}%"
    native = comparison.get("native") or {}
    original = comparison.get("original") or {}
    status = "ok" if comparison.get("comparable") else "warn"
    reasons = "".join(f"<div class='{status}'>{escape(reason)}</div>" for reason in comparison.get("reasons") or [])
    if comparison.get("comparable"):
        reasons = "<div class='ok'>Both modes verified under the same protocol. Battery figures are comparable.</div>"
    return f"""
<div class="hero">
  <div class="cell">
    <div class="label">Estimated battery-life change</div>
    <div class="value">{escape(percent_txt)}</div>
    <div class="sub">{escape(improvement.get("label") or "Insufficient data.")}</div>
  </div>
  <div class="cell">
    <div class="label">Native mean system power</div>
    <div class="value">{_w(native.get("system_mean_w"))}</div>
    <div class="sub">Battery discharge {_w(native.get("battery_mean_w"))}</div>
  </div>
  <div class="cell">
    <div class="label">Original/FEX mean system power</div>
    <div class="value">{_w(original.get("system_mean_w"))}</div>
    <div class="sub">Battery discharge {_w(original.get("battery_mean_w"))}</div>
  </div>
  <div class="cell">
    <div class="label">Native energy / minute</div>
    <div class="value">{_wh(native.get("energy_per_minute_wh"))}</div>
    <div class="sub">Original {_wh(original.get("energy_per_minute_wh"))}</div>
  </div>
</div>
{reasons}
"""


def _run_card(run: dict) -> str:
    metrics = run.get("metrics") or {}
    system = metrics.get("system_power") or {}
    battery = metrics.get("battery_discharge") or {}
    cpu = metrics.get("cpu_power") or {}
    gpu = metrics.get("gpu_power") or {}
    endurance = metrics.get("endurance") or {}
    fps = metrics.get("fps") or {}
    verified = (run.get("verification") or {}).get("matched")
    mark = "ok" if verified else "err"
    origin = "SIMULATED" if run.get("simulated") else ("HARDWARE" if run.get("hardware_observed") else "HOST")
    warnings = "".join(f"<div class='warn'>{escape(item)}</div>" for item in run.get("warnings") or [])
    return f"""
<article class="card">
  <h2>{escape(str(run.get("name") or "run"))} <span class="mode">{escape(str(run.get("mode")))}</span></h2>
  <p class="{mark}">{origin} · architecture {'verified' if verified else 'NOT VERIFIED'}</p>
  <table>
    <tr><th>System power mean / median / peak</th><td>{_w(system.get("mean"))} / {_w(system.get("median"))} / {_w(system.get("peak"))}</td></tr>
    <tr><th>Battery discharge mean</th><td>{_w(battery.get("mean"))}</td></tr>
    <tr><th>Battery energy consumed</th><td>{_wh((metrics.get("battery_energy") or {}).get("watt_hours"))}</td></tr>
    <tr><th>Energy per minute</th><td>{_wh(metrics.get("energy_per_minute_battery_wh"))}</td></tr>
    <tr><th>Estimated endurance</th><td>{_hours(endurance.get("hours"))}<div class="fineprint">{escape(str(endurance.get("label") or ""))}</div></td></tr>
    <tr><th>CPU / GPU power</th><td>{_w(cpu.get("mean"))} / {_w(gpu.get("mean"))}</td></tr>
    <tr><th>FPS / frame time</th><td>{_num(fps.get("mean"), "fps")} / {_num((metrics.get("frame_ms") or {}).get("mean"), "ms")}</td></tr>
    <tr><th>CPU / memory</th><td>{_num((metrics.get("cpu_pct") or {}).get("mean"), "%")} / {_num((metrics.get("rss_mib") or {}).get("mean"), "MiB")}</td></tr>
  </table>
  {warnings}
</article>
"""


def _w(value) -> str:
    return "n/a" if value is None else f"{float(value):.2f} W"


def _wh(value) -> str:
    return "n/a" if value is None else f"{float(value):.3f} Wh"


def _hours(value) -> str:
    if value is None:
        return "n/a"
    hours = float(value)
    minutes = hours * 60.0
    return f"{hours:.2f} h ({minutes:.0f} min) · estimate"


def _num(value, unit: str) -> str:
    return "n/a" if value is None else f"{float(value):.1f} {unit}"


def comparison_json(runs: list[dict]) -> str:
    if len(runs) < 2:
        return json.dumps({"comparable": False, "reasons": ["Need two runs."]}, indent=2)
    return json.dumps(compare_runs(runs[0], runs[1]), indent=2)
