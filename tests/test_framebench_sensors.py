from pathlib import Path

from framebench.fixtures import simulated_sysfs
from framebench.sensors import classify_label, discover, externally_powered, sum_role


def test_discovery_uses_labels_not_hwmon_indices(tmp_path):
    root = simulated_sysfs(tmp_path / "sysroot")
    found = discover(root)
    labels = {channel.label: channel.role for channel in found.channels}
    assert labels["vph"] == "system"
    assert labels["gfx"] == "gpu"
    assert labels["apc0"] == "cpu"
    assert "slg4ax46073v" not in {channel.device for channel in found.channels}
    assert found.battery is not None
    reading = found.battery.read()
    assert reading.charging is False
    assert abs(reading.discharge_w - 6.8) < 1e-6
    assert reading.usable_capacity_wh == 21.0
    assert reading.capacity_source == "measured_energy_full"
    assert found.system[0].read_watts() == 6.2
    assert abs(sum_role(found.channels, "cpu") - 1.57) < 1e-6
    assert sum_role(found.channels, "gpu") == 1.4


def test_charging_run_is_labeled_and_not_treated_as_discharge(tmp_path):
    root = simulated_sysfs(tmp_path / "sysroot", charging=True)
    found = discover(root)
    reading = found.battery.read()
    assert reading.charging is True
    assert reading.discharge_w == 0.0
    assert externally_powered(found, reading) is True


def test_missing_sensors_are_warnings_not_crashes(tmp_path):
    found = discover(tmp_path / "empty")
    assert found.channels == []
    assert found.battery is None
    assert found.warnings


def test_label_roles_never_confuse_component_with_system():
    assert classify_label("vph") == "system"
    assert classify_label("gfx") == "gpu"
    assert classify_label("apc2") == "cpu"
    assert classify_label("nsp1") == "npu"
    assert classify_label("mystery") == "other"
