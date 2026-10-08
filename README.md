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
          Steam Frame ZIP package
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

## Steam Frame install flow

The default build also creates a portable `*-linux-aarch64.zip` package. For
now, treat it as a normal file transfer rather than a magic sideload bundle:

1. copy the ZIP to the Steam Frame using Frame Control, SCP, a USB drive, or any
   other file-transfer method
2. extract it on the Frame
3. leave Steam / SteamVR running
4. open a terminal in the extracted folder
5. run `./install-to-steam.sh`

The bundled installer asks the running Steam client to import the package's
`launch.sh` as a normal **non-Steam game** using SteamOS's
`steam://addnonsteamgame/` path. It then reads back the shortcut Steam created
and installs bundled artwork under that shortcut's actual non-Steam AppID.

The installer also computes the deterministic non-Steam AppID formula used by
Deckport and related tools. That gives us a predictable ID when Steam preserves
the expected executable/name strings, while the read-back step remains the
authority if Steam normalizes the imported shortcut differently. When the source
exposes an exact Steam AppID, the converter best-effort bundles official portrait,
horizontal banner, hero, and logo art. Steam may require a Steam / SteamVR
environment restart before newly copied custom artwork becomes visible.

This avoids directly rewriting `shortcuts.vdf` while Steam is closed, which is
important on Steam Frame because shutting down Steam/SteamVR also tears down the
desktop environment.

Direct installation through third-party sideloaders such as FrameDrop or Frame
Control is not a supported contract yet. Their executable-selection and Devkit
Game behavior can bypass the generated launcher or conflict with games that use
their original Steam AppID.

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

## Design rule

A game exposing a compatibility problem is a test case, not a product target.
Prefer engine-level and platform-level fixes over title-specific patches. Keep
source payloads intact unless a generic compatibility repair is justified.

## License

GNU GPLv3. See `LICENSE`.
