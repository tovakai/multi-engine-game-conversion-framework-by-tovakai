from framebench.conditions import drift_warnings, snapshot
from framebench.fixtures import simulated_sysfs
from framebench.sensors import discover


def test_unplugged_and_charging_conditions(tmp_path):
    found = discover(simulated_sysfs(tmp_path / "ok"))
    ok = snapshot(found)
    assert ok.unplugged is True
    assert ok.charging is False
    assert ok.refresh_hz == 90.0
    assert ok.display_active is True

    charging = discover(simulated_sysfs(tmp_path / "ac", charging=True, display_on=False))
    bad = snapshot(charging)
    assert bad.externally_powered is True
    assert any("externally powered" in item for item in bad.warnings)
    assert any("Display" in item for item in bad.warnings)
    drifted = drift_warnings(ok, snapshot(charging, sys_root=tmp_path / "ac"))
    assert any("Power" in item or "Display" in item for item in drifted)
