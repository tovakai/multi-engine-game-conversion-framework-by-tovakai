# FrameBench

Companion benchmark for **performance and battery efficiency** of the same Steam
game running as a native Linux AArch64 conversion versus the original Steam
entry through FEX or Proton.

FrameBench is not the converter. It lives in the `framebench` package and is
developed on `feature/framebench` so it cannot destabilize the v0.1.1.0
installer work. It reuses the consent-gated Steam launch-option pattern from
`experiments/sts2-steamworks/steam_entry.py` and is designed to coordinate with
PR #51's automatic Steam linking without introducing a second conflicting
manager.

## Status of evidence

| Kind | What it is |
| --- | --- |
| **Simulated tests** | pytest builds fake `sysfs`, ELF processes and a fake Steam client. These prove math, discovery, switching and reports. They are **not** headset measurements. |
| **Hardware observations** | Timestamped samples collected on a Steam Frame. None are checked in with this branch. HTML reports label the distinction. |

## What it measures

Read-only Linux interfaces, discovered by **name and label**, never by unstable
hwmon indices:

- `/sys/class/hwmon/` MAX34417 channels: `vph` (total-system), `gfx` (GPU), `apc*` (CPU clusters)
- `/sys/class/power_supply/` MAX1720x battery current, voltage, capacity
- Optional SteamVR compositor FPS if a log is present

Energy is the trapezoidal integral of timestamped watts. Battery percentage
deltas are not used as energy. Valve's nominal pack is **21.6 Wh**; measured
usable capacity is preferred and every endurance figure is labeled as an
estimate, never a full-discharge measurement.

The three power families stay distinct:

1. Battery-side discharge
2. Total-system `vph` hardware power
3. CPU/GPU component rails

They are never summed together.

No privileged writes. Charging configuration is not changed.

## Switching

Preferred path: a dual-mode wrapper installed as the Steam launch option:

```text
python dual_mode_launch.py --package /path/to/converted --appid 413150 -- %command%
```

- **Native:** keep `steam-launch-wrapper` + `reaper`, replace FEX/Proton + game with the converted `launch.sh`
- **Original:** exec the expanded `%command%` unchanged

A journal records the user's normal options. Restoration refuses to overwrite a
later user edit. Crash recovery replays the journal. Switching is refused while
the game is running. Original Steam game files are never edited.

If the wrapper cannot reproduce the original chain, FrameBench falls back to the
same live `SteamClient.Apps.SetAppLaunchOptions` integration used by STS2.

## GUI and CLI

`framebench gui` is the Frame session UI: game picker, native/original, start/stop,
live power, elapsed time, architecture verification, comparison, open HTML report.

`framebench` remains for debugging and automation.

## Reference title

Stardew Valley, Steam AppID **413150**:

- Original: Linux x86 through FEX
- Native: MonoFrame Linux AArch64 .NET

Both launch through the original Steam entry. Compare only after both modes are
verified. Protocol: [framebench-protocol.md](framebench-protocol.md).
