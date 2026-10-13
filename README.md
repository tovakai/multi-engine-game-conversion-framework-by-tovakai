# Multi-Engine Game Conversion Framework by tovakai

**Convert supported PC games you already own into ARM64 packages for Linux.**
Initially built for the **Steam Frame**, with portable AArch64 Linux output as the broader goal.
Most backends use native Linux runtimes; experimental UnityFrame runs a matching
Windows ARM64 Hollow Knight player under ARM64 Proton.

There is no short public product name. You have to say the whole thing.

## Download v0.1.0.3: Cassette Beasts and guided FMOD setup

**[Latest release and release notes](https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/releases/tag/v0.1.0.3)**

| Converter application | Download |
| --- | --- |
| Windows x64 | [v0.1.0.3 Windows ZIP](https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/releases/download/v0.1.0.3/multi-engine-game-conversion-framework-by-tovakai-0.1.0.3-windows-x64.zip) |
| Linux ARM64 / AArch64 | [v0.1.0.3 Linux tarball](https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/releases/download/v0.1.0.3/multi-engine-game-conversion-framework-by-tovakai-0.1.0.3-linux-aarch64.tar.gz) |
| Archive verification | [SHA256SUMS.txt](https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/releases/download/v0.1.0.3/SHA256SUMS.txt) |

**Cassette Beasts 1.8.3 now has tested native ARM64 graphical compatibility on
Steam Frame**, including movement, transitions, battle and save/load. Controller
compatibility remains separate. Celeste and Slay the Spire 2 now share a guided
FMOD SDK download and selection dialog. See the release notes for supported scope.

These downloads contain **the converter, not games**. The project does not distribute retail game files, proprietary SDKs or Steam client libraries. You supply your own game installation and any separately licensed dependencies a particular engine needs.

### Quick start

1. Download and extract the converter for **your computer's architecture**. Run `Multi-Engine Game Conversion Framework by tovakai.exe` on Windows or the included application executable on Linux ARM64.
2. Select or drop in an **existing game installation/archive**. The app inspects it, identifies a supported backend and, where available, downloads a checksum-verified compatible runtime.
3. Convert the game to a separate **ARM64 game package**. Experimental backends may require an opt-in migration, a specific game version, or your own vendor SDK.
4. For **Steam Frame**, transfer the generated game package, extract it, keep Steam running, run `./install-to-steam.sh` from the extracted folder, and launch the new non-Steam shortcut. UnityFrame creates `*-windows-arm64-proton.zip` and requires a supported ARM64 Proton 11.0 installation; other engines keep their `*-linux-aarch64.zip` output.

**Native does not mean universal.** Matching a supported engine is not a guarantee that every game built with it will work. Read the [0.1.0.3 scope and limitations](docs/releases/0.1.0.3.md), the [23-package Steam Frame test report](docs/hardware-feedback-2026-10-11.md), and [known issues](#known-issues-and-testing-limits).

The existing [Slay the Spire 2 experimental workflow](docs/sts2-integrated-workflow.md) is different: Windows prepares a transfer package using a user-supplied FMOD Linux SDK, and the Frame finishes native components on-device. It is **not** the same one-step conversion path as the simpler engines.

## Tested game compatibility

These are **selected v0.1.0.3 compatibility highlights**, chosen for recognizable games and different engine backends. The results come from real **Steam Frame hardware tests**, but not every older result was rerun with the exact v0.1.0.3 application binary. For **all 36 recorded games**, including less-famous gems, incomplete tests and known problems, see the [full game compatibility catalog](games/README.md). Every game has its own page under `games/<game-slug>/README.md`.

| Featured game | Backend | Steam Frame hardware result |
| --- | --- | --- |
| [Stardew Valley](games/stardew-valley/README.md) | MonoFrame | Playable, including input and save/load on exact vanilla 1.6.15 |
| [Slay the Spire 2](games/slay-the-spire-2/README.md) | Experimental STS2 | Reported working; **two-stage** installation and Frame-side finishing required |
| [Undertale](games/undertale/README.md) | GameMakerFrame | Playable through second savepoint; save/load confirmed |
| [Balatro](games/balatro/README.md) | LÖVEFrame | Reported working; exact package/version depth not recorded |
| [Brotato](games/brotato/README.md) | Godot / GodotSteam | Playable; full run completed with pinned custom runtime |
| [Doki Doki Literature Club!](games/doki-doki-literature-club/README.md) | RenFrame | Original 1.1.1 reported working; later acts and file transitions not certified |
| [Fear & Hunger](games/fear-and-hunger/README.md) | RPGMFrame | Reported working; detailed coverage not recorded |
| [Fear & Hunger 2: TERMINA](games/fear-and-hunger-2-termina/README.md) | RPGMFrame | Reported working; detailed coverage not recorded |
| [To the Moon](games/to-the-moon/README.md) | RPGMFrame | Reported working; detailed coverage not recorded |
| [The Cat Lady](games/the-cat-lady/README.md) | AGSFrame | Playable with keyboard/mouse; native controller not confirmed |
| [Celeste](games/celeste/README.md) | CelesteFrame / FNA | Playable, controller and save/load confirmed; owner-supplied FMOD SDK required |
| [Cassette Beasts](games/cassette-beasts/README.md) | Godot / GodotSteam | Playable in tested 1.8.3 profile; **v0.1.0.3** graphics fix; controller unverified |
| [Hollow Knight](games/hollow-knight/README.md) | UnityFrame | Playable with controller and save/load on exact edition; **Windows ARM64 under ARM64 Proton**, not native Linux ELF |

**Status is scoped to what was observed**, not a promise of full completion, all mods,
Steam features, game updates or universal engine compatibility. A detected engine,
successful ZIP build or menu screenshot alone is not a gameplay pass. Individual
records distinguish *Playable*, *Reported working*, *Launches*, *Issues* and
*Needs retest*, and identify which packages use experimental workflows.

To contribute a result, follow the [per-game entry instructions](games/README.md#adding-or-updating-a-game)
or open a [GitHub issue](https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/issues)
with the game version, engine, converter build, tested ARM64 device, gameplay/input/save
results and sanitized logs. **Never upload proprietary SDKs, game assets or converted packages.**

## Contents

- [Download v0.1.0.3](#download-v0103-cassette-beasts-and-guided-fmod-setup)
- [Quick start](#quick-start)
- [Tested game compatibility](#tested-game-compatibility)
- [Why should I care?](#why-should-i-care)
- [Current engine backends](#current-engine-backends)
- [Roadmap](#roadmap)
- [Architecture](#architecture)
- [Install for development](#install-for-development)
- [CLI](#cli)
- [FrameBench](#framebench)
- [Steam Frame install flow](#steam-frame-install-flow)
- [Optional SteamGridDB artwork](#optional-steamgriddb-artwork-for-non-steam-games)
- [Ren'Py runtime resolution](#renpy-runtime-resolution)
- [Custom Godot / GodotSteam compatibility runtime](#custom-godot--godotsteam-compatibility-runtime)
- [Launching converted games on Linux ARM64](#launching-converted-games-on-linux-arm64)
- [Known issues and testing limits](#known-issues-and-testing-limits)
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
your existing game files and substitutes a compatible **ARM64 runtime**.
UnityFrame preserves Windows assets and runs its Windows ARM64 player under ARM64 Proton.

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
| Ren'Py | RenFrame | match official Linux ARM64 Ren'Py runtimes; opt-in full-engine migrations for original DDLC 6.99.12, exact 7.3.5, and legacy 7.4.x | Ren'Py 8, legacy 7.3.5/7.4.11 (via 7.5.0), and original DDLC 6.99.12 (via 7.5.3) launched successfully on Steam Frame; deeper compatibility varies |
| RPG Maker XP / VX / VX Ace | RPGMFrame / mkxp-z | replace RGSS player with Linux ARM64 mkxp-z plus compatibility migration | XP boots on Steam Frame |
| RPG Maker MV / MZ | RPGMFrame / NW.js | replace Windows NW.js with Linux ARM64 NW.js plus generic compatibility repairs | MV and MZ validated on Steam Frame |
| RPG Maker 2000 / 2003 | RPGMFrame / EasyRPG | copy LCF data and automatically package portable native EasyRPG | Experimental; no separate target player installation required |
| Construct 2 / 3 | ConstructFrame / NW.js | discover web exports, including `package.nw`, and replace the desktop wrapper with ARM64 NW.js | Experimental; game addons require testing |
| GameMaker VM | GameMakerFrame / Butterscotch | automatically download a verified runner; validate VM data and retain assets | Experimental; Undertale gameplay through second savepoint and save/load confirmed; YYC/GMRT excluded |
| LÖVE | LÖVEFrame | automatically download LÖVE 11.5 and supported modules; unpack game data | Experimental; Balatro menu and Gravity Circuit startup tested |
| Adventure Game Studio | AGSFrame | automatically download native AGS; retain CLIB data and supporting assets | Experimental; The Cat Lady startup tested; unknown plugins require native implementations |
| MonoGame / .NET | MonoFrame | automatically download a verified .NET/MonoGame SDK and prepare a copied installation | Experimental; vanilla Steam Stardew Valley 1.6.15: character creation, movement, tools, save/load and pointer/gamepad input user-confirmed through Steam; SMAPI and other versions excluded |
| Godot | RPGMFrame / Godot | preserve PCK; use an exact official ARM64 runtime for stable exports or a pinned compatibility runtime for supported custom/GodotSteam exports | Godot 4.3 validated; Brotato Godot 3.7 custom + GodotSteam played ~30 minutes on Steam Frame |
| Unity / Hollow Knight | UnityFrame | exact tested Steam edition: replace Windows x64 player/Mono/plugins with pinned Windows ARM64 components under ARM64 Proton | Experimental; menu, controller gameplay, audio and bench save/load after relaunch confirmed on Steam Frame; GUI-generated package installed and launched through Steam |
| Celeste / XNA to FNA | CelesteFrame | verified Steam Windows XNA Celeste 1.4.0.0; FNA 23.10 / .NET 8 ARM64 runtime and separately supplied FMOD Linux SDK | Experimental; menu, music, controller gameplay and save/load confirmed on Steam Frame; select the desired primary controller through Steam. [Setup and limits](docs/backends/celesteframe.md) |

The combined application routes by detected engine. The backend packages remain
visible in the repository so engine-specific fixes can stay focused instead of
turning the umbrella router into a giant conditional swamp.

Supported GodotSteam 3.5.1, 4.6.0 and 4.7.2 exports now use automatic verified
runtime downloads on Windows, alongside the existing Brotato recipe. No manual
runtime selection or Frame connection is needed for conversion. **Cassette Beasts
1.8.3** passed physical Steam Frame movement, transitions, battle and save/load
testing with the narrow graphics fix bundled in **v0.1.0.3**. Controller and
full-game compatibility remain unverified. See [the Cassette Beasts test entry](games/cassette-beasts/README.md)
and [downloadable GodotSteam runtimes](docs/downloadable-godotsteam-runtime.md).

Ren'Py bytecode-only exports are recognized using bounded, non-executing metadata
inspection for supported bytecode formats, independently of the host Python version. Identified Katawa
Shoujo 6.10.2 distributions use the recovered legacy compatibility profile,
including pinned HD source and UI fixes. Identified Ren'Py 8.5 nightlies offer an
experimental complete 8.5.3 engine/runtime migration in the GUI or with
`--experimental-renpy-prerelease-migration`; this requires gameplay/save testing.
Encrypted Godot packs/scripts require an ARM64 runtime built with the game's key.
The exact tested Hollow Knight Steam edition on Unity 6000.0.61f1 now uses the
regular CLI/GUI conversion flow with automatic verified downloads and Windows
ARM64 Proton packaging. See [UnityFrame setup and limits](docs/backends/unityframe.md).
Other Unity exports and WOLF RPG Editor games remain gated as unsupported.

New EasyRPG packages include a portable player and supporting libraries
automatically. Older packages can still use the system player or
`flatpak install --user --arch=aarch64 flathub org.easyrpg.player`.
EasyRPG reads the copied `RPG_RT.exe` as engine metadata; the launcher executes
EasyRPG, and Windows engine plugins are not supported.

## Roadmap

[The roadmap](docs/ROADMAP.md) tracks work toward v1.0. **Several experimental backends arrived ahead of their original milestones**, notably GameMakerFrame, ConstructFrame and MonoFrame. Future milestones focus on **reproducible conversion, broader testing, compatibility improvements and less manual device setup**, not just adding a backend's name to the menu.

The next coverage target documents **35 tested games** across Ren'Py, RPG Maker and Godot, alongside deeper GameMaker validation. These are testing goals, **not 35 promised compatible games**.

## Architecture

```text
Your game installation / archive (never included in the converter)
                           |
                inspection + engine detection
                           |
                   unified GUI / CLI
                           |
      +--------------------+-------------------------+
      |                    |                         |
   RenFrame             RPGMFrame           Other engine backends
   Ren'Py          RPG Maker + Godot    GameMaker, LÖVE, Construct,
                                       AGS, MonoGame / .NET
      |                    |                         |
      +--------------------+-------------------------+
                           |
           compatible ARM64 runtime / checked SDK
                           |
                 Linux AArch64 game ZIP
                           |
               transfer to ARM64 device
                           |
            Steam Frame shortcut (optional)
```

Supported runtime recipes are verified and cached; the source game is copied rather than altered in place. Each backend has its own compatibility constraints and test status in the table above. **STS2** remains a separate experimental two-stage path with device-side finalization. Implementation details live under [`docs/backends/`](docs/backends/) and in the [0.1.0 release scope](docs/releases/0.1.0.md).

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

## CLI

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

## FrameBench

FrameBench is a **separate companion tool** for comparing the same Steam game
running as a native ARM64 conversion versus the original Steam/FEX (or Proton)
path. Power consumption and battery endurance are first-class results. It does
not replace the converter and is developed on its own feature branch so it
cannot destabilize the v0.1.1 installer work.

```bash
framebench detect-sensors
framebench gui
framebench protocol stardew
```

Ordinary headset sessions use the GUI: pick an installed Steam game that has a
converted package, choose Native ARM64 or Original Steam, start the benchmark.
FrameBench switches the launch path, starts the real Steam entry, verifies the
running architecture, records power, then restores the previous linked
configuration. The CLI remains for automation.

See [FrameBench](docs/framebench.md) and the [Stardew protocol](docs/framebench-protocol.md).
All current automated tests are **simulated sysfs fixtures**, not Steam Frame
hardware observations.

## Steam Frame install flow

See [versioning and provenance](docs/versioning.md) for development identities,
CLI `--build-info`, the GUI's **COPY BUILD INFO**, and identifying old conversions.

The default build also creates a portable `<game>-frame-conv-v<converter-version>-linux-aarch64.zip` package
(UnityFrame keeps the `-windows-arm64-proton.zip` suffix). Existing unversioned ZIPs remain installable. For
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
Steam Frame launch, menu, audio, controls, exit and graphical relaunch were
confirmed on 2026-10-08; DDLC also appears in the later
[working-package report](docs/hardware-feedback-2026-10-11.md).
That report does **not** establish full-story, later-act, character-file or mod
compatibility. Other Ren'Py 6 games remain unsupported automatically. See
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

**Ren'Py 7.3.5 and 7.4.x** predate official ARM64 sdkarm releases. In the GUI, when
inspection identifies Ren'Py 7.4.x with **Python 2**, or exact **7.3.5** with
high-confidence, consistent engine version evidence and a Python 2 layout, the runtime
selector says **experimental Ren'Py 7.5.0** instead of incorrectly promising
automatic 7.4.x support. Clicking **CONVERT** asks for explicit consent:

- **Yes:** download and checksum-verify the official Ren'Py 7.5.0 sdkarm,
  use its **matching Ren'Py 7.5 Python engine and Python 2 ARM64 binaries**
  together, and copy the original game's `game/` assets and scripts into
  the new runtime. We do **not** combine the older Python engine with 7.5
  compiled graphics libraries;
- **No:** browse for a manually supplied compatible ARM64 Ren'Py runtime;
- **Cancel:** do nothing.

The experimental cross-minor fallback is intentionally limited to detected
7.4.x and authoritative exact 7.3.5 / Python 2 games, never automatic and never a Python 2-to-3 upgrade.
The original installation is left unchanged; the converted copy runs on
7.5.0 engine code rather than the source game's older engine code.
The output clearly warns that gameplay compatibility is **not established**.
Other pre-7.5 Ren'Py games still require an explicitly selected runtime.
The converter does **not silently** substitute a nearby Ren'Py version.
The same opt-in is available in both CLIs as `--experimental-legacy-arm64-fallback`;
`--dry-run` validates it without downloading or writing a build.
Pesterquest's 7.3.5 conversion passed Steam Frame Stages A and B (menu, music,
controls, brief gameplay, choices, save/load, quit and saved-progress restoration
after native Steam relaunch); several volumes and Steam hooks remain unverified. See
[the inspection notes and Steam Frame test procedure](docs/renpy-735-arm64-migration.md).
A manual runtime remains available as an escape hatch:

```bash
multi-engine-game-conversion-framework-by-tovakai build Game.zip \
  --renpy-runtime /path/to/reviewed-renpy-arm64-runtime
```

Set `MEGCFBT_CACHE_DIR` to relocate the shared runtime cache. RenFrame also
honors `RENFRAME_CACHE_DIR` for its own runtime cache.

## Custom Godot / GodotSteam compatibility runtime

Matching GodotSteam ARM64 release-template downloads are now available for
Godot 4.6.0 and 4.7.2, with a separate pinned source recipe for Godot 3.5.1.
See [native backends and GodotSteam tests](docs/native-backends.md) for SDK setup,
the Frame graphics-routing fix, runtime capabilities and remaining test coverage.

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

The **converter application** is distributed as a Windows ZIP or Linux ARM64
tarball. The standard **converted game** output is a separate ZIP. Do not
confuse the application download with the game package: transfer and extract
the converted game ZIP on the target device, then use its included launcher or
Steam installer. If file copying loses executable permissions, restore the
launcher/script executable bits; Ren'Py's launch wrapper also attempts to
repair runtime permissions.

When launching from **SSH**, no `DISPLAY` is normally set. Start the game from
the graphical session, or explicitly set the display and matching X11 authority
file for your own desktop. For example, Frametop uses a session-specific
Xwayland display and authentication file; **do not hardcode its Xauthority
filename**, and do not disable X11 authentication. A successful main-menu
event loop doesn't necessarily mean its window is visible on your headset.

## Known issues and testing limits

| Game / area | Known limitation |
| --- | --- |
| Cassette Beasts | Graphical corruption resolved in a user-confirmed five-minute native Frame test of fresh Windows-GUI output, including transitions, battle and save/load, using a narrow Zink/depth profile. Controller remains a separate issue; not full-game certification. [Rendering evidence](docs/cassette-beasts-rendering.md). |
| Cook, Serve, Delicious! 3 | Launches, but performance and controller behavior remain problematic. |
| Desert Child | Runs with graphical glitches; not a clean compatibility pass. |
| Katawa Shoujo (non-HD) | A compatibility profile was added after a failed conversion report; do not count it as hardware-verified gameplay without a new test. |
| Unsupported or unusual runtimes | Custom/encrypted exports, unsupported engine versions and missing native plugins can still fail inspection, conversion or launch. |

For details and the follow-up fixes around Ren'Py nightlies and Live2D, see
[the hardware feedback and investigation](docs/hardware-feedback-2026-10-11.md).
For the supported release boundary, see [the v0.1.0 scope](docs/releases/0.1.0.md).

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

Existing framework components use GNU GPLv3 (`LICENSE`); the integrated STS2
backend retains GNU AGPLv3 (`experiments/sts2-steamworks/LICENSE`). Combined
distributions carry the AGPL requirements described in `THIRD_PARTY_NOTICES.md`.
