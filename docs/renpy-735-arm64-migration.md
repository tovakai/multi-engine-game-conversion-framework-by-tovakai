# Experimental Ren'Py 7.3.5 to 7.5.0 ARM64 migration

Exact Ren'Py 7.3.5 Python 2 distributions can opt into the existing complete
official Ren'Py 7.5.0 engine migration. This is engine-generic and experimental.
Pesterquest passed Stage A on Steam Frame; gameplay has **not** been verified. A successful
conversion or title screen is not a Playable result. Do not merge before hardware verification.

## Eligibility and packaging

The new 7.3.5 gate requires a real `game/` and `renpy/__init__.py`, a Python 2
library layout, and at least one high-confidence engine version hint from
`renpy/__init__.py`, `renpy/vc_version.py`, or `renpy/versions.py`. Those engine
hints must agree on exact 7.3.5 and generation 7. Weak evidence, conflicting
versions, missing Python 2 layout, and mixed Python 2/3 layouts do not qualify.
Layout evidence does not authenticate a game's release or prove compatibility.
7.3.4, 7.3.6, and other 7.3 releases still require a manual runtime.

7.4.x retains its existing 7.5.0 opt-in. Original DDLC 1.1.1 / 6.99.12 retains
its separate 7.5.3 gate and sidecar protections. Ren'Py 8 retains exact-version
Python 3 platform conversion.

The downloader verifies the official archive SHA256, checks the matched engine
version, Python 2 standard library, license, launchers, and AArch64 ELF runtime,
and records a cache manifest. Modified or incomplete caches are rebuilt from a
verified archive. The [official 7.5.0 checksum list](https://www.renpy.org/dl/7.5.0/checksums.txt)
identifies `renpy-7.5.0-sdkarm.tar.bz2` as
`33e1fcab5a9c80c0850a245e0ce634c098dcea27d8f58a523c80014ed27b94d0`.
[Ren'Py 7.5.0](https://www.renpy.org/release/7.5.0) continues Python 2.7 support.

Conversion stages the complete matched engine with the source `game/` payload.
It does not combine old engine Python modules with new graphics extensions.
Source links/junctions are refused in legacy migration mode to prevent writes
through to the original installation. Game-owned incompatible native extensions
remain blockers. Package metadata retains source 7.3.5 separately from runtime
7.5.0, with hardware verification pending.

## Local Pesterquest inspection

The installed Steam distribution identifies as 7.3.5 with high-confidence
`renpy/__init__.py` evidence. Its `lib/` contains `linux-i686`, `linux-x86_64`,
`windows-i686`, and `pythonlib2.7`. The Windows launcher's PE header identifies
32-bit x86. The 92 apparent game-owned shared libraries reported by the scanner
are inside `pesterquest.app/Contents/MacOS/lib/darwin-x86_64/Lib/`; sampled headers
identify x86-64 Mach-O libraries. They are part of the bundled macOS distribution,
not loose Linux ARM64 game extensions. No loose `.so`, `.dll`, `.pyd`, or `.exe`
was found under `game/`. The existing warning remains visible; no native-file
allowlist or scanner exception was added.

`game/` contains the asset archive, compiled scripts for the volumes, fonts,
images, translations, cache, and compiled settings. Root extras are platform
launchers, the macOS bundle, and promotional/icon PNGs. No required external
game-data sidecar was identified from this inspection. The output preserves
all `game/` files, excludes the old engine/platform bundles and root promotional
images, and does not apply DDLC's sidecar policy to Pesterquest. Hardware testing
must still establish whether any script expects external data or Steam hooks.
Packed scripts and dialogue were not exported or committed.

Local verification on Windows (2026-10-09): **184 pytest tests passed**, including
DDLC, 7.4, and Ren'Py 8 regressions; the Windows GUI executable built successfully.
The actual GUI conversion handler produced a local Pesterquest ZIP using an
automated, authorized Yes response. Every source file's SHA256 and modification
time remained unchanged, every copied `game/` file matched, and ZIP CRC and
launcher permission checks passed. No Windows binaries, macOS bundle, or source
x86 libraries were present in the migrated output. This verifies packaging,
not execution of the game on ARM64 hardware.

## Steam Frame Stage A result (2026-10-09)

The local ZIP was transferred privately over `ssh frame`/SCP and its SHA256
matched before extraction into a fresh test directory. A direct launch in the
authenticated Frametop session created a Pesterquest window and an active
audio stream. The user confirmed the visible menu, audible music, and working
menu controls. After the user confirmed the game's Quit prompt, the process,
window, and audio stream all disappeared normally.

The bundled installer added a non-Steam shortcut. Its settings did not force
Proton. Relaunch through Steam created a new native AArch64 Ren'Py process,
window in Steam's display session, and active audio stream; the user confirmed
the menu reopened. The engine reported 7.5.0.22062402 with the GL renderer,
and no exception appeared in the inspected startup diagnostics. The runtime's
direct dynamic-library dependencies resolved on the Frame.

**Status: Launches, Stage A passed.** Routes, dialogue/choices, save/load,
several volumes, persistence, and Steam achievements/hooks remain unverified.
No original game content, screenshot, or full game log was uploaded. The
converted package stays on the user's computer and Frame. Keep the PR unmerged
while the remaining hardware tests are pending.

## Windows GUI conversion

1. Start the current Windows converter and select the installed
   `Steam/steamapps/common/Homestuck Pesterquest` folder.
2. Confirm source version **7.3.5** and the **7.5.0 EXPERIMENTAL** runtime option.
3. Select a separate output folder and enable ZIP packaging. Click **CONVERT**.
4. **Yes** approves the matched full-engine migration. **No** opens the manual
   runtime chooser. **Cancel** leaves the source and output untouched.
5. Transfer the resulting `*-linux-aarch64.zip` privately to your own Frame.

Both command-line entrypoints also accept `--experimental-legacy-arm64-fallback`.
Use `--dry-run` for validation without downloads or output. Never upload the
converted ZIP or original files to GitHub or attach them to the PR.

## Transfer and launch on Steam Frame

1. Copy the ZIP using Frame Control file transfer, SCP, or USB. Use file transfer;
   the package is installed through its bundled Steam installer.
2. In Frametop, extract it into a permanent folder, for example
   `~/Games/Pesterquest/`. Keep Steam and SteamVR running.
3. Open a **graphical terminal in the extracted package folder**, where
   `install-to-steam.sh` and `launch.sh` are located. Run:

   ```bash
   chmod +x install-to-steam.sh launch.sh
   ./install-to-steam.sh
   ```

4. Accept Steam's non-Steam shortcut import. In the new shortcut's Properties,
   disable **Force the use of a specific Steam Play compatibility tool**.
   Launch the imported shortcut natively, with Proton disabled.
5. For a direct diagnostic launch, run `./launch.sh` from that same Frametop
   graphical terminal. Do not substitute the old Windows executable or run
   from an SSH shell without the graphical session environment.

The ZIP carries executable permissions and the wrapper repairs runtime execute
bits if a transfer loses them. Keep the original Steam installation unchanged.

## Hardware checkpoints

- **Stage A:** visible window, title/menu, background music, mouse/controller
  controls, exit, and graphical relaunch. Record only Launches if this passes.
- **Stage B:** route selection, dialogue, choices, save/load, quit, and relaunch
  with saved progress. Report brief gameplay separately from full verification.
- **Stage C:** several volumes, unusual story transitions, persistent state,
  and any Steam achievements/hooks exposed by the game.

If a stage fails, report the stage, visible error, and relevant short traceback
with dialogue and personal paths removed. Keep original game files and complete
logs local. A standard official Linux x86 distribution can be considered later
as a comparison diagnostic; it is not assumed to be downloaded and does not
provide native ARM64 support. Keep the PR unmerged until real hardware results.
