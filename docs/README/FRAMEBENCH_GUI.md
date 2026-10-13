# FRAMEBENCH_GUI.md

**Script:** `framebench/gui.py`

## Purpose

CustomTkinter Frame session UI. Game picker, native/original, start/stop, live
power, elapsed time, verification, comparison, open HTML report. No keyboard
needed after games are discovered.

## Public API

- `live_readout(sys_root)` — used by tests without opening a window
- `FrameBenchApp`, `main()`
