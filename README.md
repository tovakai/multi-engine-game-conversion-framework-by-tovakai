# Multi-Engine Game Conversion Framework by Tovakai

A deliberately un-snappy desktop and command-line application for converting
supported indie-game runtimes to native Linux ARM64 packages, initially targeting
the Steam Frame.

There is no short public product name. You have to say the whole thing.

## Current engine backends

| Engine family | Backend | Conversion strategy | Hardware status |
| --- | --- | --- | --- |
| Ren'Py | RenFrame | replace the distributed runtime with a matching Linux ARM64 Ren'Py runtime | proven separately in RenFrame; combined path needs validation |
| RPG Maker XP / VX / VX Ace | RPGMFrame / mkxp-z | replace RGSS player with Linux ARM64 mkxp-z plus compatibility migration | XP boots on Steam Frame |
| RPG Maker MV / MZ | RPGMFrame / NW.js | replace Windows NW.js with Linux ARM64 NW.js plus generic compatibility repairs | MV and MZ validated on Steam Frame |
| Construct 2 / 3 | RPGMFrame / NW.js | detect exported HTML5 payloads via `c2runtime.js` or `c3runtime.js` and re-wrap them with Linux ARM64 NW.js | implemented; hardware validation pending |
| Godot | RPGMFrame / Godot | preserve PCK and launch it with the exact matching official Linux ARM64 Godot runtime | Godot 4.3 title running on Steam Frame |

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
         |           |            |             |
      Ren'Py      RPG Maker    Construct       Godot
         |           |            |             |
     RenFrame      RPGMFrame   RPGMFrame      RPGMFrame
         |           |            |             |
         +-----------+------------+-------------+
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

## Construct 2 / 3

Construct exports are browser payloads, so the first implementation deliberately
reuses the same verified Linux ARM64 NW.js runtime path already used for RPG Maker
MV/MZ. Detection recognizes Construct 2's `c2runtime.js` and Construct 3's
`c3runtime.js`, including the common `scripts/c3runtime.js` layout.

This path is currently marked **needs testing** rather than universally supported:
wrapper-specific APIs, Steam integrations, and third-party addons may depend on
Construct's original desktop wrapper. Construct 2's ZIP-based `package.nw`
payload is detected and unpacked safely. Modern opaque `assets.dat` and
single-file WebView2/CEF wrappers are not unpacked by this backend yet.

Modern Construct 3 also has an official Linux CEF exporter with ARM64 support. If
a game already ships that build, conversion should not be necessary; the converter
is primarily useful for Windows-only or older NW.js-era releases.

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

## Design rule

A game exposing a compatibility problem is a test case, not a product target.
Prefer engine-level and platform-level fixes over title-specific patches. Keep
source payloads intact unless a generic compatibility repair is justified.

## License

GNU GPLv3. See `LICENSE`.
