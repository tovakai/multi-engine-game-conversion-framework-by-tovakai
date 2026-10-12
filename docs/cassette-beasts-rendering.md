# Cassette Beasts native ARM64 rendering compatibility

Cassette Beasts 1.8.3 on Steam Frame lost terrain/background surfaces and flickered
sprites when using the replacement Godot 3.5.1 runtime. The combined configuration
below passed user-confirmed five-minute gameplay, an area transition, the first
tutorial battle and save/load on physical Frame. The normal converter now packages
this configuration automatically for the narrowly identified game/runtime.
The fresh frozen-Windows-GUI ZIP passed the same physical hardware acceptance.

The generated launcher selects GLES3 and appends `norp` to `ZINK_DEBUG`, preserving
any existing debug flags. It places these settings in `game/override.cfg`, beside
`game/CassetteBeasts.pck`:

```ini
[rendering]
quality/depth_prepass/disable_for_vendors=""
quality/depth_prepass/enable=true
```

`ZINK_DEBUG=norp` disables Zink render-pass optimizations. With this runtime's
`--main-pack` launch mode, an executable-adjacent override would not be loaded.
The helper preserves unrelated existing settings and Godot Variant values and
rejects ambiguous duplicate rendering sections/depth keys. A symlinked override
is rejected to prevent writing through to the original installation.

The profile matches Steam App ID `1321440`, pack basename `CassetteBeasts`, PCK
engine version `3.5.1`, and the existing
`godot-3.5.1-godotsteam-3.30-steamworks-1.62-frame-arm64-v1` main-pack runtime.
Other game/runtime combinations keep their existing launcher/configuration.
`godot-compatibility.json` records profile
`cassette-beasts-gles3-zink-norp-depth-v1` in the generated payload. The profile
retains experimental status; the application/runtime release versions are unchanged.

## Evidence and limits

The tested GL vendor is `Mesa`, renderer
`zink Vulkan 1.4(Turnip Adreno (TM) 750 (MESA_TURNIP))`, driver Mesa
`26.3.0-devel (git-abc426bb62)`, window 1920×1080. Godot 3.5.1's exclusion code
matches **GL_RENDERER**, so `Adreno` disables the baseline pre-pass even though
GL_VENDOR is Mesa. The engine probe verifies that the generated override changes
the effective project settings; expected pre-pass use is inferred from the
unchanged renderer source, rather than measured with a GPU frame debugger.

| Configuration | Physical Frame result |
| --- | --- |
| Baseline GLES3 | Background surfaces flicker/disappear; geometry outlines remain |
| Forced depth pre-pass alone | Equally bad |
| GLES2 | Worse, including menu backgrounds; unsupported shader/texture-array errors |
| Turnip `sysmem` | Same corruption as baseline |
| Zink `sync` | Worse, fewer textures |
| Zink `norp` alone | Background surfaces restored; trees/similar sprites still flicker |
| Zink `norp` plus forced pre-pass | User-confirmed clean movement, transition, tutorial battle and save/load for at least five minutes |

These results support a compatibility workaround; the precise underlying driver
defect has not been established. No rendering code, engine binary or individual
game resource was rewritten. The original Linux executable also identifies
Godot 3.5.1 custom_build; its symbol table includes GLES3 and GridMap code. Pack
directory digests show all 53 shader resources and project.binary match the
Windows pack; other translations/scripts/resources differ. Static comparison
does not establish every custom engine patch or prove it is unnecessary generally.

Engine FPS logs are retained. The combined trial's later logged gameplay samples
were around 30–32 FPS; aggregate trial FPS includes menus/loading and different
locations, so it is not a controlled comparative benchmark. The user confirmed
playable performance. Other GPU/Mesa versions and extended play remain outside
this bounded hardware test. Controller recognition remains a separate known issue.

## Converter verification

The isolated frozen Windows GUI ran its real drop handler and enabled Convert
button against the original Windows Steam installation, with a new runtime cache
and no runtime override. Download, conversion and ZIP creation completed in
78.7 seconds. SHA-256 hashes and modification times of original files matched
before/after. ZIP CRC, ARM64 ELF architecture, launcher, merged PCK-adjacent
override, profile receipt, notices and graphics guard passed verification.

The private converter-produced ZIP has SHA-256
`7aeda7ea1f6458e92acd9fb80ffbd3b3115c9ab93ed386ea80a5c705c23b8929`.
Transfer to Frame produced the same hash. Package contents were not modified
after extraction; a separate diagnostic wrapper only isolates saves and records
FPS. The exact ZIP's probe confirms GLES3 and enabled/unexcluded depth pre-pass.
The user confirmed this fresh output works, then confirmed again after the
requested additional gameplay to exceed five minutes. The process had run at
least 6 minutes 47 seconds at a later check, with battle commands in its log.
Fresh scene samples logged approximately 42–45 FPS, with 60 FPS in battle; these
are observations from different scenes, not a benchmark comparison.

After hardening preservation of multiline override values, a second clean-cache
frozen-GUI conversion passed in 42.1 seconds. All game/runtime/launcher/override
bytes and file permissions match the physically tested ZIP. The only byte-level
differences are semantically identical JSON artwork-slot key ordering in package
metadata. `final-gui-package-equivalence-20261012.json` records this comparison.
The accepted Frame package remains at
`/home/steamos/tovakai-diagnostics/cassette-fresh-gui-20261012/CassetteBeasts-frame`;
its external `launch-fresh.sh` wrapper retains the isolated diagnostic save profile.

Regression validation: 88 Godot/profile/launcher/Frame-packaging tests passed;
one symlink test skipped because Windows could not create symlinks. Tests cover
narrow detection, preservation of overrides and source bytes/mtimes, complete ZIP
contents and actual Bash execution with preserved arguments/debug flags. An
equivalent symlink guard check passed on Frame, leaving its original target
unchanged. The override merger also distinguishes multiline Variant values from
section headers and rejects unbalanced or multiline depth assignments safely.

See the [experiment journal](../experiments/cassette-rendering/README.md) for
private reproduction tools, runtime/pack hashes and unsuccessful trials. Private
game files, saves, screenshots and raw shader diagnostics are excluded from Git
and release artifacts. The existing working conversion and runtime release are
preserved. This feature branch has not been merged or published.
