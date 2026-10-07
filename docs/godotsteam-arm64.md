# Experimental GodotSteam ARM64 runtime recipe

This is an **opt-in** compatibility path, proven with approximately 30 minutes
of gameplay in Brotato on Steam Frame. It is not a generic custom-Godot
converter and does not automatically build Godot on Windows.

## Tested runtime components

- Godot 3.7-dev1 source commit `a117d512b00f1646db174e703e7e888519b64608`
- CanvasItem 3.x fix from Godot PR #123099
- GodotSteam `v3.30`, built as a Godot module
- Steamworks **1.62 headers**, not Proton's vendored headers
- Native Linux AArch64 `libsteam_api.so` from the Steam Frame
- SCons: `scons -j6 platform=x11 target=release tools=no arch=arm64 lto=none`

The game fingerprint originally reported GodotSteam 3.31. Substituting 3.30
preserves enough of the game-facing API for this particular tested game,
but other titles may depend on newer methods. The PCK version alone is
insufficient to establish compatibility.

## Packaging the proven runtime

On the ARM64 Linux machine where the runtime has already been built:

```bash
bash scripts/package-godotsteam-arm64-runtime.sh \
    /path/to/patched/godot \
    /opt/steamvr/bin/linuxarm64/libsteam_api.so \
    /path/to/godotsteam-arm64-runtime
```

The script checks the pinned source commit, ARM64 ELF architectures,
Steam interface symbols, and GodotSteam markers. It writes a runtime bundle
containing `godot.arm64`, `libsteam_api.so`, and `runtime.json`.
It does **not** certify that the CanvasItem patch is present or that the
GodotSteam module exactly matches v3.30. Review your source tree first.

Copy this runtime bundle to the computer running the converter. For a
Windows GUI session, set `TOVAKAI_GODOTSTEAM_ARM64_RUNTIME` to the
directory containing these three files before starting the application.
On Linux:

```bash
export TOVAKAI_GODOTSTEAM_ARM64_RUNTIME=/path/to/godotsteam-arm64-runtime
multi-engine-game-conversion-framework-by-tovakai build /path/to/game
```

For a custom Godot export that includes GodotSteam, the converter will use
this **explicitly configured** runtime. Other custom builds continue to
require an explicit matching runtime. The converter copies game-owned
`steam_data.json` beside the native executable, as well as retaining it
inside `game/`. The launcher already sets `LD_LIBRARY_PATH` to the
bundle root.

Do not distribute the proprietary Steamworks SDK or Valve's Steam API
library without reviewing the applicable redistribution terms. This script
takes an existing local library as an input rather than downloading or
committing it.

## Current limitations

This is phase one: integration and packaging of a **prebuilt** known-good
runtime. Automated cross-machine source compilation, verified upstream
patch application, runtime provenance checks, and compatibility profiling
for additional GodotSteam versions remain future work.

On the Frame, Steam initialization may depend on the Steam client/session
and game ownership. Running for 30 minutes establishes meaningful
compatibility for the tested build, not universal compatibility.
