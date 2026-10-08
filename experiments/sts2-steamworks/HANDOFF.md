# STS2 Standalone Converter V1 Handoff

Continuation, 2026-10-08: the preserved baseline below now has a source-building
backend and framework integration on `feat/sts2-reproducible-pipeline`. See
[SOURCE_PIPELINE.md](SOURCE_PIPELINE.md) and
[hardware_validation_20261008.json](hardware_validation_20261008.json) for the
actual fresh-build, complete-conversion and Frame startup evidence, and the
remaining vendor/pristine-source/owned-Steam acceptance limitations.
The SDK-loop regression fix was freshly tested through the framework CLI from
commit `49d5a88`; see [VALIDATION_49d5a88.md](VALIDATION_49d5a88.md). Its evidence
is separate from the earlier deployed bundle.

## Preservation Boundary

This handoff preserves the completed isolated experiment; it does not begin
the next development phase. The implementation lives in
`experiments/sts2-steamworks`, not in GodotFrame's generic conversion backend.
The source profile recognizes only the exact observed Windows **v0.98.2 /
f4eeecc6** input files, for Steam AppID **2868840**. Arbitrary installation
directories are accepted; arbitrary game versions are not.

Source, tests, pinned dependency metadata, source-build observations, inspection
utilities, documentation and packaging scripts are committed. No original or
converted game binary, asset pack, SDK, runtime archive, compiled native library,
save, account credential, Steam credential or local ZIP is committed. The two
full-text local captures named in `.gitignore` remain private fixtures. Runtime
license texts are included with their applicable notices; the converter itself
uses the repository's AGPL-3.0 license. The converter grants no game, FMOD,
Spine or Steam redistribution permission.

## Implemented And Verified

`convert_sts2.py` is a complete standalone staging pipeline, using Python 3.10+
and the standard library on Windows or Linux. It accepts a selected game
directory, a new output directory, three official runtime archives, and five
explicitly supplied native files. It verifies the required source/dependency
hashes, adapts the exact managed pair and dependency graph, extracts selected
runtime members, patches a new PCK, writes launch/diagnostic tools and notices,
validates every output file, and publishes without replacing an existing
directory. An optional uncompressed tar preserves Linux execute permissions
for Windows-to-Frame transfer.

All transformations are out of place. No game DLL or native library is executed
by the converter. Existing installations and the manually prepared prototype
are not modified. Rollback of an acceptance run consists of restoring the prior
Steam launch options; there is no original-installation patch to reverse.

The launcher inherits Steam's display/session environment, defaults to the
prototype's X11 path, and requires SteamAppId 2868840 without manufacturing it.
It does not grant ownership or authenticate a user; those remain genuine game
and Steam operations. No fake stats or achievement callback is implemented.

Local verification is complete at this milestone. **A full conversion of a
publisher-pristine installation and execution of that converter output on a
physical Steam Frame have not been performed here.** The user's successful
gameplay/audio/input/Steam-initialization reports concern the earlier manually
prepared prototype, not this new output.

## What The 196 Tests Cover

The isolated Python suite previously ran **196 tests, all passing with no
skips**, when all optional local inspection fixtures, captures and official
archives were supplied. It is rerun before the preservation commit. This count
is not a count of on-device tests, and is not the result of the repository-wide
pytest suite. The separate CLR harness described below is also not included in
the 196 Python test count.

Preservation validation rerun: **196 passed, 0 skipped** in the populated
workspace. A source-only export of the staged publication tree, with no private
captures or fixture environment variables, discovered 188 tests: **145 passed,
43 intentionally skipped**, no failures. Optional fixture-dependent discovery
accounts for the different total. The CLR harness was freshly built outside the
checkout with **0 warnings / 0 errors** and passed its **5 separate behavior
checks**. These are local preservation checks, not physical-device acceptance.

- Synthetic complete conversions exercise the real deployment file plan,
  original-source preservation, exclusion of unselected/Windows files,
  source/native/archive hash refusals, AArch64 checks, archive member/path guards,
  staging cleanup, output collisions, JSON CLI behavior and shell syntax.
- Tar round trips verify file contents and execute modes. A fixed software
  allowlist excludes binary/private fixtures and produces reproducible ZIPs.
  The packaged CLI is relocated and executed with Python site packages disabled.
- Official x86-64 Godot independently reads synthetic packs produced by the
  append writer and complete converter. This tests Godot's PCK reader, not
  ARM64 execution or STS2 gameplay.
- Real inspected game/wrapper fixtures prove the original Windows hash
  relationship after restoring the PE machine field, reproduce the preserved
  patch chain, and match the verified final full-file hashes.
- Static IL inspection compares 46,701 original game method bodies: the stats
  adaptation changes only method 3964. It checks the local signature, exact
  GetStat call, callback registration and absence of the obsolete call.
  AArch64 disassembly checks all 44 native UserStats interface-013 thunks.
- The real-artifact pipeline extracts the checksum-verified official Godot,
  .NET and Sentry archives, uses the genuine inspected Steam API, and verifies
  the final managed recipe outputs. A separate relocated CLI test also uses
  the actual captured extension manifest bytes inside a synthetic pack.
- Inventory/provenance tests cover Windows stat precision, symlink refusal,
  structured dependency graph comparisons, selected manifest preservation,
  source-copy observations and the two exact FMOD build-source adaptations.

The four unavailable supplied native binaries, unchanged game dependency DLLs,
and full original 1.6 GiB pack are **synthetic stand-ins** in the complete local
pipeline tests. Production hashes are not relaxed by a CLI option. Test-only
temporary profiles identify synthetic fixtures; they are not distributed as a
supported game recipe.

The separate `clr-stats-tests` net8.0 harness runs five behavior checks on the
candidate's exact initialization IL, rebinding tokens to typed mocks. It tests
the uninitialized guard, successful/failed GetStat results, exception handling,
callback retention without fabricated delivery, global flow and reinitialization.
It never loads the game assembly as executable code or connects to Steam.

### Repeating Local Tests

Run from the repository root:

```bash
python3 -m venv /tmp/sts2-handoff-inspection-venv
/tmp/sts2-handoff-inspection-venv/bin/python -m pip install -r experiments/sts2-steamworks/requirements-inspection.txt
/tmp/sts2-handoff-inspection-venv/bin/python -m unittest discover -s experiments/sts2-steamworks -p 'test_*.py'
```

A public clone intentionally lacks the private captures and proprietary
inspection fixtures. The suite must report those tests as **skipped**, not as
additional passing tests. To reproduce the fully populated run, supply these
environment variables with your own authorized files:

| Variable | Required Fixture |
| --- | --- |
| `STS2_WRAPPER_DLL` | Inspected ARM64-tagged pre-patch wrapper, SHA-256 `474a2af1328c2a2b32bedf8376ed46a50958423313856659ac05bee677d8fdd3` |
| `STS2_GAME_DLL` | Inspected ARM64-tagged pre-stats game, SHA-256 `3f41afab3a499e40ddcc017ab672a1efdf236b038ac17b6badfdd825f19f7481` |
| `STS2_NATIVE_LIBRARY` | Genuine ARM64 Steam API, SHA-256 `9d354c631f01f7318bc00e8fa29842b83678f4293b52d0d5c11806edd76a7f4b` |
| `STS2_SOURCE_DEPS` | Hash-verified original Windows `sts2.deps.json` |
| `STS2_PROTOTYPE_DEPS` | Hash-verified working prototype `sts2.deps.json` |
| `STS2_DOTNET_RUNTIME_PACKAGE` | Pinned official linux-arm64 9.0.7 NuGet archive |
| `STS2_GODOT_MONO_TEMPLATES` | Pinned official Mono 4.5.1 export-template archive |
| `STS2_SENTRY_ARCHIVE` | Pinned official Sentry Godot 1.5.0 archive |
| `STS2_SPINE_API_JSON` | `extension_api.json` at the recorded godot-cpp commit |
| `STS2_FMOD_SCONSTRUCT` | Unmodified SConstruct at the recorded FMOD extension commit |
| `STS2_FMOD_COMMON_HEADER` | Unmodified common.h at the recorded FMOD extension commit |
| `STS2_GODOT_PACK_TEST_ENGINE` | Official x86-64 Mono 4.5.1 `templates/linux_release.x86_64` member on an x86-64 Linux test host |

The ignored `prototype_deployment_v1.json` and
`prototype_packed_extensions_v1.json` are the local full-text responses from
`probe_deployment_config.py` and `probe_packed_extensions.py`; they are required
only for their optional capture checks. Do not publish them to avoid redistributing
game/configuration contents. Their hash-only observations are committed.

For the separate CLR harness, supply a hash-verified final patched `sts2.dll`
as the positional argument. Redirect SDK outputs outside the checkout:

```bash
dotnet build experiments/sts2-steamworks/clr-stats-tests/StatsTests.csproj --artifacts-path /tmp/sts2-handoff-clr
dotnet /tmp/sts2-handoff-clr/bin/StatsTests/debug/StatsTests.dll /path/to/authorized/final/sts2.dll
```

The ordinary converter requires none of these inspection packages, the .NET
SDK, or private test fixtures. Its two standalone test modules can also run
with standard-library Python; optional artifact/engine tests will skip.

## Generated Versus Supplied Files

The successful local fixture output contains **226 manifest-tracked files**,
plus `conversion-manifest.json`. The exact allowlist and full size/hash pins
are in `converter_profile_v1.json`; this table explains their origin.

| Output | Origin / Action |
| --- | --- |
| `SlayTheSpire2.pck` | A new copy of the user's original pack, with two adapted manifests and an appended directory; original asset payloads and offsets are retained |
| `data_sts2_linuxbsd_arm64/sts2.dll` | Original matching game DLL, exact ARM64 PE metadata change and preserved stats initialization patch |
| `data_sts2_linuxbsd_arm64/Steamworks.NET.dll` | Original matching wrapper, exact ARM64 PE metadata change and preserved Steam interface recipes |
| `data_sts2_linuxbsd_arm64/sts2.deps.json` | Structured transformation of the hash-pinned original graph, serialized deterministically |
| 14 other game DLLs, `sts2.runtimeconfig.json`, `release_info.json`, controller VDF | Copied unchanged from selected original installation, verified individually |
| 186 .NET runtime deployment files | Selected members of official Microsoft .NET ARM64 9.0.7 package; no runtime build or binary patch |
| `SlayTheSpire2` | Official Godot Mono 4.5.1 ARM64 release export template, extracted unchanged |
| Sentry ARM64 `.so` and `crashpad_handler` | Selected official Sentry Godot 1.5.0 prebuilt members, extracted unchanged |
| Spine extension, FMOD extension, two FMOD runtimes, Steam API | Five explicitly supplied prebuilt files, copied unchanged after full size/hash/AArch64 checks |
| `launch.sh`, `collect-startup.sh`, `CONVERSION-NOTICES.txt` | Generated by converter-owned templates |
| `verify_output.py` | Converter-owned source copied to output, independent of the original prototype |
| `licenses/*` | Pinned open-source notices; two .NET texts are extracted from its archive, others accompany the software |
| `conversion-manifest.json` | Generated hashes, sizes, architecture/mode flags and transformation evidence for the completed staged output |
| Optional transfer `.tar` | Generated from validated output, with Linux modes; not a distributable game release |

The converter neither copies a prototype game tree nor needs prototype DLLs
as production inputs. The acceptance procedure retrieves the explicitly supplied
Steam API from its known deployed location only for convenience; any authorized
file with the same pin can replace that source. The other four supplied binaries
can come from surviving build/SDK workspaces or another authorized matching
prebuilt source. No prototype game, pack, managed code or launcher is transplanted.

## Dependency And Build Provenance

| Component | Current Method | Recovered Pin / Record |
| --- | --- | --- |
| Godot 4.5.1 Mono ARM64 | Download official templates; extract release runtime | Source `f62fdbde15035c5576dad93e586201f4d41ef0cb`; publisher SHA-512 and member SHA-256 in `godot_mono_451_provenance_v1.json` |
| Microsoft.NETCore.App 9.0.7 ARM64 | Download official NuGet runtime; extract selected members | Source `3c298d9f00936d651cc47d221762474e25277672`; archive SHA-256/SHA-512 and all deployment pins in `dotnet_runtime_907_provenance_v1.json` |
| Sentry Godot 1.5.0 | Download official release; use its prebuilts | Source `6c4d74ece1fab5eb841fc7c7135341a4abb28497`; archive and native member pins in `sentry_godot_150_provenance_v1.json` |
| Spine 4.2 GDExtension | Supplied prebuilt from the successful Frame build | Spine `e7dc1435fa4a0083ab431f1b28e083c14a1f5c68`, godot-cpp `27d9dd23c83871e0619fca5dc2cddfbfd69e926a`; `spine_*_observation_v1.json` |
| FMOD GDExtension 6.1.0-4.5.0 | Supplied prebuilt; source-build adaptations preserved | Source `fda1f89a08c0048ed313b333f90b7a7258ce2e61`, godot-cpp `e83fd0904c13356ed1d4c3d09f8bb9132bdc6b77`; `fmod_*_observation_v1.json` |
| FMOD core/studio 2.03.15 | Supplied licensed ARM64 SDK runtime prebuilts | Selected SDK, build and deployed hashes agree; SDK itself is not downloaded or redistributed |
| ARM64 Steam API | Supplied genuine prebuilt matching inspected ABI | SHA-256 `9d354c631f01f7318bc00e8fa29842b83678f4293b52d0d5c11806edd76a7f4b`; no fake export adapter or replacement authentication |

`fetch_converter_runtimes.py` downloads only the three official archives, using
HTTPS and full checksum verification, and reuses only verified cached files.
NuGet signature inspection previously returned zero with revocation-server
warnings; full online revocation validation is not claimed. The current fetcher
uses the preserved archive hashes, not a verification bypass.

No component is compiled during conversion. Recovered original Spine commands
were `setup-extension.sh 4.5.1-stable false` then
`build-extension.sh linux arm64` under `spine-godot/build`. The recovered FMOD
command used `scons platform=linux arch=arm64 target=template_release
fmod_lib_dir="$LAYOUT/" -j4`. This is recorded history, not a fresh reproducible
build claim. `adapt_fmod_build_sources.py` preserves the paired, exact-hash edits:
guard `-m64` / `-fuse-ld=gold` for non-ARM64, and prepend `<cstdio>` to common.h.
It refuses mixed/unknown source pairs and supports the reverse transformation.

## Preserved Steam Patch Provenance

The full patch chain is already **automatically generated** from the exact
original matching managed inputs by `prepare_managed.prepare_pair`; manual
prototype copying is not needed. `patch_accessors.py` and `patch_stats.py` retain
the original reversible installers, hashes and guarded byte recipes unchanged.

1. Original Windows game hash
   `bdf10e3bc572d0061c7d523b8f2ff4aa998baa19bd8cac5e2474b87cbe6500ab`
   and wrapper hash
   `e1cd0bf2436cefbb8bfcfcc1cea0587e5b9c740769e8340f7b9e9de72785fcf0`
   were linked to the inspected ARM64-tagged counterparts by changing only the
   PE machine metadata. The method body/native-header checks establish why this
   exact managed metadata change is permitted; it is not general native-code
   translation.
2. `generic-v1` changes only the eager GameSearch and MusicRemote accessor calls
   to genuine GetISteamGenericInterface routes after those exports were found
   absent. Wrapper intermediate hash:
   `808393ad362ef694e506d6b722bf4357014b1f2cdb19256d0f467c89b9ac02de`.
3. `client023-v2` selects SteamClient023 instead of 021. Device probes exposed
   HTTP/UGC accessor incompatibility with the older client; the user then
   reported successful Steam initialization with 023. Wrapper intermediate:
   `7dd9a985d68666096bdf8941497cc38e911561179998119a151373d9ea928db5`.
   Do not insert the separate historical HTTP-generic candidate into this chain.
4. `stats013-v3` selects UserStats013 for the inspected native thunk layout and
   replaces the obsolete RequestCurrentStats initialization call with the real
   GetStat result controlling readiness. It preserves genuine callback
   registration and global-stat flow; it never synthesizes a successful callback.
   Final wrapper:
   `e214b36dda06df40901cd5b0fb043045b7aa626475c0154f7ca421bb725fde14`.
   Final game:
   `c27aedddd408500ab05ac3c045f41c3f224e3db19c4a6904b5581cc4f588351c`.

Offsets, expected original bytes, target hashes and rollback logic are preserved
in those modules; static tests and the typed CLR harness supply the local
evidence, while prior user reports supply the prototype's device evidence.
Their historical installer CLI defaults reference the prototype paths; the
standalone converter imports only their pure guarded functions and never uses
those defaults. Do not run historical in-place installers against a clean source.

For a future release, `inspect_managed.py`, `inspect_stats.py` and the test tools
can parse MethodDefs, call tokens, user strings, local signatures and ABI thunks
to derive a new candidate recipe. That generation must remain evidence-driven:
new original/target hashes, exact method/semantic diffs, independently checked
native ABI, typed behavior tests and hardware acceptance are needed before a
new source profile is enabled. Do not generalize the existing byte offsets or
replace missing Steam functions with fabricated success.

## Remaining Clean-Source Reproducibility Work

The current converter is reproducible **given the pinned matching source and
authorized exact prebuilts**, but the clean-source/hardware acceptance claim is
not yet established. The next milestone, not performed during this handoff,
must address:

1. Validate publisher-pristine provenance for the matching original game files
   and run the complete converter against that legitimate installation. The
   observed inventory contained an unverified Windows Steam replacement and
   settings, which are excluded. Matching hashes do not certify the tree's
   publisher origin. Do not weaken hash guards if legitimate source bytes differ.
2. Obtain the four currently unavailable native files through authorized build
   outputs/SDK runtimes and run the full original pack through the converter.
   Supply the genuine Steam API explicitly; do not redistribute these binaries.
3. For build-from-source reproducibility, automate licensed Spine/FMOD builds at
   the recovered source pins, preserving exact changes, SDK/layout permissions,
   toolchain/SCons/compiler versions and build settings. Hash equality with a
   surviving build does not establish byte-reproducible compilation. Proprietary
   FMOD runtimes remain vendor-provided even when their extension is compiled.
4. Complete and review the licensed Steam API acquisition/version procedure and
   all dependency notice obligations. There is currently no automated proprietary
   SDK acquisition or permission grant in the converter.
5. Perform the physical Frame acceptance run below. Validate saves/reloads,
   controls and genuine Steam behavior separately. Authentication, ownership,
   cloud sync, stats writes and achievements are not proven by initialization,
   a nonzero pointer, a local setting write or a remote-storage write.

Backend/GUI wiring, newer game releases, packaging polish and broader native
build infrastructure remain separate milestones and were not enabled here.

## Physical Steam Frame Acceptance

**[STANDALONE.md, One Consolidated Procedure](STANDALONE.md#one-consolidated-procedure)
is the exact executable acceptance procedure.** It contains the complete
PowerShell preparation/conversion/transfer block, standalone Frame extraction
heredoc, real Steam launch options, acceptance checklist and diagnostic download
commands. Use those blocks together; this handoff deliberately does not maintain
a second divergent copy of them.

The sequence and acceptance criteria are:

1. From the experiment directory or extracted software bundle, select your
   legitimate v0.98.2 game directory. Supply the five authorized dependencies
   with the required basenames and verify the three official archives. The
   documented download and conversion commands retain their exit statuses and
   JSON reports. A source/hash refusal is a stop, not permission to edit pins.
2. Convert into an exclusively new local output and tar, run `verify_output.py`,
   and record the tar and output-manifest SHA-256 values. The original installation
   remains untouched. Do not upload the converted game archive to GitHub.
3. Transfer to an exclusively new Frame directory. Compare the tar SHA-256,
   extract with the documented exclusive-file heredoc, restore Linux modes,
   then verify `errors: []` and the manifest SHA. Use an execution-capable
   filesystem; do not alter device mount options as part of this test.
4. Record the prior owned STS2 Steam entry's launch/compatibility settings. For
   the documented output path, its temporary launch options are exactly:

   ```text
   bash -c 'exec "/run/media/steamos/SD512/sts2-clean-acceptance-01/sts2-arm64/collect-startup.sh"' -- %command%
   ```

   Launch from the real AppID 2868840 entry, not a non-Steam shortcut, SSH
   AppID override or fabricated callback. Do not modify original game files.
5. Require the successful Steam initialization log, no startup failure/dialog,
   and main-menu access. Play briefly; check animation/audio, mouse, ordinary
   gamepad and Frame Confirm/Cancel/direction/Settings controls. Save/exit and
   relaunch once to test reload. Back up personal saves by your normal process
   first: genuine gameplay can write user data even though conversion cannot.
6. Collect `conversion.json`, the latest `diagnostics/*.json` and verbose
   `diagnostics/*.log`, and observations for the checklist, whether passing or
   failing. If no native launch occurs, report the Steam UI launch error and
   whether diagnostic files exist. Review/redact Steam IDs before public sharing;
   never share credentials, saves, SDK contents or game binaries.
7. Restore prior Steam launch options/settings to roll back. Leave artifacts
   available for diagnosis; do not apply speculative DLL/controller patches.

The diagnostic collector uses static hashes and optional `readelf`, never
`ldd` or a Steam probe. It records dependency names, architecture, AppID/GameID,
display-variable presence and client presence; it does not dump the environment.
The verbose game log is the evidence for the actual native startup exception.

## Known Limitations

- v0.107.1 and unknown original hashes are rejected; no general managed binary
  converter or native instruction translator is implemented.
- The observed input already uses NullAchievementStrategy. This is preserved,
  not introduced by the compatibility patch. Achievement functionality and
  publisher-pristine provenance are not established by this experiment.
- The working observed dependency graph retains a Windows RID fallback under
  its Linux key. The separate `official-linux` candidate is not selected or
  validated on hardware.
- `dxgi.dll` Windows debug-information logging and any additional controller
  errors remain deferred. The prototype's successful input report does not
  substitute for testing this new output.
- Publication supports Windows and Linux no-replace semantics; unsupported
  hosts/filesystems fail rather than overwrite. Power-loss durability is not
  guaranteed; interrupted staging or an optional archive failure can leave
  clearly reported temporary/completed artifacts.
- No generic backend integration, automated proprietary dependency acquisition,
  bit-reproducible native build, extended gameplay test, cloud-sync test, ownership
  test, authentication test, stats-write test or achievement test is claimed.

## Source-Level Packaging

The normal distributable contains conversion software only:

```bash
python3 experiments/sts2-steamworks/package_converter.py /tmp/sts2-converter-software.zip
```

For a complete source-level preservation artifact, including tests, build
configuration, provenance and handoff documentation, archive the committed
allowlisted tree rather than a game output:

```bash
git archive --format=zip --output=/tmp/sts2-complete-source-handoff.zip HEAD LICENSE experiments/sts2-steamworks
```

The Git archive excludes ignored local captures, local builds and binaries by
construction. Do not use recursive filesystem ZIP commands over the experiment
directory: those could accidentally include private ignored captures.
