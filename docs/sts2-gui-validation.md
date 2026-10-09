# Experimental STS2 Windows-to-Frame validation

STS2 remains experimental. No claim of complete gameplay compatibility is made.

## Evidence collected October 9, 2026

- Windows development GUI: real drag/drop handler, connection setup and Convert
  action converted the legitimate retail Windows installation v0.107.1 /
  59260271. Inputs were checksum-pinned and read without modifying originals.
- Fresh application-owned Frame cache compiled native extensions from pinned
  sources and the authorized FMOD SDK. No prototype binaries were consumed.
- Deployment: 229 manifest-tracked files passed hash/mode verification; native
  extensions passed AArch64 ELF and exported-entrypoint verification.
- Retail managed patch: independent comparison of 48,970 method bodies found
  only the guarded statistics initializer changed. Five CLR mock behavior checks
  passed. These checks do not establish full gameplay or achievement behavior.
- Headless retail startup initialized .NET/GodotPlugins, FMOD and Sentry. Absence
  of Steam context correctly prevented Steam initialization in that test.
- The actual Windows GUI Steam connection action backed up the existing owned
  entry setting and installed the generated persistent launcher through Steam's
  API, after explicit user approval. No manual launch-option editing was needed.
- Real owned-Steam startup of that retail output: logs confirm Steamworks
  initialization succeeded, .NET/GodotPlugins and FMOD initialized. The user
  reports reaching the menu. Audio, controller navigation and full gameplay
  acceptance remain unconfirmed. The test used isolated local user data and
  did not start or load a run.
- Older v0.98.2 gameplay evidence belongs to earlier revisions and is not counted
  as fresh retail gameplay acceptance.

Private logs, receipts, user identifiers and proprietary inputs are excluded
from publication. Test destinations are isolated; original installations,
SteamOS partitions and existing prototypes are preserved.

## User workflow

Drag the original supported game folder into the Windows application. Complete
Frame Setup once using a trusted connection and an authorized FMOD SDK. Choose
an output location and click Convert. Downloads, transfers, source builds,
guarded transformations and verification run asynchronously. Accept Connect
Steam after conversion, then press Play in the owned Steam entry on the Frame.
Restore Steam recovers the saved per-game launch setting, provided it has not
subsequently been manually edited.

## Remaining gates

- FMOD acquisition and applicable FMOD/Spine permissions remain the user's
  responsibility; ownership does not imply middleware redistribution rights.
- Exact retail build pins are supported experimentally, not future versions.
- The packaged Windows GUI at commit 374eb4d completed a separate real retail
  conversion, with 229 tracked files verified. That output shares the initial
  retail Spine placement defect described below. Testing the corrected packaged
  build and its new Steam integration remains outstanding.
- Full owned-Steam gameplay, audio/controller behavior, save/Cloud behavior and
  restart/Restore acceptance still require validation.
- No root or system-wide compiler installation is performed. Frame prerequisites
  and the existing local Steam UI endpoint must be present.

## Retail startup finding

The first retail owned-Steam menu test exposed a real defect that integrity-only
validation did not detect: the Spine manifest moved to `addons/spine/`, while
the native recipe still placed its relative library under `bin/linux/`. Godot
therefore failed to load Spine and many animation resources. The corrected recipe
places the library under `addons/spine/linux/`; publication now resolves all three
packed ARM64 extension bindings against staged native files. Missing bindings and
wrong architectures are rejected before publication. This fixes directory
placement without changing the game's Spine manifest or using prototype binaries.

A separate Windows-specific DXGI diagnostic call throws in
`OsDebugInfo.GetSystemInfoString` on Linux. The exception is logged by an
asynchronous diagnostic task; the observed menu continues running. Its impact
beyond that observation is unverified. No dummy Windows library or fabricated
system information is supplied.

Local regression results before the corrected hardware smoke test: 50 pytest
tests passed on Linux; 49 passed and one Windows symlink-privilege test skipped
on Windows. The standalone suite ran 204 tests successfully (43 optional tests
skipped). CI for 0b6ae9a passed both Ubuntu and Windows desktop jobs, including
a Windows GUI window smoke test and software-only packaged build:
https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/actions/runs/37945648720

The corrected development GUI conversion completed in 346 one-second UI
heartbeats. Its fresh isolated Frame smoke test exited 0, verified all 229 files,
initialized hostfxr/GodotPlugins/FMOD, resolved all three ARM64 extension bindings,
and logged no missing Spine library or Spine resource-loader errors. No Steam
identity was synthesized. Owned-Steam graphical testing of this corrected output
is a separate outstanding gate.

Original input transfers can now be reused only from application-owned jobs
with the same full size and SHA256. Extraction still checks every original file
against the version profile. Prepared native outputs are never input-cache
candidates. This avoids repeated multi-gigabyte transfers while preserving the
original-source boundary.

## Corrected packaged application milestone

The Windows package built from 99eebac completed retail selection and conversion
through its real Browse, Output Folder and Convert controls. It deployed a new
229-file output, with all native bindings verified and manifest SHA256
`3a0d92cfc2d9129521f5ace52b73fea43d6403e980395e6132df284b53773101`.
A fresh isolated Frame smoke test exited 0 and initialized .NET/FMOD without
missing Spine libraries or Spine resource-loader errors.

After explicit approval, the actual packaged GUI Connect Steam button configured
that output in the owned entry and confirmed success. Local/cached Steam game
data was backed up privately before the normal-launch menu-only test; Steam
Cloud settings were not changed. CI for 99eebac passed both jobs.

The corrected packaged output has now launched through the real owned Steam
entry. Fresh logs confirm Steamworks, hostfxr/GodotPlugins and FMOD initialization,
with no missing Spine library or Spine resource-loader errors. The running game
is ELF machine 183 (AArch64), with Spine, FMOD, Steam API and hostfxr mapped.
The user confirms the menu, controller navigation and audio work. This evidence
is specific to the new packaged-GUI conversion, not the older prototype. Full
combat/gameplay, save/reload, achievements and Cloud synchronization remain
unverified; STS2 stays experimental.

The original Windows installation still passes full selected-input checksum
preflight after all GUI conversions. The packaged Restore Steam button restored
the previous saved launch setting; a subsequent packaged Connect Steam action
reselected the corrected output. Both states were checked through Steam's actual
UI API. The running game was not interrupted. The two-action automation initially
missed a confirmation dialog; the Restore state and separate reconnect were then
independently confirmed.
