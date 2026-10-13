# FRAMEBENCH_SENSORS.md

**Script:** `framebench/sensors.py`

## Purpose

Read-only MAX34417 / MAX1720x discovery by name and label. No sysfs writes.

## Public API

- `discover(sys_root)` — injectable root for simulated tests
- `classify_label`, `sum_role`, `externally_powered`
- `PowerChannel.read_watts()`, `BatterySensor.read()`
