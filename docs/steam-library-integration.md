# Steam library integration on Frame

Extract the converted ZIP, keep Steam / SteamVR running, and run
`./install-to-steam.sh`. Use `--help` for a short description.

**Add as non-Steam game is the recommended installation method.** Original-entry
linking and asset deduplication are **[experimental]** optional features. Hardware
coverage is incomplete, especially Steam updates and storage removal; retain
the conversion ZIP for recovery. Their unfinished checks gate promotion out of
experimental status, rather than v0.1.1.0 publication.

**The original Steam game must be installed through Steam on this Steam Frame
before library linking is available.** Owning it, or installing it on another PC,
is not sufficient. The installer discovers mounted secondary Steam libraries
through Steam's `libraryfolders.vdf`. It checks the matching application manifest,
exact AppID, fully installed state and nonempty local game directory. A manifest
alone does not prove ownership. Incomplete, stale and unreliable metadata are
reported separately; ownership remains unknown.

If the original is missing, choose **Install original game through Steam, then
link**. This opens `steam://install/<validated-AppID>` in Steam. Complete Steam's
installation, then rescan or rerun this same extracted installer. No regeneration
or transfer is needed. The converter never downloads the original game itself.

## Automatic linking

Choose the explicitly labeled **[experimental]** original-entry option to opt in.
The installer reads the exact
custom launch options through Steam's live `RegisterForAppDetails` callback
(`strLaunchOptions`), saves them in its recovery record, and calls
`SteamClient.Apps.SetAppLaunchOptions` with the validated AppID and wrapper command.
It reads the options back and reports configuration success only on an exact
match. There is no copying, pasting or editing Steam Properties.

The bridge uses an **already existing** loopback CEF debugging endpoint, probing
ports 8080, 1337 and 9222 and the Steam SharedJSContext. It does not enable debugging,
open a listener, install plugins, change Steam binaries/wrappers or restart Steam.
If no safe live interface works, linking is unavailable and the installer offers
non-Steam installation. It never edits `localconfig.vdf` or falls back to manual
launch-option entry. Enabling CEF on a client that lacks it is separate setup
research; no restart or patch is introduced as a hidden prerequisite.

The wrapper consumes `%command%`, checks actual inherited Steam identity, and
executes the converted launcher without passing Steam's original executable as
game arguments. It accepts matching Steam-provided identity fields or the actual
ancestor SteamLaunch AppID when `SteamAppId` is absent. It preserves inherited Steam context and does not fabricate
ownership or successful Steamworks calls. Steam Input and original-entry playtime
may work, but require device verification. Steam initialization is not proof of
achievement support. Offline Steam stubs remain offline stubs.

**configured** means live launch-option readback succeeded. **launch-observed** means the
wrapper was reached, not that the game successfully initialized or gameplay was
verified. Run the installer again and choose **Verify existing link** to inspect
the receipt, package availability, live options and current local installation.
While the game is running, verification checks the actual `/proc/<pid>/exe`,
matching Steam context and the converted Linux AArch64 ELF. Wrapper execution
alone never establishes game-runtime success. Steam does not get killed, restarted, or edited through
configuration files.

## Backend capability matrix

| Backend | Shared linking | Identity and limitations |
| --- | --- | --- |
| MonoFrame / Celeste (legacy CelesteFrame accepted) | Automatic native, device acceptance pending | Hash-gated vanilla Steam XNA 1.4.0.0 profile, AppID 504230; existing user FMOD and controller launcher retained |
| MonoFrame / Stardew Valley | Automatic native, device acceptance pending | Hash-gated Steam 1.6.15 .NET 6 profile, AppID 413150; Steam online features remain unverified |
| GameMakerFrame | Automatic native, device acceptance pending | Exact source Steam manifest required; offline runtime stubs gain no achievements |
| LÖVEFrame | Automatic native, device acceptance pending | Exact source Steam manifest required; no general Steamworks guarantee |
| AGSFrame | Automatic native, device acceptance pending | Exact source Steam manifest required; no general Steamworks guarantee |
| RenFrame | Deferred | Non-Steam supported; Ren'Py/runtime variants need dedicated context acceptance |
| RPGMFrame | Deferred | Non-Steam supported; NW.js, mkxp-z and EasyRPG contracts need separate acceptance |
| Godot / GodotSteam | Deferred | Non-Steam supported; genuine APIs, limited legacy bridges and offline stubs must remain distinct |
| UnityFrame / Hollow Knight | Deferred | Existing Windows ARM64 / ARM64 Proton launcher and prefix remain unchanged |
| Slay the Spire 2 experiment | Existing specialized integration | Two-stage preparation/finalization and authentic Steam launch chain remain unchanged; not routed through the shared native wrapper |

Loose `steam_appid.txt`, command-line overrides and title matching do not authorize
shared linking. Source manifests or the explicit hash-gated profiles supply
identity. Conflicting identities fail closed. Other-store games and packages with
no trustworthy identity can always use the non-Steam workflow.

Package metadata keeps the historical source `engine` field (for example,
`monogame`) and separately records the canonical converter `backend` (for example,
`monoframe`). The unified router preserves backend-produced Steam manifest
evidence, runtime AppID, audited profile and conversion provenance in both the
wrapper and payload metadata. Runtime AppIDs alone never establish Steam identity.
Exact historical backend names remain supported; generic engine names never
establish a backend by themselves.

Conversions from the affected development candidates, including
`0.1.1.0.dev180+g9b17575828f8`, must be reconverted with a fixed converter and the
new ZIP transferred/extracted. Those ZIPs lost backend identity and Steam evidence;
rerunning their old installer or editing an AppID cannot safely recover that
provenance. Keep existing saves and user data when selecting the new output.

## Repair and restoration

Records live at `~/.local/share/megcfbt/steam-links/<AppID>.json`, outside the
original game directory. The stable `launch-<AppID>.sh` wrapper lives there too,
so a moved/deleted conversion can still produce repair guidance. Records contain
package and launcher paths, AppID,
converter identity, profile, mode, generated options, exact live previous
options, installation paths, status and timestamps. Records are atomically
written before wrapper activation. A failed operation retains recovery data.

Rerunning the installer offers verification, repair, restoration, a separate
non-Steam shortcut, or cancellation. One record per original AppID prevents
duplicate integration records. Repairs and package moves retain the first
preserved original options. Repair and restoration refuse unrelated later user
changes. Existing non-Steam duplicate detection and artwork refresh still apply.

Choose **Restore original Steam launch configuration**. The installer reads live
options, compares them with its generated command, restores the exact saved
string through Steam and verifies readback. If the user changed the options,
restoration refuses to overwrite them. Interrupted restoration is retryable.
An unavailable backup is never invented. Restoration never deletes original
games, saves, mods or unrelated settings. Recovery records and the inactive
wrapper are retained.

If the conversion was moved or deleted, run the installer at its new location
and select repair or automatic restoration using the existing record.
The stable wrapper reports missing launchers even if the entire conversion
folder was deleted. Use a newly extracted package's installer to restore the
original options or repair the link; no command entry is needed.

## Required Steam Frame acceptance

Full hardware acceptance remains pending for this release candidate. Record converter
commit, game/runtime versions, library paths and evidence for each check:

SSH access to a Frame was available. Synthetic fixtures passed there, including
actual bubblewrap write denial and source metadata preservation. On the actual
Frame, the existing loopback endpoint exposed both required SteamClient methods.
Stardew's live empty options were backed up, replaced, read back, restored,
verified and configured again, with SteamVR running and original files (including
hashes and metadata) unchanged during configuration. Subsequent real-game testing
confirmed `payload/runtime/dotnet/dotnet` as an AArch64 Linux ELF with genuine
AppID 413150. The user confirmed SteamVR view, controller input, gameplay,
saving and relaunch. Steam and SteamVR remained running throughout.

The shared launch contract retains Valve's native ARM64 launch wrapper and
`reaper SteamLaunch AppId=...` prefix from `%command%`, then uses the installed
native Valve pressure-vessel host launcher to execute the conversion. The original
x86/FEX/Proton game suffix is replaced. Preserving this harness and its graphics
context was necessary for SteamVR and controller input on the tested Frame.
A wrapper receipt alone is never counted as proof of an ARM64 game process.

The user confirmed successful Stardew launch and controller input after an ordinary
Steam/Frame restart on 2026-10-14. Original-runtime gameplay after restoration,
playtime and achievements remain unverified. A subsequent live restore/relink cycle
restored the exact prior options; the user confirmed the original runtime launches
after a startup delay, then confirmed the relinked ARM64 version works. Its actual
executable was verified as AArch64 dotnet. Other backends still require
real-game acceptance. The [asset deduplication checklist](steam-asset-deduplication.md)
is also mandatory; this test does not approve every candidate backend.

- [ ] Installed original on internal storage: recommended non-Steam installation and optional experimental link offered.
- [ ] Owned but not installed locally: clear requirement; official Steam install
      flow; cancel and later rescan without transferring again.
- [ ] Original installed on mounted SD/secondary library: detected without reinstall.
- [ ] No valid identity / other store: existing non-Steam path and artwork work.
- [ ] Automatic link from original entry: actual AArch64 game executable, gameplay, Steam Input/controller,
      save, exit and relaunch; original files unchanged.
- [ ] Playtime attribution verified separately, or explicitly unverified.
- [ ] Achievements verified using a genuinely supported backend and an actual
      unlock, or explicitly unverified; initialization alone is insufficient.
- [x] Restore previous options; original Stardew runtime launches; ARM64 relink verified.
- [x] Stardew live options persist across an ordinary user-initiated Steam restart;
      installer does not restart Steam or SteamVR.
- [ ] Duplicate installer runs, conversion updates, moved/deleted packages and
      interrupted setup recover without duplicate modifications.
- [ ] User edits after linking remain preserved; restoration refuses conflicts.
- [ ] Non-Steam registration and all artwork slots still work with Steam running.
- [ ] Celeste FMOD/controller and Stardew saves remain correct; Hollow Knight
      ARM64 Proton and STS2 two-stage workflows have no regressions.
- [ ] Windows x64, Linux AArch64 and Linux x64 candidate archives, notices, identities,
      SHA256 checksums and frozen GUI receipts pass on clean hosts.

The linking/deduplication checks above qualify experimental features; unfinished
items are retained for future promotion and do not block v0.1.1.0 under its
revised scope. Non-Steam installation, backend regression and final artifact
checks remain publication requirements in the release acceptance ledger.

## Implementation references

Valve documents the user-facing [Launch Options setup](https://help.steampowered.com/en/faqs/view/7D01-D2DD-D75E-2955)
and a Linux [%command% wrapper example](https://help.steampowered.com/en/faqs/view/145A-FE54-F37B-278A).
The [Steam browser protocol](https://developer.valvesoftware.com/wiki/Steam_browser_protocol)
provides the official client installation flow. STS2's local debug setter is an
architectural reference, not a stable public API assumed available across clients.

The [steam-engine API example](https://github.com/6E6B/steam-engine) demonstrates
`SetAppLaunchOptions` over CDP, but its wrapper-patching/debugger-enabling setup is
not adopted. [Decky frontend support](https://github.com/SteamDeckHomebrew/decky-frontend-lib)
and [steam-debug](https://github.com/kmturley/steam-debug) provide additional live
client context. `GetLaunchOptionsForApp` returns game-defined choices and is not
used to back up custom launch options.

## Non-Steam artwork refresh

The installer continues to copy bundled artwork under the actual registered
shortcut ID. When an existing loopback live interface is available, it also calls
`SteamClient.Apps.SetCustomArtworkForApp` to refresh the running client's artwork
without restarting Steam or SteamVR. This applies to all non-Steam backends,
including Hollow Knight; it does not enable original-entry linking for them.
If the interface is unavailable, installed image files remain intact and the
installer reports the refresh limitation. Steam API acknowledgement is distinct
from user confirmation that artwork is visible.
