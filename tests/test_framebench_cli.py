import json

from framebench import cli
from framebench.fixtures import converted_package, simulated_sysfs


def test_detect_sensors_json(tmp_path, capsys):
    root = simulated_sysfs(tmp_path / "sys")
    assert cli.main(["detect-sensors", "--sys-root", str(root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert any(channel["label"] == "vph" for channel in payload["channels"])
    assert payload["hardware_observed"] is False


def test_protocol_print_and_report_cli(tmp_path, capsys):
    assert cli.main(["protocol", "stardew"]) == 0
    assert "413150" in capsys.readouterr().out
    package = converted_package(tmp_path / "pkg")
    native = {
        "id": "n", "schema": "framebench.run/v1", "appid": 413150, "name": "Stardew Valley",
        "mode": "native", "simulated": True, "hardware_observed": False,
        "verification": {"matched": True},
        "metrics": {
            "comparable_battery": True,
            "system_power": {"mean": 5.0, "median": 5.0, "peak": 6.0},
            "battery_discharge": {"mean": 5.5},
            "battery_energy": {"watt_hours": 0.2},
            "energy_per_minute_battery_wh": 0.1,
            "endurance": {"hours": 4.0, "label": "estimate"},
            "cpu_power": {}, "gpu_power": {}, "fps": {}, "frame_ms": {}, "cpu_pct": {}, "rss_mib": {},
        },
        "warnings": [],
    }
    original = json.loads(json.dumps(native))
    original.update({"id": "o", "mode": "original"})
    original["metrics"]["endurance"] = {"hours": 2.0, "label": "estimate"}
    original["metrics"]["system_power"] = {"mean": 8.0, "median": 8.0, "peak": 9.0}
    left = tmp_path / "n.json"
    right = tmp_path / "o.json"
    left.write_text(json.dumps(native), encoding="utf-8")
    right.write_text(json.dumps(original), encoding="utf-8")
    html = tmp_path / "out.html"
    assert cli.main(["report", str(left), str(right), "-o", str(html)]) == 0
    assert "SIMULATED" in html.read_text(encoding="utf-8")
    assert package.is_dir()


def test_gui_live_readout_uses_simulated_sysfs(tmp_path):
    from framebench.gui import live_readout

    root = simulated_sysfs(tmp_path / "sys")
    data = live_readout(root)
    assert data["system_w"] == 6.2
    assert data["charging"] is False
