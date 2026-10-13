# FRAMEBENCH_PROCESS.md

**Script:** `framebench/process.py`

## Purpose

Find Steam-owned processes, read ELF machine, detect FEX/Proton, verify the
requested mode before scoring. `CpuMeter` provides /proc CPU and RSS deltas.
