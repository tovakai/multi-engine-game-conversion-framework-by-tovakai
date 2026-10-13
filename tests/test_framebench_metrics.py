from framebench.metrics import (
    energy_per_minute,
    estimate_endurance,
    integrate_energy_wh,
    relative_improvement,
    summarize,
)


def test_energy_uses_timestamped_trapezoid_not_percent():
    energy = integrate_energy_wh([0.0, 60.0, 120.0], [10.0, 10.0, 10.0], max_gap_s=90.0)
    assert abs(energy.watt_hours - (10.0 * 120.0 / 3600.0)) < 1e-9
    assert energy.method == "trapezoidal_timestamped_power"
    assert energy.gap_count == 0
    assert abs(energy_per_minute(energy) - 10.0 / 60.0) < 1e-9


def test_sampling_gaps_are_excluded():
    energy = integrate_energy_wh([0.0, 1.0, 30.0, 31.0], [8.0, 8.0, 8.0, 8.0], max_gap_s=5.0)
    assert energy.gap_count == 1
    assert abs(energy.watt_hours - (8.0 * 2.0 / 3600.0)) < 1e-9


def test_endurance_is_labeled_estimate_not_full_discharge():
    stats = summarize([6.0, 7.0, 8.0])
    estimate = estimate_endurance(stats.mean, capacity_wh=21.6, capacity_source="nominal_valve_21_6wh", stdev_w=stats.stdev)
    assert estimate.measured_full_discharge is False
    assert "not a measured full-discharge" in estimate.label
    assert estimate.hours == 21.6 / 7.0
    assert estimate.low_hours is not None and estimate.high_hours is not None


def test_relative_improvement_and_missing_data():
    result = relative_improvement(4.0, 2.0)
    assert result["ratio"] == 2.0
    assert result["percent"] == 100.0
    assert relative_improvement(None, 2.0)["percent"] is None
