# Steam library integration on Frame

Extract the converted ZIP, keep Steam / SteamVR running, and run
`./install-to-steam.sh`. Use `--help` for a short description.

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

## Guided linking

Choose the recommended original-entry option. First copy your current launch
options from the original game in **Properties → General → Launch Options** into
the installer. Empty means you confirm there were none. The installer cannot
reliably read live launch options; its backup is explicitly user-provided.

Copy the generated command (clipboard tools are used when available) and paste
it into that field. Disable forced compatibility overrides for the native Linux
launcher; do not select x86 Proton. Start the original game through Steam.

The wrapper consumes `%command%`, checks the matching inherited `SteamAppId`, and
executes the converted launcher without passing Steam's original executable as
game arguments. It preserves inherited Steam context and does not fabricate
ownership or successful Steamworks calls. Steam Input and original-entry playtime
may work, but require device verification. Steam initialization is not proof of
achievement support. Offline Steam stubs remain offline stubs.

Setup remains **pending** until the wrapper observes a matching Steam launch
context and rechecks the local installation. **launch-observed** means the
wrapper was reached, not that the game successfully initialized or gameplay was
verified. Run the installer again and choose **Verify existing link** to inspect
the receipt, package availability and current local installation. Compare the
printed command with the live Launch Options field; cached configuration is not
treated as authoritative. Steam does not get killed, restarted, or edited through
configuration files.

## Backend capability matrix

| Backend | Shared linking | Identity and limitations |
| --- | --- | --- |
| CelesteFrame | Guided native, device acceptance pending | Hash-gated vanilla Steam XNA 1.4.0.0 profile, AppID 504230; existing user FMOD and controller launcher retained |
| MonoFrame / Stardew Valley | Guided native, device acceptance pending | Hash-gated Steam 1.6.15 .NET 6 profile, AppID 413150; Steam online features remain unverified |
| GameMakerFrame | Guided native, device acceptance pending | Exact source Steam manifest required; offline runtime stubs gain no achievements |
| LÖVEFrame | Guided native, device acceptance pending | Exact source Steam manifest required; no general Steamworks guarantee |
| AGSFrame | Guided native, device acceptance pending | Exact source Steam manifest required; no general Steamworks guarantee |
| RenFrame | Deferred | Non-Steam supported; Ren'Py/runtime variants need dedicated context acceptance |
| RPGMFrame | Deferred | Non-Steam supported; NW.js, mkxp-z and EasyRPG contracts need separate acceptance |
| Godot / GodotSteam | Deferred | Non-Steam supported; genuine APIs, limited legacy bridges and offline stubs must remain distinct |
| UnityFrame / Hollow Knight | Deferred | Existing Windows ARM64 / ARM64 Proton launcher and prefix remain unchanged |
| Slay the Spire 2 experiment | Existing specialized integration | Two-stage preparation/finalization and authentic Steam launch chain remain unchanged; not routed through the shared native wrapper |

Loose `steam_appid.txt`, command-line overrides and title matching do not authorize
shared linking. Source manifests or the explicit hash-gated profiles supply
identity. Conflicting identities fail closed. Other-store games and packages with
no trustworthy identity can always use the non-Steam workflow.

## Repair and restoration

Records live at `~/.local/share/megcfbt/steam-links/<AppID>.json`, outside the
original game directory. The stable `launch-<AppID>.sh` wrapper lives there too,
so a moved/deleted conversion can still produce repair guidance. Records contain
package and launcher paths, AppID,
converter identity, profile, mode, generated options, user-preserved previous
options, installation paths, status and timestamps. Records are atomically
written before wrapper activation. A failed operation retains recovery data.

Rerunning the installer offers verification, repair, restoration, a separate
non-Steam shortcut, or cancellation. One record per original AppID prevents
duplicate integration records. Repairs and package moves retain the first
preserved original options. Preserve any later user edits before agreeing to
repair. Existing non-Steam duplicate detection and artwork refresh still apply.

Choose **Restore original Steam launch configuration** and paste the CURRENT
live Launch Options to compare with the generated command. If they changed,
the installer refuses restoration and asks you to preserve and reconcile your
settings manually. Otherwise it prints the preserved original options to paste
back into Steam, and marks the record restored only after explicit confirmation.
An unavailable backup is never invented. Restoration never deletes original
games, saves, mods or unrelated settings. Recovery records and the inactive
wrapper are retained.

If the conversion was moved or deleted, run the installer at its new location
and select repair, or restore the original options in Steam using the record.
The stable wrapper reports missing launchers even if the entire conversion
folder was deleted. Open the original game's Properties and use the preserved
record to restore its options, or repair from a newly extracted ZIP.

## Required Steam Frame acceptance

No hardware acceptance is claimed for this release candidate. Record converter
commit, game/runtime versions, library paths and evidence for each check:

SSH access to a Frame was available. Synthetic fixtures passed there, including
actual bubblewrap write denial and source metadata preservation. Real-game
interactive acceptance below remains pending. The
[asset deduplication checklist](steam-asset-deduplication.md) is also mandatory.

- [ ] Installed original on internal storage: recommended link offered.
- [ ] Owned but not installed locally: clear requirement; official Steam install
      flow; cancel and later rescan without transferring again.
- [ ] Original installed on mounted SD/secondary library: detected without reinstall.
- [ ] No valid identity / other store: existing non-Steam path and artwork work.
- [ ] Guided link from original entry: actual gameplay, Steam Input/controller,
      save, exit and relaunch; original files unchanged.
- [ ] Playtime attribution verified separately, or explicitly unverified.
- [ ] Achievements verified using a genuinely supported backend and an actual
      unlock, or explicitly unverified; initialization alone is insufficient.
- [ ] Restore previous options; original runtime launches normally.
- [ ] Duplicate installer runs, conversion updates, moved/deleted packages and
      interrupted setup recover without duplicate modifications.
- [ ] User edits after linking remain preserved; restoration refuses conflicts.
- [ ] Non-Steam registration and all artwork slots still work with Steam running.
- [ ] Celeste FMOD/controller and Stardew saves remain correct; Hollow Knight
      ARM64 Proton and STS2 two-stage workflows have no regressions.
- [ ] Windows x64 and Linux AArch64 candidate archives, notices, identities,
      SHA256 checksums and frozen GUI receipts pass on clean hosts.

Do not publish `v0.1.1.0` until mandatory acceptance evidence is reviewed.

## Implementation references

Valve documents the user-facing [Launch Options setup](https://help.steampowered.com/en/faqs/view/7D01-D2DD-D75E-2955)
and a Linux [%command% wrapper example](https://help.steampowered.com/en/faqs/view/145A-FE54-F37B-278A).
The [Steam browser protocol](https://developer.valvesoftware.com/wiki/Steam_browser_protocol)
provides the official client installation flow. STS2's local debug setter is an
architectural reference, not a stable public API assumed available across clients.
