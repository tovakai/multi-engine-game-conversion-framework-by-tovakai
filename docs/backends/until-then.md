# Until Then: experimental native ARM64 conversion

The unified GUI and CLI recognize the audited Windows Steam build **23785927**,
Godot **4.1.4**, with six native extensions. Conversion verifies the complete
3.25 GiB PCK SHA-256 and the original extension fingerprints. A changed game
build requires a new audited profile; matching a title or an AppID is insufficient.

## Convert on Windows

1. Select or drop the installed `Until Then` game directory into the converter.
2. Supply the **FMOD Studio API 2.02.35 Linux SDK**, kept unextracted as
   `fmodstudioapi20235linux.tar.gz`. Downloads is checked automatically; the
   shared **GET FMOD SDK • UNTIL THEN** dialog can select another location.
   Obtain the SDK from [FMOD downloads](https://www.fmod.com/download#fmodengine)
   under its terms. Celeste/STS2's 2.03.15 SDK is incompatible with this profile.
3. Click **CONVERT**. The tested ARM64 engine and extensions are resolved and
   validated automatically. The development Windows artifact includes their
   verified offline runtime archive; no compiler or manual runtime selection is
   required. Runtime-only public distribution is separate from the application
   release, and remains a release-preparation gate.
4. Transfer the versioned ZIP to Frame, extract it, run `install-to-steam.sh`,
   and choose **Add as non-Steam game**. Artwork uses the shared installer.

CLI:

```powershell
python -m megcfbt build "C:\Program Files (x86)\Steam\steamapps\common\Until Then" --fmod-sdk "C:\Users\YourName\Downloads\fmodstudioapi20235linux.tar.gz"
```

A source checkout without the offline archive or published runtime can use
`--backend-runtime <extracted-audited-bundle>`; arbitrary stock Godot runtimes
cannot supply this profile. Candidate application builders verify optional
offline archives in `build/runtime-bundles/` before embedding them. They are
build inputs, not committed binaries or vendor SDKs.

## Package and safety contract

The original PCK remains byte-identical. A separate small PCK overlays Linux
extension descriptors and adapts one custom thumbnail-loading call. The
matching engine loads this overlay before extensions initialize. Native
replacements implement JSON Patch, camera interpolation and seeded coloring;
InkCPP, Threen, FMOD and GodotSteam use pinned public sources. Private game
scripts appear only in the owner-generated overlay, never in converter source
or runtime distribution.

ARM64 FMOD libraries come exclusively from the checksum-verified owner SDK.
The genuine Steam API is resolved from `/opt/steamvr/bin/linuxarm64` on Frame.
Neither the SDK nor proprietary Steam/FMOD runtime libraries are bundled in the
open-source compatibility archive. Extension SDK symbols are isolated between
libraries; FMOD is released before unload so its worker threads cannot execute
unmapped callbacks. The launcher preserves Steam's existing display environment
and does not force x86 Proton, FEX or Zink.

AppID **1574820** comes from the hash-gated profile, with exact source-manifest
provenance retained when available. Conflicting manifests fail conversion.
Sidecars and titles cannot establish Steam ownership; genuine Steam initialization
and the game's own license checks still run. **Original-entry linking and asset
deduplication are unsupported for this profile.**

Converted saves use the stable separate directory
`~/.local/share/megcfbt/until-then` (or the equivalent beneath `XDG_DATA_HOME`).
Updating/reconverting a package retains that save location. Original saves and
Steam Cloud are not migrated. Earlier research saves remain in
`~/.local/share/megcfbt/research/until-then-20261014`; preserve them when migrating.
An existing source `override.cfg` is retained as `source-override.cfg`; the
converted override selects the isolated save directory.

## Evidence and limits

Real Steam Frame research testing confirms native AArch64 execution, visible
menus, audio, controller input, the morning scene and transition toward school,
saving, saved-game reload and normal menu exit. The story-loading and FMOD
shutdown regressions were fixed and retested. Native behavioral comparisons
pass 255 JSON cases, 36 camera checks and 2,560 coloring cases.

The production converter's inspection/backend/router/ZIP/installer path has
synthetic regression coverage. A fresh package produced by the frozen GUI also
requires its own device check; earlier research evidence is not automatically
production-package acceptance. Full-game coverage, thumbnail scheduling, NPC
appearance, playtime, achievements and Steam Cloud remain unverified. Logs retain
texture/resource cleanup warnings, scripted missing Visibility-node messages
and headless font warnings. This remains an experimental profile, and does not
make v0.1.1.0 release-ready.
