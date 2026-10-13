# FRAMEBENCH_CLI.md

**Script:** `framebench/cli.py`

## Purpose

Automation and debug CLI. Subcommands: detect-sensors, list-games, start,
recover, restore, compare, report, protocol, gui.

## Flags

- `--consent` — required before Steam launch-option mutations
- `--simulated` / `--sys-root` — mark runs as fixture data, not hardware
