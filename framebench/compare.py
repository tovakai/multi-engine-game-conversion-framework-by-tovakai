"""Compare validated native and original runs under the same protocol."""

from __future__ import annotations

from framebench.metrics import relative_improvement


def comparable(left: dict, right: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if left.get("appid") != right.get("appid"):
        reasons.append("AppIDs differ.")
    if {left.get("mode"), right.get("mode")} != {"native", "original"}:
        reasons.append("Comparison requires one native run and one original run.")
    if not left.get("verification", {}).get("matched") or not right.get("verification", {}).get("matched"):
        reasons.append("Both execution modes must be verified before comparison.")
    if left.get("simulated") != right.get("simulated"):
        reasons.append("Do not mix simulated fixture data with hardware observations.")
    left_ok = left.get("metrics", {}).get("comparable_battery")
    right_ok = right.get("metrics", {}).get("comparable_battery")
    if not left_ok or not right_ok:
        reasons.append("One or both runs were charging/externally powered; battery figures are not comparable.")
    return not reasons, reasons


def compare_runs(left: dict, right: dict) -> dict:
    native = left if left.get("mode") == "native" else right
    original = right if native is left else left
    if native.get("mode") != "native" or original.get("mode") != "original":
        native, original = _by_mode(left, right)
    ok, reasons = comparable(native, original)
    native_end = (native.get("metrics") or {}).get("endurance") or {}
    original_end = (original.get("metrics") or {}).get("endurance") or {}
    improvement = relative_improvement(native_end.get("hours"), original_end.get("hours"))
    return {
        "comparable": ok,
        "reasons": reasons,
        "native_id": native.get("id"),
        "original_id": original.get("id"),
        "appid": native.get("appid"),
        "name": native.get("name"),
        "simulated": bool(native.get("simulated") or original.get("simulated")),
        "hardware_observed": bool(native.get("hardware_observed") and original.get("hardware_observed")),
        "battery_life_improvement": improvement,
        "native": _headline(native),
        "original": _headline(original),
        "deltas": _deltas(native, original) if ok else {},
    }


def _by_mode(left: dict, right: dict) -> tuple[dict, dict]:
    if left.get("mode") == "native":
        return left, right
    if right.get("mode") == "native":
        return right, left
    return left, right


def _headline(run: dict) -> dict:
    metrics = run.get("metrics") or {}
    system = metrics.get("system_power") or {}
    battery = metrics.get("battery_discharge") or {}
    endurance = metrics.get("endurance") or {}
    fps = metrics.get("fps") or {}
    return {
        "id": run.get("id"),
        "mode": run.get("mode"),
        "system_mean_w": system.get("mean"),
        "system_peak_w": system.get("peak"),
        "battery_mean_w": battery.get("mean"),
        "energy_wh": (metrics.get("battery_energy") or {}).get("watt_hours"),
        "energy_per_minute_wh": metrics.get("energy_per_minute_battery_wh"),
        "endurance_hours": endurance.get("hours"),
        "endurance_label": endurance.get("label"),
        "fps_mean": fps.get("mean"),
        "cpu_pct": (metrics.get("cpu_pct") or {}).get("mean"),
        "rss_mib": (metrics.get("rss_mib") or {}).get("mean"),
        "verified": bool((run.get("verification") or {}).get("matched")),
    }


def _deltas(native: dict, original: dict) -> dict:
    n = _headline(native)
    o = _headline(original)

    def delta(key: str) -> float | None:
        if n.get(key) is None or o.get(key) is None:
            return None
        return n[key] - o[key]

    return {
        "system_mean_w": delta("system_mean_w"),
        "battery_mean_w": delta("battery_mean_w"),
        "energy_per_minute_wh": delta("energy_per_minute_wh"),
        "endurance_hours": delta("endurance_hours"),
        "fps_mean": delta("fps_mean"),
    }
