# Multi-Engine Game Conversion Framework by Tovakai

A deliberately un-snappy desktop and command-line application for converting
supported indie-game runtimes to native Linux ARM64 packages, initially targeting
the Steam Frame.

There is no short public product name. You have to say the whole thing.

## Why should I care?

Most PC games are distributed for x86-64 processors. On an ARM64 Linux device,
running those versions often means using translation or compatibility layers
such as FEX and Proton. Those tools are impressive, but sometimes the game
itself is already portable: it is the **bundled engine runtime** that was
built for x86-64.

This project takes a different route. When an engine is supported, it keeps
your existing game files and substitutes a compatible **native Linux ARM64
runtime**, rather than translating the original x86-64 runtime while playing.

Why bother?

- **Less translation work:** the engine executes directly on the ARM64 CPU,
  potentially reducing overhead, memory use, and power consumption.
- **Another way to run games:** some titles may work natively even when their
  original Windows or x86 Linux builds struggle through compatibility layers.
- **More than one device:** the goal is portable ARM64 Linux output, whether
  you're using a Steam Frame, a Raspberry Pi, an ARM handheld, or a laptop.
- **Your games, your setup:** convert games you already own for your own device;
  no bundled game downloads, mandatory storefront, or prescribed launcher.

**Native does not automatically mean faster or more compatible.** Results
depend on the engine version, graphics drivers, native libraries, and the
individual game. FEX and Proton may still be the better option for some games.
Not every title made with a supported engine can be converted successfully.

The idea is simple: **if a game doesn't actually need an x86-64 CPU, why make
it pretend it has one?**

## Current engine backends

| Engine family | Backend | Conversion strategy | Hardware status |
| --- | --- | --- | --- |
| Ren'Py | RenFrame | replace the distributed runtime with a matching Linux ARM64 Ren'Py runtime | proven separately in RenFrame; combined path needs validation |
| RPG Maker XP / VX / VX Ace | RPGMFrame / mkxp-z | replace RGSS player with Linux ARM64 mkxp-z plus compatibility migration | XP boots on Steam Frame |
| RPG Maker MV / MZ | RPGMFrame / NW.js | replace Windows NW.js with Linux ARM64 NW.js plus generic compatibility repairs | MV and MZ validated on Steam Frame |
| Godot | RPGMFrame / Godot | preserve PCK; use an exact official ARM64 runtime for stable exports or a pinned compatibility runtime for supported custom/GodotSteam exports | Godot 4.3 validated; Brotato Godot 3.7 custom + GodotSteam played ~30 minutes on Steam Frame |

The combined application routes by detected engine. The backend packages remain
visible in the repository so engine-specific fixes can stay focused instead of
turning the umbrella router into a giant conditional swamp.

## Architecture

```text
Multi-Engine Game Conversion Framework by Tovakai
                     |
              source preparation
                     |
               engine router
          ___________|____________
         |           |            |
      Ren'Py      RPG Maker     Godot
         |           |            |
     RenFrame      RPGMFrame    RPGMFrame
         |           |            |
         +-----------+------------+
                     |
             Linux ARM64 build
                     |
             optional tar.gz
```

The current import points are recorded under `docs/backends/`.

## Install for development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,gui]"
pytest
```

On Windows PowerShell:

```powershell
py -m venv .venv-win
.\.venv-win\Scripts\Activate.ps1
pip install -e ".[dev,gui]"
```

## Use the extremely reasonable executable name

Inspect a game:

```bash
multi-engine-game-conversion-framework-by-tovakai inspect /path/to/game
```

Build it:

```bash
multi-engine-game-conversion-framework-by-tovakai build /path/to/game
```

Open the GUI:

```bash
multi-engine-game-conversion-framework-by-tovakai gui
```

There is also a second executable named
`multi-engine-game-conversion-framework-by-tovakai-gui`, because apparently
one long command was not enough.

## Ren'Py runtime resolution

Ren'Py now follows the same automatic-runtime philosophy as the other backends.
When inspection yields an exact Ren'Py 7.x or 8.x release, the RenFrame backend:

1. normalizes the detected release to `X.Y.Z`
2. downloads the official `renpy-X.Y.Z-sdkarm.tar.bz2` from renpy.org
3. verifies its SHA-256 against the official `checksums.txt`
4. extracts only the matching `py2-linux-aarch64` or
   `py3-linux-aarch64` platform slice
5. validates an AArch64 ELF runtime
6. caches that platform slice for later conversions
7. grafts it into a copy of the original distributed game

The original game's `renpy/` engine tree and other payload files are preserved.
This is intentionally more surgical than replacing the game with a complete SDK.

The converter does **not** substitute a nearby Ren'Py version when detection is
ambiguous. A manual runtime remains available as an escape hatch:

```bash
multi-engine-game-conversion-framework-by-tovakai build Game.zip \
  --renpy-runtime /path/to/reviewed-renpy-arm64-runtime
```

Set `MEGCFBT_CACHE_DIR` to relocate the shared runtime cache. RenFrame also
honors `RENFRAME_CACHE_DIR` for its own runtime cache.

## Custom Godot / GodotSteam compatibility runtime

Custom Godot development exports are still treated conservatively. The first
automatic compatibility recipe is deliberately narrow: Godot 3.7.0 custom
builds with a built-in GodotSteam marker on native Linux ARM64.

On Steam Frame, the converter can build and cache the proven compatibility
stack automatically:

- Godot 3.7-dev1 at `a117d512...`
- upstream CanvasItem cast fix from Godot PR #123099
- GodotSteam 3.30 using the classic Steam C++ interface path
- Steamworks 1.62 header surface from ValveSoftware/Proton
- the Frame's installed native ARM64 `libsteam_api.so`

A manual custom runtime remains available as an override. See
`docs/custom-godot-arm64-runtime.md` for the exact recipe and host
requirements.

## Launching converted games on Linux ARM64

For Windows-to-Linux transfers, prefer extracting the generated `.tar.gz`
package directly on the target device; its archive metadata restores executable
permissions. The Ren'Py launch wrapper also attempts to repair executable bits
on ARM64 runtime files when they were lost in a folder copy.

When launching from **SSH**, no `DISPLAY` is normally set. Start the game from
the graphical session, or explicitly set the display and matching X11 authority
file for your own desktop. For example, Frametop uses a session-specific
Xwayland display and authentication file; **do not hardcode its Xauthority
filename**, and do not disable X11 authentication. A successful main-menu
event loop doesn't necessarily mean its window is visible on your headset.

## Tested game compatibility

This table tracks **real game tests on Linux ARM64 hardware**, not games that
merely pass engine detection or produce a build. It is a growing test log,
not a promise that every game using an engine will work.

| Game | Engine | Tested device | Status | Notes |
| --- | --- | --- | --- | --- |
| [Brotato 1.1.14.6](https://store.steampowered.com/app/1942280/Brotato/) | Godot 3.7 custom / GodotSteam | Steam Frame | Playable (completed a full run without issues) | Requires the pinned GodotSteam compatibility runtime; not a standard Godot export |
| [My Pig Princess 0.10.1](https://cyancapsule.itch.io/my-pig-princess) | Ren'Py 8.3.7 | Steam Frame | Playable (gameplay confirmed) | Native ARM64; requires an accessible graphical session. Tested with Frametop Xwayland after preserving Python bytecode and restoring executable permissions |

**Status guide:** **Playable** = actual gameplay tested; **Launches** = starts
but gameplay not yet validated; **Issues** = runs with notable problems;
**Blocked** = conversion or launch currently fails. Include the game version,
runtime/backend, device, and any workarounds in the notes whenever known.

A successful conversion build alone is **not** a compatibility pass. Results
may differ across game versions, ARM64 devices, graphics drivers, and runtime
versions. To contribute a result, open a GitHub issue or pull request with
the game name and version, engine, device/distro, status, reproduction steps,
and relevant logs. **Do not upload or redistribute game files.**

## Support the project ☕

**Why tip a vibecoded project?**

The code may be AI-assisted, but the testing is very much hands-on. I spend
hours converting games, chasing down compatibility issues, and actually playing
them on ARM64 hardware to find out whether they work beyond the title screen.
I'm also buying games out of my own pocket just to put more engines, versions,
and edge cases through their paces.

This is **100% a passion project**. The converter is free, and you don't need
to donate to use it. But if it helps you enjoy a game on a device it wasn't
originally built for, and you'd like to help fund the next round of testing,
you can [buy me a coffee on Ko-fi](https://ko-fi.com/tovakai).

Every little bit helps keep the compatibility list growing. Thank you! ❤️

## Design rule

A game exposing a compatibility problem is a test case, not a product target.
Prefer engine-level and platform-level fixes over title-specific patches. Keep
source payloads intact unless a generic compatibility repair is justified.

## License

GNU GPLv3. See `LICENSE`.
