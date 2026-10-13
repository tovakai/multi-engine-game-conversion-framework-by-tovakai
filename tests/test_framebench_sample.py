from framebench.fixtures import simulated_sysfs
from framebench.sample import Sampler
from framebench.sensors import discover


def test_sampler_keeps_rails_distinct(tmp_path):
    found = discover(simulated_sysfs(tmp_path / "sys"))
    clock = {"t": 100.0}

    def now():
        clock["t"] += 1.0
        return clock["t"]

    sampler = Sampler(found, clock=now)
    first = sampler.take()
    second = sampler.take()
    assert first.system_w == 6.2
    assert first.cpu_w != first.system_w
    assert first.gpu_w == 1.4
    assert first.battery_w == 6.8
    assert first.rails_w["vph"] == first.system_w
    metrics = sampler.summarize(comparable_battery=True, capacity_wh=21.0, capacity_source="measured_energy_full")
    assert metrics.system_energy.watt_hours > 0
    assert metrics.battery_energy.watt_hours > 0
    assert metrics.endurance.capacity_source == "measured_energy_full"
    assert second.t > first.t


def test_charging_samples_excluded_from_battery_energy(tmp_path):
    found = discover(simulated_sysfs(tmp_path / "sys", charging=True))
    sampler = Sampler(found, clock=lambda: 1.0)
    sampler.take()
    metrics = sampler.summarize(comparable_battery=False, capacity_wh=21.0, capacity_source="measured_energy_full")
    assert metrics.comparable_battery is False
    assert any("Charging" in note for note in metrics.notes)
