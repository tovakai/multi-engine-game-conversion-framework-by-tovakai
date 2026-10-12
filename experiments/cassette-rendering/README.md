# Cassette Beasts graphical investigation

Status: baseline corruption reproduced on physical Steam Frame; forced depth
pre-pass gameplay evaluation pending. This is an experiment, not a verified
compatibility profile. Normal conversions and runtime releases remain unchanged.

## Reproduce privately

On Frame, use a **new** destination and the existing converted payload:

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
not transfer to B. The optional `launch-gles2.sh` is prepared but not yet tested.
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
| B depth pre-pass | true | empty | none | Override loaded; gameplay evaluation pending |
| GLES2 | not measured | original | not applicable | Prepared, not run |
| Zink/Turnip alternatives | not measured | not measured | not measured | Deferred until A/B results |

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

Validation: 36 experiment/Godot runtime/provisioning tests passed. First test run
failed at pytest temporary-directory setup due to filesystem permissions; rerun
with an explicit dedicated worktree test directory passed (one cache-write warning).
