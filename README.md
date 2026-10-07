# Multi-Engine Game Conversion Framework by Tovakai

A deliberately literal multi-engine game conversion application for producing native **Linux ARM64** builds from Windows-oriented indie game distributions.

The name is not abbreviated. Please enjoy typing it.

## Integrated backends

| Engine | Conversion path | Current Steam Frame status |
| --- | --- | --- |
| Ren'Py 7/8 | RenFrame sdkarm runtime conversion | Hardware-proven on tested modern Ren'Py titles; selected legacy titles use compatibility profiles |
| RPG Maker XP / VX / VX Ace | Linux ARM64 mkxp-z | XP hardware-proven to title screen with To the Moon |
| RPG Maker MV / MZ | Linux ARM64 NW.js | Hardware-proven with multiple MV/MZ games |
| Godot | Matching official Linux ARM64 Godot runtime | Godot 4.3 hardware-proven with a converted title |

The top-level application detects the engine, selects the backend, resolves the appropriate ARM64 runtime, and emits a transfer-ready build. Engine-specific compatibility logic remains isolated behind backend boundaries.

## Why this repository exists

This repository combines the working conversion code from:

- **RenFrame**, including the current legacy/runtime compatibility work from compat/legacy-profiles-0.1.1
- **RPGMFrame**, including the current RPG Maker XP/VX/VX Ace, MV/MZ, and Godot backends

The merger is intentionally evolutionary rather than a rewrite. The proven backend packages remain importable inside this repository while the new application layer provides one detector, one build API, one CLI, and one GUI. Shared code can be collapsed later without destabilizing working conversion paths.

Imported baseline snapshots:

- RenFrame compatibility backend: a571e75d4b5b21d8494c2a1181d367af631eb4d3
- RenFrame mod-library tooling: 59e09b263067b4782118c4d50ed4fab993a0d774
- RPGMFrame: ec54754e5832f3665df9107b75020c65b7b6c735

## Install from source

~~~bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[gui]"
~~~

On Windows PowerShell:

~~~powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[gui]"
~~~

## The command

Inspect a game:

~~~bash
multi-engine-game-conversion-framework-by-tovakai inspect /path/to/game
~~~

Convert it:

~~~bash
multi-engine-game-conversion-framework-by-tovakai build /path/to/game
~~~

Open the desktop application:

~~~bash
multi-engine-game-conversion-framework-by-tovakai gui
~~~

Show the integrated backend matrix:

~~~bash
multi-engine-game-conversion-framework-by-tovakai backends
~~~

RenFrame's mod-library code is preserved in the source tree for later integration, but the maintainer UI is not exposed by the unified application yet. The original seed catalog is intentionally not part of this bootstrap merge.

## Input and output behavior

The unified inspector accepts game directories, ZIP archives, and TAR-family archives. Archive inspection rejects path traversal and unsafe links.

For Ren'Py, the parent application copies directory inputs into a temporary working tree before conversion so the original game is not patched in place. The final artifact is a Linux ARM64 ZIP.

RPG Maker and Godot builds produce a <source>-frame/ directory and, by default, a portable <source>-linux-aarch64.tar.gz beside it.

Runtime selection remains backend-specific:

- Ren'Py resolves matching sdkarm builds and known safe same-series fallbacks.
- RPG Maker MV/MZ uses the pinned/tested NW.js ARM64 line unless overridden.
- RPG Maker XP/VX/VX Ace uses the pinned mkxp-z ARM64 artifact.
- Godot reads the engine version from the PCK and resolves the matching official ARM64 release.

## Development

~~~bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,gui]"
pytest
~~~

The old RenFrame and RPGMFrame repositories remain useful as historical development records. New cross-engine application work belongs here.
