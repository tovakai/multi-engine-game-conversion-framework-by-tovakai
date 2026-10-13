# FRAMEBENCH_WRAPPER.md

**Script:** `framebench/wrapper.py`

## Purpose

Stdlib dual-mode Steam wrapper. Native launches the converted package (keeping
wrapper+reaper when recognized). Original execs `%command%`. Copied into
XDG state so Steam can invoke it without the git checkout on PYTHONPATH.
