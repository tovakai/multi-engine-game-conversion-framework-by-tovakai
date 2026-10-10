Engine expansion feasibility — 2026-10-10

Implementation update: the four data-driven backends now exist and have native
startup evidence. See [native backend status and SDK setup](native-backends.md)
for the current implementation, limitations and Godot candidate retests. The
assessment below records the earlier discovery stage.

GameMakerFrame and LÖVEFrame are practical next backends. ConstructFrame can be
factored out of the existing Construct/NW.js path. AGSFrame is practical with
native plugin handling. WOLFRPGFrame has a WebAssembly candidate, but its data
preparation and runtime terms need separate investigation.

This assessment inspected 67 top-level folders under
C:\Program Files (x86)\Steam\steamapps\common, including Steam tools and shared
components. Original installations were read without executing or modifying
them. File signatures, container headers, Lua metadata, native-library
architectures, and upstream runtime documentation supplied the evidence.
GameMaker probes used separate copies on Steam Frame and isolated save folders.
Recognition, runtime availability, startup, and playable gameplay are distinct.

| Proposed backend | Installed examples | Assessment | Next implementation |
| --- | --- | --- | --- |
| GameMakerFrame | Undertale; Desert Child; Honey, I Joined a Cult; Cook, Serve, Delicious! 3?!; Void Stranger | Viable for VM exports. Native Undertale introduction rendered on Frame. | Detect FORM/GEN8 and CODE; pin a runner; preserve external assets; handle native extensions and saves. |
| LÖVEFrame | Balatro; Gravity Circuit | Viable Lua payloads, with native binding work. | Extract fused ZIP data; match LÖVE/LuaJIT; preserve fused behavior and save identity; resolve native Lua modules. |
| ConstructFrame | The Witch's House | Existing Construct 3 conversion reached its menu on Frame in earlier verification. Construct 2 has synthetic coverage. | Add a backend facade sharing NW.js downloads, extraction, launchers, compatibility repairs, and packaging. |
| AGSFrame | The Cat Lady | Viable engine/data separation, with plugin work. No new ARM64 game test here. | Handle embedded CLIB archives, numbered files, speech/audio/translations, and native plugins. |
| WOLFRPGFrame | The Crooked Man | Experimental browser-runtime route found. No game test here. | Investigate BrowserWoditor preparation, archive/key compatibility, encrypted fonts, local serving, and permitted distribution. |

The GameMaker inventory contains five exports with VM CODE entries and one
likely YYC export:

| Installed folder | WAD/bytecode field | CODE entries | Observation |
| --- | --- | --- | --- |
| Undertale | 16 | 6,272 | Native introduction rendered. |
| Desert Child | 17 | 3,348 | Runner loaded data and compiled shaders; screenshot showed an Error screen. |
| Honey, I Joined a Cult | 17 | 14,656 | VM candidate; not run here. |
| CookServeDelicious3 | 17 | 2,233 | VM candidate; not run here. |
| Void Stranger | 17 | 10,269 | VM candidate; not run here. |
| Colt Canyon | 17 | CODE absent | Likely YYC; exclude from an initial VM-only backend. |

[Butterscotch](https://github.com/ButterscotchRunner/Butterscotch) publishes a Linux
AArch64 runner and documents WAD 8–17 support, with compatibility still in
development. YYC and GMRT exports are outside that VM path. The runner uses
[AGPL-3.0](https://github.com/ButterscotchRunner/Butterscotch/blob/main/LICENSE);
retain notices and pin the distributed artifact/source.
[GMLoader-Next](https://github.com/JohnnyonFlame/gmloader-next) is another ARM64
route using an Android runner and a platform compatibility layer, adding a
separate runner-provisioning requirement.

The downloaded Butterscotch binary was ELF machine 183 (AArch64), and its help
command ran on Frame. ZIP SHA256:
cd3e07591da3bbf4cf0c6be989a0bfd7bf2e6ca0342f12f1e1b5550bf2f764c6.
This exploratory autobuild is not a production runtime pin.
Both probes executed 180 frames and produced screenshots. Undertale entered
room_introstory. Only data.win was supplied, so external music must be included
in future packaging. Desert Child logged missing/stubbed Steam/GOG and other
functions. Its VM loading does not establish playability. Gameplay, controls,
save compatibility, and performance remain unverified.

Version matching needs more than the stored 2.0.0.0 or WAD 17 fields.
[UndertaleModTool's format model](https://github.com/UnderminersTeam/UndertaleModTool/blob/master/UndertaleModLib/Models/UndertaleGeneralInfo.cs)
documents their reuse across modern releases. Inspect format features and
extension requirements before selecting a runner.

For LÖVE, [official distribution documentation](https://www.love2d.org/wiki/Game_Distribution)
describes ZIP-based payloads and executable fusion. Preserve the
[fused flag](https://www.love2d.org/wiki/love.filesystem.isFused), which affects
save placement and native-module lookup. Balatro supplies loose luasteam.dll and
https.dll. Its main script contains protected calls, but its HTTP worker also
imports HTTPS directly; optional fallback behavior needs testing. Gravity
Circuit requests LÖVE 11.4 and includes Linux luasteam.so and libsteam_api.so,
both x86-64. Its Steam initialization imports luasteam without a protected call.
Build matching ARM64 bindings using the [luasteam sources](https://github.com/uspgamedev/luasteam).
Frame Flathub metadata confirmed org.love2d.love2d 11.5 for AArch64; it was not
installed or used to run these games in this assessment.

For AGS, [upstream](https://github.com/adventuregamestudio/ags) supplies a Linux
engine and documents backward compatibility and plugin requirements. The Cat
Lady has an EXE-embedded CLIB footer, acsetup.cfg, TheCatLady.001/.002,
audio.vox, speech.vox, and translations. Its Windows plugins include AGSBlend,
AGSD3DVSync, and agsteam. The [plugin tree](https://github.com/adventuregamestudio/ags/tree/master/Plugins)
includes AGSBlend source. Verify rendering and Steam plugin handling in a native
build rather than disabling every plugin.

The [BrowserWoditor publisher](https://frostyhowl.com/browser-woditor/) provides
a WebAssembly port of the original WOLF runtime. Version 0.6.2.0 contains
woditor.wasm, JavaScript glue, fonts, and BrowserWoditor.dat, which must be inside
a prepared encrypted game archive. It requires HTTP serving. The bundled
license says the runtime is closed-source and describes game-rightsholder
distribution; the guidelines restrict standalone runtime redistribution.
Permission to ship it inside a general converter has not been established.
A user-supplied authorized runtime/export is an investigation path.
Its compatibility notes list Windows-dependent feature limitations, networking
limitations, and MP4 playback limitations. The Crooked Man also ships encrypted
.wolfx fonts. A different game's browser port does not prove this build works.
The package was inspected, not executed. ZIP SHA256:
50d525af26cfa597c402bfb527d1af66ca6b8db993e019079489e5e50cf91f20.

The Godot scan found seven exports with readable standard PCK headers and one
additional export with Godot-specific libraries and a nonstandard PCK header:

| Installed game | Evidence | Work needed | Priority |
| --- | --- | --- | --- |
| Brotato | 3.7.0; unencrypted; built-in GodotSteam | Existing matched runtime recipe, verified in earlier work. | Established baseline |
| Silly Linguine Cat Gambling Deluxe Online | 4.6.0; embedded PCK v3; unencrypted; GodotSteam; no listed extra extension manifests | Match a Steam-enabled ARM64 runtime and Steam context; extract PCK; test. No script rewrite identified. | First new candidate |
| Unnamed Space Idle | 4.7.2; PCK v4; unencrypted; GodotSteam; no listed extra extension manifests | Match a Steam-enabled ARM64 runtime and Steam context; test. No script rewrite identified. | First new candidate |
| Cassette Beasts | 3.5.1; PCK v1; unencrypted; GodotSteam | Select the game over WorkshopUtility; match/build the older Steam-enabled runtime. No script rewrite identified. | Next candidate |
| Looking Up I See Only A Ceiling | 3.6.0; GodotSteam; encrypted scripts | Matching keyed runtime or authorized decrypted data preparation. | More work |
| Find The Needle Demo | Nonstandard PCK header; GodotSteam, beltcore, terrain Windows libraries | Establish pack format/version and obtain additional ARM64 extension implementations. | More work |
| Until Then | 4.1.4; six packed extension manifests | ARM64 FMOD, GodotSteam, inkcpp, internal, jsonutils, threen; some project-specific. | Substantial work |
| Slay the Spire 2 | 4.5.1; .NET; FMOD/Sentry/Spine manifests | Existing separate managed/native workflow. | Separate project |

GodotSteam is solvable, as Brotato demonstrates. Its presence alone does not
exclude a game. The simplest new targets have portable, unencrypted data and no
detected additional extension manifests. They still need matching Steam-enabled
runtimes; Brotato's 3.7 binary is not an automatic match for other versions.
These are static candidates, not newly verified playable Godot games.
[GodotSteam upstream](https://github.com/GodotSteam/GodotSteam) now points to
[Codeberg](https://codeberg.org/godotsteam/godotsteam). Follow the upstream
location and pin new recipes/releases without changing the proven Brotato pin.

Two general detection repairs were implemented during this inventory: a unique
normalized folder-name match can select the main EXE/PCK over a companion
utility; stable built-in GodotSteam exports use the matching-module runtime
path. Ambiguous collections still require selection. The full suite passed
238 tests.

My proposed implementation order is GameMakerFrame with Undertale first,
ConstructFrame extraction, LÖVEFrame with native bindings, AGSFrame with plugins,
then the isolated WOLFRPGFrame investigation. In parallel, extend GodotSteam
recipes for the two modern candidates, followed by Cassette Beasts. Share source
preparation, architecture checks, runtime caching, Frame-aware launchers,
metadata, artwork, packaging, and Steam installation across the backends.
Require repeatable GUI/CLI conversion, native gameplay/input, and save/relaunch
verification before advertising support.
