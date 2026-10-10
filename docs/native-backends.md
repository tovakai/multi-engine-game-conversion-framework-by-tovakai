# Native data-driven backends

GameMakerFrame, LÖVEFrame, ConstructFrame and AGSFrame are routed through the
same inspection, GUI, package metadata, artwork and ZIP flow as RenFrame.
Detection and a successful package build are distinct from gameplay validation.

| Backend | Accepted exports | Runtime | Current hardware evidence |
| --- | --- | --- | --- |
| GameMakerFrame | FORM/GEN8 data with VM CODE, WAD 8–17 | ARM64 Butterscotch | Undertale opening scene; Void Stranger startup; Desert Child still has runner gaps |
| LÖVEFrame | `.love`, fused EXE ZIP, or Lua project | LÖVE 11.5 / LuaJIT and required ARM64 modules | Balatro main menu; Gravity Circuit language screen with Steam initialized |
| ConstructFrame | Construct 2/3 packaged web exports | Shared ARM64 NW.js backend | The Witch's House main menu from the earlier native conversion test |
| AGSFrame | CLIB game library or appended executable data | AGS 3.6.2.21 with plugin capabilities | The Cat Lady opening sequence through the generated launcher |

GameMaker YYC/GMRT native exports cannot use a VM runner. Newer WAD 17 features,
native extensions and unimplemented runner functions can still prevent gameplay.
The pinned runner patch fixes `ds_list_set(id, position, value)` accepting the
wrong argument count; it applies to all games using that function. Steam support
in this runner currently consists of offline stubs.

LÖVE packaging replaces incompatible embedded Linux modules with matching ARM64
modules from the runtime. It refuses missing replacements rather than producing
a known broken package. LuaJIT/Lua 5.1 modules must match the runtime's Lua ABI.
The Steamworks compatibility adapter replaces the removed `RequestCurrentStats`
call with a real request for the current user's stats; it does not fake success.

AGS retains an original EXE containing CLIB as data and preserves numbered
volumes, audio, speech and translations. It never executes that Windows EXE.
Runtime `engine-capabilities.json` lists `builtin_plugins` and `stub_plugins`;
other requested plugins require native `.so` implementations. Offline plugin
fallbacks are reported in package warnings. The identified Windows D3D vsync
hook is matched by its SHA-256 and replaced by native OpenGL vsync, independently
of the game name. Unknown variants remain subject to the plugin requirement.

## Configure an SDK once

Select a runtime bundle using the GUI runtime button or `--backend-runtime`.
The bundle root contains `butterscotch`, `love`, or `ags`, its native libraries,
license notices and optional capability manifest. Executables and ELF libraries
are checked for ARM64. Failed builds preserve an existing output directory.

For repeated conversions, set `GAMEMAKERFRAME_RUNTIME`, `LOVEFRAME_RUNTIME`, or
`AGSFRAME_RUNTIME`. Alternatively place SDKs in:

- Windows: `%LOCALAPPDATA%/tovakai/cache/runtimes/native/{gamemaker,love,ags}`
- Linux: `~/.cache/tovakai/runtimes/native/{gamemaker,love,ags}`
- Custom parent: `MEGCFBT_NATIVE_RUNTIME_DIR/{gamemaker,love,ags}`

The new SDKs can be built from pinned public source on Linux ARM64:

```sh
python -m megcfbt.native_sdk gamemaker --work-dir /path/build/gamemaker \
  --output /path/sdks/gamemaker --distrobox tovakai-godot-build
python -m megcfbt.native_sdk ags --work-dir /path/build/ags \
  --output /path/sdks/ags --distrobox tovakai-godot-build
python -m megcfbt.native_sdk love --work-dir /path/build/love \
  --output /path/sdks/love --distrobox tovakai-godot-build \
  --steam-api /path/to/compatible/arm64/libsteam_api.so
```

Omit `--distrobox` to use the native host toolchain. SDK builds require Git,
CMake, Make/GCC, SDL2, OpenGL and appropriate media development libraries.
For Ubuntu 22.04 these include `libsdl2-dev`, `libfreetype6-dev`, `libogg-dev`,
`libtheora-dev`, `libvorbis-dev`, and for LÖVE `libopenal-dev`, `libmodplug-dev`,
`libmpg123-dev`, `libluajit-5.1-dev`, `libssl-dev`, `libcurl4-openssl-dev`.
The builder does not install host packages. Native SDK bundles need the
corresponding runtime libraries on the target; Steam Frame currently supplies
the tested SDL/media dependencies.

## GodotSteam candidates

Godot 4.6.0 and 4.7.2 use checksum-pinned upstream ARM64 release templates and
their matching Steam API library. These are export runtimes rather than editors.
Runtime capability `pack_loading: adjacent` selects a PCK beside `godot.arm64`
as `godot.pck`; this supports templates that reject `--main-pack`.

Godot 3.5.1 has a source-build recipe using pinned Godot/GodotSteam/Proton sources,
the Frame Steam library, a release-safe Variant guard and the legacy dictionary
initialization API. That adapter forwards real Steam results; it does not fake
successful initialization. It does not apply
the Godot 3.7 CanvasItem patch. On Windows, select a prepared matching bundle;
native Linux ARM64 can build/cache this recipe automatically.

The small source-backed `libframe_steam_env.so` helper preserves the selected
Frametop graphics environment across real Steam initialization. It is enabled
only for Frametop launches. This prevents early Steam initialization from moving
Godot's window to another X server. Nested API calls and unguarded launches were
tested on Frame, and Steam return values and service state remain intact.

On 2026-10-10, native tests reached Silly Linguine's startup screen, Unnamed Space
Idle's introduction and Cassette Beasts' 3D title screen through generated
converter packages and launchers. The legacy initialization adapter removed
Cassette Beasts' Steam initialization error. Its old X11 backend can report a
keyboard-layout bounds warning under Xwayland and then use its QWERTY fallback.
The fresh Unnamed Space Idle test profile reached its introduction without the
save recovery prompt seen after repeatedly interrupting the reused test profile.
Automated X11 key injection did not reliably advance these screens in Frametop;
keyboard/controller interaction through Steam still needs device testing.
Online/co-op/workshop, save round trips and complete gameplay remain unverified.
Intro/menu screenshots are not full-game compatibility certification.

Final local verification: 264 tests passed on Windows, with two link tests
skipped for missing symlink privileges. Escaped links and recursive links were
also rejected in direct Linux checks on Frame. All three canonical native SDK
source builds completed on Frame. The rebuilt Windows GUI passed its hidden
startup and bundled backend/helper checks.

Upstream sources: [Butterscotch](https://github.com/ButterscotchRunner/Butterscotch),
[LÖVE](https://github.com/love2d/love), [luasteam](https://github.com/uspgamedev/luasteam),
[lua-https](https://github.com/love2d/lua-https),
[AGS](https://github.com/adventuregamestudio/ags),
[GodotSteam](https://codeberg.org/godotsteam/godotsteam), and
[Valve networking headers](https://github.com/ValveSoftware/GameNetworkingSockets).
