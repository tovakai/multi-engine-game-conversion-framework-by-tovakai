# Multi-Engine Game Conversion Framework by Tovakai

A deliberately un-snappy desktop and command-line application for converting
supported indie-game runtimes to native Linux ARM64 packages, initially targeting
the Steam Frame.

There is no short public product name. You have to say the whole thing.

## Contents

- [Why should I care?](#why-should-i-care)
- [Current engine backends](#current-engine-backends)
- [Architecture](#architecture)
- [Install for development](#install-for-development)
- [Use the extremely reasonable executable name](#use-the-extremely-reasonable-executable-name)
- [Ren'Py runtime resolution](#renpy-runtime-resolution)
- [Custom Godot / GodotSteam compatibility runtime](#custom-godot--godotsteam-compatibility-runtime)
- [Optional SteamGridDB artwork](#optional-steamgriddb-artwork-for-non-steam-games)
- [Launching converted games on Linux ARM64](#launching-converted-games-on-linux-arm64)
- [Tested game compatibility](#tested-game-compatibility)
- [Support the project](#support-the-project-)
- [Design rule](#design-rule)
- [License](#license)

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
| Ren'Py | RenFrame | match official Linux ARM64 Ren'Py runtimes; opt-in full-engine migrations for original DDLC 6.99.12 and legacy 7.4.x | Ren'Py 8, legacy 7.4.11 (via 7.5.0), and original DDLC 6.99.12 (via 7.5.3) launched successfully on Steam Frame; deeper compatibility varies |
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

## Optional SteamGridDB artwork for non-Steam games

Set the `STEAMGRIDDB_API_KEY` **process environment variable** before running
the converter to enable [SteamGridDB](https://www.steamgriddb.com/api/v2) artwork.
The key is never written to the repository, portable ZIP, metadata or Steam shortcut.

For non-Steam games such as My Pig Princess, the converter searches for a
**unique exact title match**, rather than guessing based on fuzzy titles.
With an existing embedded Steam AppID, official Steam CDN artwork takes priority,
and SteamGridDB resolves the game by that platform ID only for missing slots.

Artwork priority for each slot: **user-selected > official Steam > SteamGridDB**.
The provider fills available portrait (600x900), horizontal grid, hero and logo
slots with static JPEG/PNG. Missing artwork or network/API errors never block conversion.
SteamGridDB defaults to its safe `nsfw=false` filter. To allow adult artwork
from the community, set `STEAMGRIDDB_NSFW=any` explicitly in the environment.

To get art when the **converted game is not on this computer**, fetch it
standalone by title. No game files, launcher, or conversion output are needed:

~~~powershell
.\.venv-win\Scripts\python.exe -m megcfbt.cli artwork `
    --name "My Pig Princess" `
    --output "$env:USERPROFILE\Downloads\MyPigPrincess-artwork"
~~~
Images are saved under `.megcfbt/artwork/` inside that destination.
Copy those small image files to the existing Frame installation and use its
Steam installer if available. Standalone mode intentionally does **not**
generate a fake game launcher or a game ZIP, and rejects `--repackage`.

You can also **refresh artwork on an existing converted game** without rebuilding:

~~~powershell
# Run from the repository root. The key is entered without echoing.
$secure = Read-Host "SteamGridDB API key" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $env:STEAMGRIDDB_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}
$env:STEAMGRIDDB_NSFW = "any"  # Optional: allow adult-tagged artwork
.\.venv-win\Scripts\python.exe -m megcfbt.cli artwork "C:\path\to\MyPigPrincess-frame" --repackage --force
~~~

Use `--steamgriddb-id NUMBER` if there are several exact-title records;
otherwise the converter skips ambiguous matches instead of using the wrong
game's art. The `artwork` command expects the **original converted build**
directory, not an already extracted Frame ZIP wrapper, when using `--repackage`.
On the Frame, run `./install-to-steam.sh` again to refresh custom art for
the existing non-Steam shortcut. The installer uses the actual non-Steam shortcut
ID, never the SteamGridDB game ID. Artwork provenance is recorded in
`.megcfbt/package.json`; no API credentials are recorded.

## Ren'Py runtime resolution

Original DDLC 1.1.1 / Ren'Py 6.99.12 has a separate opt-in **experimental**
full-engine migration to official Ren'Py 7.5.3 Python 2 ARM64 in the main GUI.
Steam Frame Stage A launch, menu, audio, controls, exit and graphical relaunch
were confirmed on real hardware (2026-10-08). Story progression, poem game,
saves, character-file transitions and in-story restarts still require deeper
verification. Other Ren'Py 6 games remain unsupported automatically. See
[the DDLC migration and Steam Frame test procedure](docs/ddlc-111-arm64-migration.md).

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

**Ren'Py 7.4.x** predates official ARM64 sdkarm releases. In the GUI, when
inspection confidently identifies Ren'Py 7.4.x with **Python 2**, the runtime
selector says **experimental Ren'Py 7.5.0** instead of incorrectly promising
automatic 7.4.x support. Clicking **CONVERT** asks for explicit consent:

- **Yes:** download and checksum-verify the official Ren'Py 7.5.0 sdkarm,
  use its **matching Ren'Py 7.5 Python engine and Python 2 ARM64 binaries**
  together, and copy the original game's `game/` assets and scripts into
  the new runtime. We do **not** combine the 7.4 Python engine with 7.5
  compiled graphics libraries;
- **No:** browse for a manually supplied compatible ARM64 Ren'Py runtime;
- **Cancel:** do nothing.

The experimental cross-minor fallback is intentionally limited to detected
7.4.x / Python 2 games, never automatic and never a Python 2-to-3 upgrade.
The original installation is left unchanged; the converted copy runs on
7.5.0 engine code rather than the source game's 7.4 engine code.
The output clearly warns that gameplay compatibility is **not established**.
Other pre-7.5 Ren'Py games still require an explicitly selected runtime.
The converter does **not silently** substitute a nearby Ren'Py version.
A manual runtime remains available as an escape hatch:

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
| [My Pig Princess 0.10.1](https://www.patreon.com/CyanCapsule) | Ren'Py 8.3.7 | Steam Frame | Playable (gameplay confirmed) | Native ARM64; requires an accessible graphical session. Tested with Frametop Xwayland after preserving Python bytecode and restoring executable permissions |
| [Everlasting Summer 1.6](https://store.steampowered.com/app/331470/Everlasting_Summer/) (original release) | Ren'Py 7.4.11 / Python 2; experimental full-engine migration to Ren'Py 7.5.0 ARM64 | Steam Frame | Playable (brief skip-through; full testing pending) | Game launches, passes splash screen and progresses through dialogue. Requires the opt-in 7.5.0 engine/runtime fallback; the previous 7.4 engine + 7.5 graphics-library hybrid crashed at GL initialization. |
| Everlasting Summer (author's Ren'Py 8 beta) | Ren'Py 8.x; exact beta/runtime version not recorded | Steam Frame | Playable (initial gameplay confirmed; full testing pending) | Standard conversion ran without observed issues during initial play. Upstream beta status relates to potential mod compatibility; mods were not tested. |
| [Doki Doki Literature Club! 1.1.1](https://ddlc.moe/) (original, not Plus) | Ren'Py 6.99.12 / Python 2; experimental full-engine migration to official Ren'Py 7.5.3 ARM64 | Steam Frame | Launches (Stage A passed; gameplay verification pending) | Real-device native Steam shortcut: menu, audio, input, exit and relaunch reported working. The user's original files are preserved locally. Poem game, save/load, character-file transitions and later acts remain untested; mods not tested. |

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
