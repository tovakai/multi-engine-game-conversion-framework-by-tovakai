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

## Ren'Py runtime note

RPG Maker and Godot runtime acquisition is automatic through the imported
RPGMFrame backend. RenFrame does not yet automatically acquire a matching ARM64
Ren'Py runtime, so the combined application currently requires one explicitly:

```bash
multi-engine-game-conversion-framework-by-tovakai build Game.zip \
  --renpy-runtime /path/to/renpy-arm64-runtime
```

Automatic Ren'Py runtime resolution is an obvious next unification target.

## Design rule

A game exposing a compatibility problem is a test case, not a product target.
Prefer engine-level and platform-level fixes over title-specific patches. Keep
source payloads intact unless a generic compatibility repair is justified.

## License

GNU GPLv3. See `LICENSE`.
