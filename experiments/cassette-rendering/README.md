# Cassette Beasts graphical investigation

Status: the combined Zink `norp` + forced depth pre-pass configuration passed
user-confirmed five-minute gameplay, transitions, tutorial battle and save/load
on physical Steam Frame. A narrowly matched experimental conversion profile is
implemented; fresh frozen-GUI ZIP hardware acceptance is pending. Runtime releases
and the existing control conversion remain unchanged.

## Reproduce privately

On Frame, use a **new** destination and the existing converted payload:

For standalone use, copy `rpgmframe/godot_compatibility.py` beside `prepare.py`
and `probe.gd`. In a repository checkout the helper is imported directly.

```sh
python3 prepare.py /path/to/control/payload /path/to/new/comparison
DISPLAY=:0 /path/to/new/comparison/launch-baseline.sh --print-fps
# Exit A before starting B.
DISPLAY=:0 /path/to/new/comparison/launch-depth-prepass.sh --print-fps
```

The tool copies the payload into three independent packages (about 3.2 GB for
the tested build), hashes the control before/after, and copies existing saves and
settings into independent XDG profiles. No hard links or symlinks share writable
files. Each trial starts from the same original save/settings; progress in A does
not transfer to B. The optional `launch-gles2.sh` was tested and is not usable.
The only rendering change in B is the two depth pre-pass settings, in
`payload/game/override.cfg`, beside the PCK. Existing override text and unrelated
Godot Variant values are preserved; ambiguous duplicate depth keys/sections are
rejected. All launchers explicitly choose their renderer and record logs, graphics
environment and engine FPS when `--print-fps` is supplied.

Choose the display/session used by the control (the measured session was `:0`).
Do not compare host and Frametop containers as if they were the same environment.
For an independent effective-settings probe in either package:

```sh
DISPLAY=:0 /path/to/new/comparison/launch-baseline.sh --script /path/to/new/comparison/probe.gd
DISPLAY=:0 /path/to/new/comparison/launch-depth-prepass.sh --script /path/to/new/comparison/probe.gd
```

This exits without gameplay. `prepass_expected_from_source` applies Godot 3.5.1's
renderer matching rule; it is not GPU frame instrumentation. GLES2 does not use
the GLES3 pre-pass, so this field must not be interpreted as a GLES2 render pass.
The project also specifies `user://custom_settings.cfg` as a later project
settings override. A user-supplied file there could supersede these settings;
always inspect the effective-settings probe rather than assuming the merge won.

## 2026-10-12 experiment journal (UTC)

Feature branch: `feat/cassette-depth-prepass`, based on local
`integration/working-main` at `dfff741`. Existing release checkout and dirty
Celeste/research files were preserved with an isolated worktree.

Control: `/run/media/steamos/SD512/games/Dont work/CassetteBeasts-frame/payload`.
Trial root: `/home/steamos/tovakai-diagnostics/cassette-rendering-20261012`.
Game: Cassette Beasts 1.8.3; Godot PCK exported for 3.5.1.

Runtime recipe: `godot-3.5.1-godotsteam-3.30-steamworks-1.62-frame-arm64-v1`.
Engine version: `3.5.1.stable.custom_build.6fed1ffa3`; native `aarch64` Frame.
Binary SHA-256: `dff499fb712d0d8b0777d4171d0fcf89164dbf8bc6a841cc9ce9239d74bb9884`.
Source: Godot `6fed1ffa313c6760fa88b368ae580378daaef0f0`, GodotSteam
`f73d138b56fe971a940dd0498e8b9d0fc8fdcffd`; existing compatibility patches are
Steam dictionary adapter, release-safe Variant missing-method guard and native
networking helpers. No new engine changes/builds.

The installed launcher does not explicitly force Zink, but the host GL driver is
Zink over Turnip. `glxinfo -B`: Mesa `26.3.0-devel (git-abc426bb62)`;
GL vendor `Mesa`; renderer
`zink Vulkan 1.4(Turnip Adreno (TM) 750 (MESA_TURNIP))`.
Both engine probes report GLES3 and a 1920×1080 window.

| Trial | Effective enable | Exclusion list | Matching renderer substring | Result |
| --- | --- | --- | --- | --- |
| A baseline | true | PowerVR,Mali,Adreno,Apple | Adreno | Pre-pass excluded; background corruption reproduced |
| B depth pre-pass | true | empty | none | Override loaded; user reports equally bad corruption |
| C GLES2 | true (GLES3-only setting) | original | not applicable | Worse; menu backgrounds also missing; unsupported shaders |
| D Turnip sysmem | baseline GLES3 | original | Adreno | User reports same as A/B |
| E Zink sync | baseline GLES3 | original | Adreno | Worse; fewer textures |
| F Zink norp | baseline GLES3 | original | Adreno | Terrain restored; trees/similar textures still flicker (partial improvement) |
| G Zink norp + depth | true | empty | none | User-confirmed five-minute gameplay, transition, battle and save/load pass |

A settings probe: 21:19:38. A gameplay launch: 21:20:23.
User described background textures flickering out, leaving outlines of 3D objects.
Private `baseline-first.png` shows missing terrain/background surfaces with
visible outlines and some surviving tree/player textures. This is broader than
billboard invisibility; one screenshot cannot distinguish failed texture sampling
from missing surface color passes. Baseline engine FPS logging includes about
10–11 FPS in the captured gameplay period, versus 53–60 FPS earlier; no controlled
performance conclusion follows from comparing different scenes.

During the switch, B briefly overlapped A because the first exact-process stop
command failed. A was then stopped by its exact diagnostic executable path.
Exclude overlap from timing/performance comparisons. No control process or files
were changed. Probe shutdown produces resource-leak warnings after early exit;
these are diagnostic shutdown observations, not proof of a gameplay failure.

The preparation receipt records SHA-256 hashes and `control_unchanged=true`.
Private game files, saves, screenshots and raw logs stay on Frame/in ignored local
build storage. Only code, hashes and diagnostic summaries belong in Git.

## Interpretation and next gate

The [Heroic report](https://github.com/Heroic-Games-Launcher/HeroicGamesLauncher/issues/5637)
motivates the test but its claimed root cause is not established for this runtime.
[Godot 3.5.1 renderer code](https://github.com/godotengine/godot/blob/3.5.1-stable/drivers/gles3/rasterizer_storage_gles3.cpp#L7743)
checks **GL_RENDERER**, not GL_VENDOR, for the exclusion substrings. The measured
Zink renderer therefore matches Adreno even though vendor is Mesa.
[Project settings loading](https://github.com/godotengine/godot/blob/3.5.1-stable/core/project_settings.cpp#L356)
reads the main-pack directory override; executable-adjacent placement would be
wrong for this launch mode.

Require user-confirmed five minutes of actual movement, terrain/sprite stability,
area transitions, battles and save/load before claiming graphical compatibility.
If B succeeds, implement a narrow Cassette profile in the converter, test profile
detection/override preservation/ZIP contents, and verify a fresh frozen Windows
GUI conversion on physical hardware. If B fails, run GLES2 and bounded driver
comparisons, then inspect depth/shader behavior and original engine customizations.
Controller handling remains a separate investigation. Do not merge or mark fully
verified based on startup or the settings probe.

### Failed depth and GLES2 experiments

User-confirmed B: "It looks pretty much equally bad." Private `depth-first.png`
also shows broad absent terrain/background surfaces; player and tree remain
visible. Enabling the pre-pass is therefore **not sufficient** to resolve the
corruption. This does not prove pre-pass is irrelevant to every possible sprite
issue, and does not establish a replacement root cause.

User-confirmed C: worse, fewer textures, including missing menu background.
Engine diagnostics report GLES3-only `uint`, `textureSize(sampler2D, int)` and
`sampler2DArray`, unsupported 3D textures/texture arrays, and resulting invalid
GL texture operations. Rewriting those resources would exceed a minimal fallback.
Normal GLES3 A/B logs contain the known X11 keyboard-layout error and deprecated
HingeJoint warning, but no captured shader compile errors.

`rendering-summary-20261012.json` contains effective-setting probes and FPS/error
summaries. FPS statistics include menu/loading and cannot compare gameplay speed.
`shader-inventory-20261012.json` records a read-only lexical inventory: 53 shader
resources; 18 mention uint, 7 textureSize, 2 sampler2DArray, 13 DEPTH_TEXTURE and
15 depth_draw_alpha_prepass. Counts may include comments. No game resources or
shader source are copied into Git.

### Bounded driver comparisons

Prepare a second **new** destination using the same control and original saves:

```sh
python3 prepare.py /path/to/control/payload /path/to/new/drivers --variants turnip-sysmem zink-sync zink-norp
DISPLAY=:0 /path/to/new/drivers/launch-turnip-sysmem.sh --print-fps
DISPLAY=:0 /path/to/new/drivers/launch-zink-sync.sh --print-fps
DISPLAY=:0 /path/to/new/drivers/launch-zink-norp.sh --print-fps
```

Exit each game before the next. These retain baseline's original override and
change one driver flag. Installed
driver binary strings contain `sysmem`, `sync` and `norp`. The
[Mesa Turnip documentation](https://docs.mesa3d.org/envvars.html#turnip-driver-environment-variables)
defines `TU_DEBUG=sysmem` as forced system-memory rendering. The
[Mesa Zink documentation](https://docs.mesa3d.org/drivers/zink.html#debugging)
defines `ZINK_DEBUG=sync` as full barriers before draws/dispatches, and `norp` as
disabling render-pass optimizations. Driver root:
`/home/steamos/tovakai-diagnostics/cassette-drivers-20261012`.

The [developer's technical article](https://www.cassettebeasts.com/category/technical/)
confirms GridMap batching/chunk streaming and custom GridMap engine optimizations.
That is relevant background, not evidence that missing customizations cause this
corruption. Initially no original Linux executable was located. The user then
installed the official game through Steam on Frame. Static metadata now records
the original x86_64 Linux binary SHA-256
`57b48157b5576abdd391b06a41548ce222cac574f5ae8dfb16f6b39bb22e034f`, size
46,104,344 bytes, engine strings `3.5.1.stable.custom_build`, and available ELF
symbol table. It includes the expected GLES3 and GridMap implementation symbols.
The replacement is confirmed as ELF AArch64. Static strings/symbols do not
establish which custom engine patches are present. Original Windows metadata is
also recorded; no proprietary executable is copied into Git.

### Partial improvement and combined trial

F user report: all background textures are present; trees/similar textures still
flicker. That supports testing the pre-pass **on top of norp**, even though
pre-pass alone failed. G was prepared from the same untouched control and original
save/settings in `/home/steamos/tovakai-diagnostics/cassette-combined-20261012`.
The probe confirms `ZINK_DEBUG=norp`, GLES3, empty exclusion list and enabled
pre-pass at 1920×1080. Private screenshots show restored terrain and visible
trees/player in one frame; they cannot establish absence of temporal flicker.
Reproduction: use `--variants zink-norp-depth` with a fresh destination, then
`launch-zink-norp-depth.sh --print-fps`.

An independent software-renderer availability check failed on the host: Zink
requested a CPU Vulkan device but none was installed; explicit llvmpipe selection
failed GLX context creation. The Frametop container has llvmpipe Mesa 26.2.3,
whereas the tested host uses Mesa 26.3.0-devel. No software game trial was run;
a container comparison would need a matched container GPU control to avoid
confounding driver/session changes.

Validation: 37 experiment/Godot runtime/provisioning tests passed. First test run
failed at pytest temporary-directory setup due to filesystem permissions; rerun
with an explicit dedicated worktree test directory passed (one cache-write warning).
