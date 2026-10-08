# Original DDLC 1.1.1 experimental ARM64 migration

Issue [#37](https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/issues/37).
Hardware verification is **pending**. Conversion success does not establish
menu, story, save, later-act, restart, ending, or mod compatibility. Do not
merge this milestone until real Steam Frame testing is complete.

## Scope and architecture

Only a user-owned original DDLC 1.1.1 installation with authoritative Ren'Py
6.99.12 engine evidence is a candidate. The gate also requires exact-case
`DDLC.exe`, `DDLC.py`, `game/audio.rpa`, `images.rpa`, `scripts.rpa`, `fonts.rpa`
and a real `characters/` directory. Conflicting engine evidence, case
collisions, Unity markers, unexpected character entries and linked required
paths are rejected. Existing character files may be absent: that can be story
state. A loose `game/script_version.txt`, when present, must say `1.1.1`.
The original Steam layout does not require this loose marker. Layout evidence
does not authenticate a game version or detect all modifications; the user
confirms original 1.1.1 when opting in. Packed story scripts are never read for
identification. DDLC Plus and mods are outside this milestone.

The migration replaces the entire engine with the matched official Ren'Py
7.5.3 Python 2.7 engine and AArch64 binaries. It never maps all Ren'Py 6 games
to generation 7, never silently uses Python 3, and does not graft 7.5.3 binary
extensions into 6.99.12. Normal 7/8 acquisition and the separate 7.4 → 7.5.0
fallback remain available.

Downloads come from the [official 7.5.3 release](https://www.renpy.org/release/7.5.3).
The SDK archive SHA256 was independently compared with the official checksum
file and is pinned for the default official origin:

```text
renpy-7.5.3-sdkarm.tar.bz2
6e5da3388b083d05f9d43991310776ff394b04bbb5541ee6216484ebd3d5a567
```

The verified real archive root is `renpy-7.5.3-sdkarm/`. Selected entries are
`renpy/`, `renpy.py`, `renpy.sh`, `lib/py2-linux-aarch64/`, `lib/python2.7/`
and license notices. SDK sample games, editor packages and other architectures
are excluded. Engine version, AArch64 ELF headers, stdlib and license presence
are checked. A file-hash manifest validates reuse of the 7.5.3 extracted cache;
changes cause re-extraction from a SHA256-verified archive. Archive path/link
checks and staging protect the source and existing output.

The converted copy retains `game/` byte-for-byte, including local saves, and
game-owned root sidecars, especially `characters/` and `firstrun` if present.
It omits the obsolete root `.exe`, `.dll`, `.py`, `.pyc`, `.sh` engine entrypoints
and source `renpy/`/`lib/`. Source links/junctions are refused for this profile
so writes in the converted copy cannot follow them back to the original.
The generated DDLC launcher changes to its own root before calling the
unmodified official launcher with the project path and original arguments.
This preserves relative file operations from Steam/desktop launch locations.
Real files are used: deleted characters stay deleted across relaunches. No
virtual filesystem, global `open` patch, story patch, save redirection,
handheld controls, GL4ES or Weston configuration is installed.

Save serialization and original DDLC restart semantics still need real-game
validation. Windows saves outside the installation are not automatically
imported. Keep a local backup of the original Windows save/persistent directory
and the converted copy before later-act tests. Do not use `--savedir` until
its compatibility with the original game's behavior has been established.
Rebuilding or extracting the initial ZIP again creates fresh copied character
state; continue play in the same writable extracted folder.

Package metadata keeps source `engine_version=6.99.12` separate from
`runtime_engine_version=7.5.3`, records the experimental profile and marks
`hardware_verification=pending`. Automatic artwork acquisition is skipped for
this opt-in mode. No original game content is bundled with the converter or
uploaded to CI. Converted output is an unofficial personal-use copy kept local.

## Windows GUI procedure (Stage A)

1. From this checkout, run:

   ```powershell
   .\.venv-win\Scripts\python.exe -m megcfbt.cli gui
   ```

2. Choose the **original** local game folder:
   `C:\Program Files (x86)\Steam\steamapps\common\Doki Doki Literature Club`.
   The inspection must show Ren'Py **6.99.12**, `NEEDS_TESTING`, and the
   **7.5.3 EXPERIMENTAL** runtime option. If it does not, stop and review the
   source layout; do not bypass identification by changing the title.
3. Set the output directory to a fresh writable folder outside the Steam
   installation, for example this checkout's `dist\ddlc-gui-test`.
   Keep ZIP packaging enabled and replacement/force disabled. Leave artwork
   unset. Do not choose a manual runtime for the automatic migration test.
4. Click **CONVERT**. **YES** confirms your own original DDLC 1.1.1 and selects
   checksum-verified full 7.5.3 migration. **NO** selects a manual runtime;
   **CANCEL** creates nothing. The warning explicitly says later-act behavior
   is unverified. Wait for the separate output folder and `*-linux-aarch64.zip`.
5. Keep the source unchanged. Keep the converted package local: do not attach
   it, its game scripts, `.chr` files, screenshots, or asset-bearing traces to
   GitHub, chat, AI tools, or CI. Report only reproduction steps and sanitized
   exception type/engine version if necessary.

## Steam Frame procedure (Stage A only first)

1. Copy the local ZIP to `/run/media/steamos/SD512`. In Frametop's graphical
   desktop, extract it to a fresh writable folder on that SD card. For the
   locally prepared `DDLC111-Frame-linux-aarch64.zip`, the folder is
   `/run/media/steamos/SD512/DDLC111-Frame` and the game data is under `payload/`.
2. Open a terminal **in the graphical desktop session**, with Steam running:

   ```bash
   cd /run/media/steamos/SD512/DDLC111-Frame
   bash ./install-to-steam.sh
   ```

   For a GUI-created package, substitute its extracted folder name. Use the
   existing non-Steam installer; no manual `shortcuts.vdf` edits are needed.
3. In Steam, open the added game's Properties. Leave Proton/forced
   compatibility off. Use the native launcher imported by the installer,
   with SteamLinuxRuntime_4-arm64 if Steam asks for the runtime.
4. Launch through Steam and confirm the warning/menu opens. Test basic
   keyboard/mouse navigation, audio, fullscreen/windowed mode, then exit and
   launch again from the same folder. A desktop `bash ./launch.sh` can help
   distinguish Steam configuration from game startup.
5. Stop and report Stage A results: menu yes/no, exit/relaunch yes/no, native
   runtime selected, and a sanitized error if applicable. SSH normally has no
   `DISPLAY`; an SSH-only “No available video device” is not a failed GUI test.
   Do not mark DDLC playable or fully supported after reaching the menu.

## Subsequent hardware checklist (after Stage A)

| Milestone | Verify on the same converted copy | Status |
| --- | --- | --- |
| A | Native menu, sound, exit and graphical relaunch | Pending |
| B | Dialogue, choices, poem input, save/load, quit/relaunch and Frame reboot restore | Pending |
| C | Later-act character-file creation/deletion, persistent act transitions, intentional restarts, ending, Steam/Frametop keyboard/mouse controls | Pending |
| D | Mod compatibility as a separate optional scope | Not included |

For C, verify the actual `payload/characters/` changes expected by the game's
story, including missing state after quit, relaunch and reboot. Check that
`payload/game/` and any game-created root sidecars remain writable. Confirm the
Windows original remains unchanged. If a specific API/path/restart failure is
demonstrated, investigate that smallest failure with a synthetic reproduction
before introducing compatibility code. Do not regenerate missing `.chr` files
or transplant third-party lifecycle patches speculatively.

## CLI and validation

The no-download dry run is available in both entrypoints:

```powershell
.\.venv-win\Scripts\python.exe -m megcfbt.cli build "C:\Program Files (x86)\Steam\steamapps\common\Doki Doki Literature Club" --output .\dist\DDLC111-Frame --experimental-ddlc-753-migration --dry-run
.\.venv-win\Scripts\python.exe -m renframe.cli build "C:\Program Files (x86)\Steam\steamapps\common\Doki Doki Literature Club" --output .\dist\DDLC111-Frame --experimental-ddlc-753-migration --dry-run --json
```

Remove `--dry-run` from the unified command to produce the local Frame ZIP.
The opt-in cannot be combined with a manual runtime or 7.4 fallback. Manual
runtime overrides keep existing validation: a different generation requires
the explicit CLI `--allow-renpy-version-mismatch` (unified) or
`--allow-version-mismatch` (RenFrame). GUI manual override alone does not
silently authorize migration to Python 3.

Automated tests use synthetic structures and stub launchers, including
character deletion/persistent-state changes across subprocess relaunches.
They do not execute original DDLC scripts. On Windows with Git Bash:

```powershell
$env:PATH = 'C:\Program Files\Git\bin;' + $env:PATH
.\.venv-win\Scripts\python.exe -m pytest -q --basetemp=build/pytest-all
.\.venv-win\Scripts\python.exe -m compileall -q megcfbt renframe rpgmframe
powershell -NoProfile -ExecutionPolicy Bypass -File .\build\build_windows.ps1
```

## Upstream and content policy

Ren'Py runtime license notices are retained in the local output; see the
[Ren'Py license](https://www.renpy.org/doc/html/license.html). This implementation
uses the official SDK, not unofficial wrapper binaries.
[DDLC-ARM-Linux](https://github.com/josepilas/DDLC-ARM-Linux) was an architectural
reference named in the issue. No wrapper code, PortMaster patches, or mod
template code was copied; no MPL-2.0 compatibility code is redistributed here.
The [Team Salvato IP guidelines](https://teamsalvato.com/ip-guidelines) apply to
users' original game content. No game downloads, decompiled scripts, converted
game releases, proprietary fixtures or asset-bearing CI artifacts are provided.
