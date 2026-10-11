# Steam Frame user testing, 2026-10-11

The user reported the following converted packages working on Steam Frame.
These are user hardware results, not automated conversion-only results.
Exact game versions, converter builds, gameplay depth and save/load coverage
were not supplied in this report. Do not infer completion of these games.

| Working package | Qualification |
| --- | --- |
| ADatewithDeath-frame | Reported working |
| Balatro-frame | Reported working |
| Brotato-frame | Reported working; earlier full-run result remains separately documented |
| DDLC-frame | Reported working; later acts and character-file transitions not specified |
| EverlastingSummer-frame | Reported working; release variant not specified |
| FearHunger2TERMINA-frame | Reported working |
| FearHunger-frame | Reported working |
| FindLoveorDieTryingByAudenChoWong-frame | Reported working |
| GrimmsHollow-frame | Reported working |
| HelpIMarriedASlut-frame | Reported working |
| hertearsweremylight-frame | Reported working |
| ImperialBureaucracyHero-frame | Reported working |
| KatawaShoujoHD-frame | Reported working |
| MayasMission-frame | Reported working |
| MyPigPrincess-frame | Reported working |
| SillyLinguineCatSimulatorDeluxeOnline-frame | Reported working; online features not specified |
| Slay the Spire 2-frame | Reported working; exact release and test coverage not specified |
| TheCatLady-frame | Works with keyboard/mouse; controller not recognized |
| TheSeaWolves-frame | Reported working |
| TheWitchsHouse-frame | Reported working |
| TotheMoon-frame | Reported working |
| Undertale-frame | Reported working; earlier second-savepoint and save/load result remains documented |
| VoidStranger-frame | Reported working |

## Reported limitations and investigation

| Game | User result | Investigation |
| --- | --- | --- |
| Cassette Beasts | Starts; keyboard/mouse works; controller not recognized; in-game textures/tiles/sprites disappear and reappear | Input routing and Godot 3 rendering remain unresolved; startup is not a gameplay compatibility pass |
| Cook, Serve, Delicious! 3 | Starts; laggy; controller unreliable | Native runner performance/input remain unresolved |
| Desert Child | Works with graphical glitches | Earlier runner failures no longer describe this tested package; rendering remains unresolved |
| Katawa Shoujo, non-HD | Would not convert | Installed Steam release is Ren'Py 6.16.5, using a computed version tuple and Python 2.7 lib layout; old profile recognized only 6.10.2. Extend the same vanilla 8.0.3 migration without HD overlays |
| Alone with My Stepsister | Could not download Ren'Py 8.4.2 | Source is nightly 8.4.2.25082901. Official stable 8.4.2 endpoints return 404. Offer the existing explicit complete 8.5.3 engine migration for identified Python 3.12 nightlies |
| Broken Sky | Default Plasma archive manager extraction failed; extracted package does not launch | Frame copy lacks payload launcher and runtime. Source uses nightly 8.4.1.25071908 and Live2D. A fresh migrated ZIP passed Frame CRC and PeaZip's bundled 7-Zip extraction; a separate startup crash resolved after installing the user's Linux ARM64 Cubism Core |

The Cat Lady's [official Steam page](https://store.steampowered.com/app/253110/The_Cat_Lady/)
describes keyboard controls and lists a keyboard requirement, with no controller
support feature. Lack of native controller recognition is consistent with that
interface; a keyboard-mapped Steam Input layout is the appropriate first check.

During inspection the Frame exposed virtual keyboard/mouse devices but no gamepad
device in `/proc/bus/input/devices`. Its installed Frametop input relay documents
that Frame controllers are visible to SteamVR rather than Linux evdev. This does
not prove the cause of either game's input failure: Steam Input routing, launch
context and each game's input API still need verification. No system input rules
or controller mappings were changed during this initial inspection.

## Converter changes and validation

Non-HD Katawa now uses the existing 8.0.3 compatibility profile, preserves original
resource archives and does not apply HD UI/source overlays. Identified Python 3.12
Ren'Py 8.4 nightlies now offer the same explicit full-engine 8.5.3 migration as
8.5 nightlies; they no longer attempt an unavailable stable 8.4.2 download or
silently graft a stable native runtime into a nightly engine.

Live2D is a shared RenFrame dependency. Games containing model files or a shipped
Cubism Core are detected. Convert requires an ARM64 Core, opens a vendor download
dialog when missing, and imports the user's downloaded SDK. Only Linux ARM64 Core
and its license notice are selected; Windows/x64 and Android builds are rejected.
The Core is hashed, cached, checked on reuse and copied into the output runtime.
No Core binary or vendor SDK is published in the repository or converter ZIP.

The user downloaded `CubismSdkForNative-5-r.5.zip` after accepting vendor terms.
Its ARM64 Core SHA-256 is
`3314987fd7d378cdfca785880384f87b5eece8c8e60336b6306ebee49f03a882`.
Frame startup reported Core 6.0.1. The isolated Broken Sky test copy remained
running, created its X11 window and rendered the initial important-notice screen
through Mesa Zink/Turnip. Gameplay, Live2D animation sequences and saves remain
unverified. The old partial extraction remains untouched; the cause of its
original extraction failure was not established.

The frozen Windows GUI completed Katawa, Alone with My Stepsister and Broken Sky
conversions. Archive CRC and payload launchers/runtime contents were checked.
Full automated regression tests cover the existing backends and SDK detection,
architecture rejection, cache corruption, source preservation and the popup gate.
