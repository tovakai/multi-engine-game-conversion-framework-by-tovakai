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
- Packaged Windows GUI conversion and its new Steam integration must be recorded
  separately from development GUI evidence; packaged testing is ongoing.
- Full owned-Steam gameplay, audio/controller behavior, save/Cloud behavior and
  restart/Restore acceptance still require validation.
- No root or system-wide compiler installation is performed. Frame prerequisites
  and the existing local Steam UI endpoint must be present.
