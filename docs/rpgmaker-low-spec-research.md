# Deferred research: RPG Maker on low-spec hardware

Research date: 2026-10-15.

Status: **parked for future exploration**. This is a feasibility note, not an
implementation plan committed to a release. Any implementation should start on
a separate experimental branch. No Pi compatibility or performance improvement
has been validated by this research.

## Goal and current architecture

Explore optional RPGMFrame settings and conversion-time optimizations that let
owned games run on less powerful hardware, ideally including some games on a
Raspberry Pi 3B. Related discussion considered image downscaling for RenFrame;
RPG Maker needs different treatment because tiles, sprite sheets and game logic
often depend on exact pixel dimensions and update timing.

The current repository already has three runtime paths:

| Engine family | Backend | Initial research priority |
| --- | --- | --- |
| RPG Maker 2000/2003 | EasyRPG | First: strongest initial Pi candidate |
| RPG Maker XP/VX/VX Ace | mkxp-z | Second: runtime tuning and script profiling |
| RPG Maker MV/MZ | NW.js | Third: rendering, memory and plugin experiments |

This priority is an engineering assessment, not a hardware test result. Existing
Steam Frame compatibility reports do not establish Raspberry Pi compatibility.
ARM64 binaries also require a matching 64-bit userspace and compatible native
libraries; an ARM CPU alone is insufficient.

Relevant integration points are `rpgmframe/easyrpg_backend.py`,
`rpgmframe/mkxp_backend.py`, `rpgmframe/launchers.py`, and
`rpgmframe/compat.py`. The mkxp backend already writes `mkxp.json`, migrates legacy
settings and enables path caching. It pins runtime revision `37a04d1` at the
time of inspection. New settings must be checked against that runtime rather
than copied blindly from upstream development documentation.

## RPG Maker 2000/2003: preserve assets and tune EasyRPG

These games normally render at 320x240. The first preset should preserve that
logical resolution and original graphics, use inexpensive nearest-neighbour or
integer scaling, and test a modest physical display resolution. EasyRPG warns
that changing logical resolution can cause glitches or break games.

Verify the packaged runtime uses an optimized release build. Measure slow maps,
battles, transitions and audio before changing asset data. Downscaling already
small tiles and character sheets is unlikely to be the best first tradeoff.

EasyRPG exposes frame limiter and vsync options, but their availability does not
prove a lower limit preserves all game timing. Treat timing changes as separate
experiments. Complex events and Windows engine extensions remain potential
compatibility or CPU bottlenecks.

Source: [EasyRPG manual](https://easyrpg.org/player/manual/).

## XP/VX/VX Ace: tune mkxp-z before rewriting assets

Upstream mkxp-z exposes frame skipping, scaling filters, high-resolution asset
replacement and framebuffer scaling controls. A conservative preset could keep
native rendering resolution, avoid costly upscale filters and test `frameSkip`
when rendering falls behind. Several inexpensive settings are already upstream
defaults, so benefits depend on the game's configuration.

Do not assume high-resolution scaling factors support fractional downscaling
correctly. Do not treat a maximum texture-size setting as an asset resizer.
Inspect the pinned implementation before using either for this purpose.

Ruby scripts can dominate performance: parallel events, lighting, particles and
repeated bitmap drawing may remain slow even after reducing textures. Profile
these and use narrow, per-game recipes where necessary. Automatically disabling
unknown scripts or events could remove gameplay.

Avoid a blanket fixed-framerate override: movement, waits and scripts can depend
on update counts. Frame skipping and frame-rate changes require gameplay timing
checks, not just an FPS counter.

Source: [mkxp-z configuration](https://github.com/mkxp-z/mkxp-z/blob/dev/mkxp.json).

## MV/MZ: reduce drawing costs without slowing simulation

Potential experiments, each gated by detected engine/core/plugin versions:

- Draw at 30 FPS while retaining normal game updates. MV's official core
  separates its timed update loop from scene rendering, providing a plausible
  hook. MZ and plugins need independent validation; limiting the whole loop can
  slow movement, timers or combat. Render-only limiting will not solve CPU-bound
  game logic.
- Reduce actual render-target resolution while preserving logical coordinates,
  viewport behavior and input mapping. A smaller window or CSS scale alone does
  not establish reduced internal rendering cost.
- Reduce known optional lighting, blur, particles and full-screen filters through
  explicit game/plugin recipes. Preserve effects that communicate gameplay.
- Tune image caches and texture lifetimes, balancing memory savings against
  repeated decoding, disk reads and transition pauses. Inspect existing engine
  management before adding a second cache policy.
- Verify hardware acceleration with the selected NW.js version and Pi driver.
  Generic Chromium flag collections or disabling the GPU are not established
  performance fixes.

A browser-based launch mode is another research option for compatible games,
but is not automatically lighter than NW.js. Plugins can depend on Node and
NW.js APIs, filesystem access and desktop save behavior.

Sources:

- [MV SceneManager](https://github.com/rpgtkoolmv/corescript/blob/master/js/rpg_managers/SceneManager.js)
- [MV Graphics](https://github.com/rpgtkoolmv/corescript/blob/master/js/rpg_core/Graphics.js)
- [MV ImageCache](https://github.com/rpgtkoolmv/corescript/blob/master/js/rpg_core/ImageCache.js)
- [MZ Graphics implementation](https://developer.rpgmakerweb.com/rpg-maker-mz/Graphics.js.html)
- [Pixi performance guidance](https://pixijs.com/7.x/guides/production/performance-tips)
  (general guidance; adapt to the game's bundled Pixi version)
- [NW.js manifest documentation](https://nwjs.readthedocs.io/en/latest/References/Manifest%20Format/)

## Selective asset optimization

Large backgrounds, parallaxes, portraits and video are better initial candidates
than tilesets, character sheets, windowskins or fonts. Preserve logical sizes,
source rectangles, transparency, animation grids and plugin expectations. Some
games encrypt or archive assets, requiring format-aware processing.

For scale, raw RGBA pixel data for a 1920x1080 image is about 7.9 MiB; at 960x540
it is about 2.0 MiB. That 75% pixel reduction is not a prediction of total game
memory savings. Decoding buffers, CPU canvases, GPU textures and caches can add
other allocations. Stronger PNG compression alone generally reduces storage,
not decoded pixel memory.

Video/audio transcoding could reduce storage or decoding work, but must preserve
supported codecs, looping, synchronization and any transparency requirements.
Do not remove apparently unused files automatically: scripts and plugins can
construct asset paths dynamically.

Source: [MV Bitmap implementation](https://github.com/rpgtkoolmv/corescript/blob/master/js/rpg_core/Bitmap.js).

## Suggested sequence when this work resumes

1. Establish an unchanged baseline on actual Pi 3B hardware, recording OS,
   userspace architecture, runtime, graphics driver and acceleration status.
2. Add diagnostics for engine/core version, plugins and oversized assets; measure
   process memory, frame times and loading pauses.
3. Test conservative EasyRPG and mkxp-z presets before asset transformations.
4. Prototype MV render-only frame limiting, then evaluate MZ separately.
5. Add selective asset changes and per-game effect recipes only where measured
   bottlenecks justify them.

Compare each preset with the unchanged conversion across movement, menus,
battles, slow maps, transitions, input, audio, save/load and long sessions.
Record actual movement/timer behavior as well as FPS. Keep the source untouched,
make optimization opt-in, and record settings and transformed assets in package
metadata so results can be reproduced.

The first useful milestone is one measured Pi 3B gameplay success, followed by a
repeatable preset. No general low-spec or Raspberry Pi support claim should be
made from successful conversion or a title-screen screenshot alone.
