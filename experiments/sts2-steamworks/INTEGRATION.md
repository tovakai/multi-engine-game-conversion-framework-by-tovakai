# STS2 conversion integration: evidence gate

Work branch: `feature/sts2-arm64-conversion`. No change to generic Godot C#
support is enabled yet. The standalone `convert_sts2.py` now completes the isolated
staging pipeline, with synthetic and real-artifact integration tests; actual
clean-installation conversion and Frame acceptance remain pending. See
[STANDALONE.md](STANDALONE.md) for the consolidated acceptance procedure.
The evidence below is chronological; earlier incomplete-milestone statements
are retained as historical observations, not current pipeline status.

## Hardware evidence

The user reports that the prepared prototype reaches gameplay with working
audio, mouse, standard gamepad, Frame controllers, and Steam initialization.
This does not validate a conversion from a clean installation, ownership or
authentication workflows, cloud synchronization, achievements, extended play,
or complete save/load behavior. Do not assign a supported game release from the
reported `v0.98.2` log alone.

## Known transformations

The existing `patch_accessors.py` recipes preserve two generic interface routes
and select SteamClient023. The paired `patch_stats.py` recipe selects user-stats
013 and uses the actual result of `GetStat` to set readiness. See their exact
input/output hashes and tests. These transformations start from inspected
prototype assemblies, **not yet verified clean-installation assemblies**.

Local reinspection confirms that both supplied pre-final-patch assemblies have
PE machine `0xAA64`, PE32+ magic `0x20B`, CLR flags `0x1` and a zero managed
native header. These are already ARM64-tagged prototype images, not evidence
for the original Windows game PE headers. The corrected clean inventory now
establishes the wrapper relationship described below, but not the game DLL's
original IL or portability for that first game build. A second source observation
now links both managed counterparts by full hashes, as described below. Do not
silently use prototype identities to recognize an arbitrary installation.

The uploaded game already uses a null achievement strategy; this is not a change
made by the stats recipe. The second source game matches that image except for
the PE machine field, so this behavior predates our conversion patches in that
source observation. This is not proof of publisher-pristine game provenance or
working achievements. Never manufacture achievement callbacks.

## Missing reproduction inputs

### Received prototype inventory

The user supplied a complete static inventory with no read errors or exclusions:
250 regular files, 185 `.dll` files, and 23 ELF64 AArch64 identifications.
There are no symlink records. Its canonical file-record checksum recomputes to
`ce454508e6c4de2763168dc0397398e29f16462bb1580ada291db59111404287`.
The received file records are preserved in `prototype_inventory_v1.json` without
terminal prompts. This is user-supplied device evidence, not direct device access
or an independently reproduced clean conversion. No binary contents are stored.

All final wrapper, game and native Steam API hashes match the validated recipes.
The engine is an AArch64 ELF, 63,405,320 bytes, hash
`857b8242180c01648090998a53bbd6ac857ac2bfcbbced144ad847218b8275f1`.
Its exact official artifact has now been matched below. The package includes ARM64
CoreCLR, JIT, `libhostfxr.so`, `libhostpolicy.so` and System native libraries.
Both runtimeconfig summaries report `net9.0` with an empty `frameworks` array;
the initial collector does not include `includedFrameworks`, so this is not proof
that the deployment lacks a self-contained framework declaration or uses an
external runtime. Read the actual deployment configs next.

### Received deployment configuration

The follow-up device probe reports no errors for all nine hash-guarded files.
Its output is archived in `prototype_deployment_v1.json`. Raw launcher and
manifest text hashes independently recompute to the inventory values locally;
JSON configuration contents are structured summaries, not preserved original
byte layouts or suitable hash-verified patch inputs.

- `sts2.runtimeconfig.json` declares `net9.0` with an `includedFrameworks`
  entry for `Microsoft.NETCore.App` 9.0.7: a self-contained deployment declaration.
- `sts2.deps.json` targets `.NETCoreApp,Version=v9.0/linux-arm64`, lists 19
  libraries in that target and a Linux ARM64 runtime pack including `libhostfxr`.
  The separate framework deps target the same RID and version; its reported
  native list includes `libhostpolicy` but not `libhostfxr`. This identifies
  deployed configuration, not every step used to assemble it.
- `release_info.json` reports `v0.98.2`, commit `f4eeecc6`. This corroborates
  prototype release metadata only; the first source reports a different release.
- `launch.sh` resolves its own directory, selects the ARM64 data directory,
  prepends only root and data to the caller's existing `LD_LIBRARY_PATH`, sets
  `DOTNET_EnableDiagnostics=1`, and executes the engine with `--main-pack`,
  `--verbose` and forwarded arguments. It does not configure the known FMOD,
  Sentry, Spine or Steam client directories itself. The earlier successful SSH
  launch exported those directories before invoking it. A standalone launcher
  must deliberately account for that inherited environment; do not merely
  copy the short prototype script or force an SSH-specific display setup.
- The loose `addons/sentry/sentry.gdextension` is explicitly an override test:
  entry symbol `gdextension_init`, library `does-not-exist.so`. It is not a
  working ARM64 manifest and must not be adopted as the recipe. Its presence
  does not prove that the running engine used it, that Sentry is disabled, or
  that the packed manifest has priority; inspect packed resources next.
- The saved old Sentry manifest uses `gdextension_init` and lacks ARM64 entries.
  The saved ARM64 candidate uses `sentry_gdextension_init`, maps the ARM64
  library and declares the ARM64 crash handler. Packed content must establish
  whether that candidate was actually incorporated.

The completed diagnostic, `probe_packed_extensions.py`, reads bounded v2/v3 standalone
PCK tables, the small extension manifests and `.godot/extension_list.cfg` in all
three surviving packs. It checks actual configuration bytes against declared
MD5 values and reports their SHA-256 values. Other resources are compared only
by declared size/MD5/flags, not full payload hashes: this cannot prove all game
assets were preserved. Full pack hashes are not rechecked in this diagnostic.
Its published complete block remains in `FRAME_PACKED_EXTENSIONS.md`.

The layout was checked against upstream Godot 4.5.1 source fetched over the
configured Git transport at tag commit
`f62fdbde15035c5576dad93e586201f4d41ef0cb`:
[reader](https://github.com/godotengine/godot/blob/f62fdbde15035c5576dad93e586201f4d41ef0cb/core/io/file_access_pack.cpp),
[flags](https://github.com/godotengine/godot/blob/f62fdbde15035c5576dad93e586201f4d41ef0cb/core/io/file_access_pack.h).
This resolves parser layout provenance, not release-asset checksums or engine
binary identity at that earlier stage. HTTP release API access remains denied;
direct release downloads and official checksum files now succeed. The engine
archive/member comparison is recorded below; no validation bypass was used.

PCK fingerprints differ across three surviving files:

| Observed file | Bytes | SHA-256 |
| --- | --- | --- |
| Current PCK | 1,647,627,992 | `c30b5a98923273ef187638c3196275029ab0642da6bc71cc37bf96f150ad025e` |
| `.before-fmod-patch` | 1,647,627,768 | `7f04ddb038562e0402007a0e6e139a9cfe1c62443a1653dc77044e99623989ed` |
| `.before-sentry-patch` | 1,647,470,256 | `c0c4b951fa6b342d379c4221e2d96eba8a8bbfce5cd7cd2049254a74f6575d41` |

These names do not prove chronology, exact transformations, or original-source
identity. PCK resource/manifest changes must be recovered, not silently replaced
by copying the currently patched pack. The deployed loose Sentry manifest is
196 bytes; two saved manifests are 1,675 and 1,860 bytes with different hashes.
Their contents are now known from the deployment probe above; effective packed
contents are now known from the received packed-resource probe below. Neither
diagnostic performs native calls.

The tree also contains patch backups, diagnostic logs and `steam_settings` files.
Their presence alone does not establish use of any alternative Steam library:
the active prototype library matches the inspected genuine ARM64 Steam API.
Do not package experimental debris or configuration leftovers automatically;
establish their source/need before deciding which files belong in clean output.

An official Godot GitHub release metadata request from this cloud environment
was denied by the network proxy (HTTP 403 tunnel error). The later direct
release download succeeds, and the archive/engine checksums are now verified
below. No download validation was bypassed or unverified runtime adopted.

### Received packed extension evidence

The device returned three successfully parsed, unencrypted format-3 packs,
each declaring Godot 4.5.1, flag 2 and 13,158 directory entries. All twelve
reported configuration payloads have matching table MD5 values; the supplied
UTF-8 text independently recomputes to each reported SHA-256 locally.
`prototype_packed_extension_hashes_v1.json` preserves the hash-only observations.
Full-text captures (`prototype_packed_extensions_v1.json` and
`prototype_deployment_v1.json`) remain local, ignored by Git and excluded from
distributable fixtures. No source pack, game DLL or native binary is committed.

- Compared with `.before-fmod-patch`, current declared resource metadata differs
  only for `addons/fmod/fmod.gdextension`.
- Compared with `.before-sentry-patch`, it differs for that FMOD resource and
  `addons/sentry/sentry.gdextension` only. This is not an all-payload byte comparison.
- The extension list is identical and registers FMOD, Sentry and Spine.
- The packed Spine manifest is identical in all three packs; it already declares
  `linux.release.arm64` pointing to the deployed Spine library, with entry symbol
  `spine_godot_library_init`. No manifest modification is established for Spine.
- Current packed Sentry matches the saved ARM64 candidate, including entry
  `sentry_gdextension_init`, the real ARM64 library and crash-handler mapping.
  It is not the nonexistent-library loose test manifest. This confirms packed
  contents, not successful crash reporting or which file a running engine loaded.

Recovered resource adaptations:

| Resource | Before SHA-256 | After SHA-256 | Bytes before/after |
| --- | --- | --- | --- |
| FMOD | `d00e76c4661575ac13f205bdd1fa7482a87bc36b448dde4627ad76be501871b9` | `573b57815b1c7e341b567e12480e735dfc9a37d5bfaf3a8bfe0a1dca5e0e93a9` | 3,767 / 3,971 |
| Sentry | `39ee709ec6706630a001e6a7f7116a01250751ebf2bb232c82465c9d8c63b3eb` | `afeceb8ec9095aaac5f1ed57c2d79f152844de1bd78fd57442a0687d3da726bc` | 1,675 / 1,860 |

FMOD adds the ARM64 release library and dependencies for `libfmod.so.14` and
`libfmodstudio.so.14`. Sentry changes its entry symbol and adds the ARM64 release
library and crash-handler dependency. `adapt_packed_manifests.py` reproduces both
exact output hashes with guarded byte edits, retaining all other manifest bytes.
It is idempotent, refuses unknown inputs and validates the dependent set before
returning it. It changes no files and is **not** a PCK writer, package transaction,
clean-build recipe or normal converter integration. Its ID deliberately denotes
observed prototype manifests, not an identified supported game release.

The oldest observed pack stores its directory near the end, at 1,646,209,888,
with file base 112. The newer packs use directory offset 104 and file base
1,274,112. Thus whole-pack repacking/layout changed too. We can preserve logical
resources using the locally tested append writer described below, but cannot claim byte-identical
prototype output from two manifest inserts or that the oldest pack is original.

The clean-installation inventory has now been received and compared below.
`CLEAN_SOURCE_INVENTORY.md` retains complete Bash and native Windows PowerShell
blocks accepting any selected root. The first source release metadata now
identifies a newer build; a second inventory links the original experiment
below. Neither observation enables a full game-specific recipe in the converter.

### Received clean Windows inventory

The user-supplied version-2 report declares Windows Python 3.12.10, 218 regular
files, no errors, no exclusions and no symlinks. Its canonical file-record
checksum independently recomputes to
`b31fed61cd629adf7621e9613ce3bc07cb6a1b405fc2e00d65a7471901536c36`.
It is archived as `clean_inventory_v2.json`, containing hashes/metadata only.
Every record reports a handle/path difference in `st_ctime_ns`, confirming why
the earlier cross-API equality check rejected unchanged files. This is a
successful user-run Windows inventory, not execution or inspection of the game
on this machine.

`compare_inventories.py` validates report completeness, canonical checksums,
counts and regular relative file records before mapping exactly
`data_sts2_windows_x86_64/` to `data_sts2_linuxbsd_arm64/`. It compares size and
SHA-256, not permissions or platform stat metadata, and refuses path/mapping
collisions. The archived result `clean_prototype_comparison_v1.json` records
14 equal files, 176 different files, 28 source-only files and 60 prototype-only
files. This mapping is for comparison only, not a file-copy plan. Windows/Linux
framework changes, experimental debris and game-build differences must not be
treated as interchangeable transformations.

| File | Clean bytes | Clean SHA-256 | Conclusion |
| --- | --- | --- | --- |
| Steamworks.NET.dll | 387,584 | `e1cd0bf2436cefbb8bfcfcc1cea0587e5b9c740769e8340f7b9e9de72785fcf0` | Matches the inspected pre-patch wrapper after restoring only PE machine AA64 to 8664 |
| sts2.dll | 9,364,480 | `a1f9e653f1e28e4076558fee1e60d218619cb7e057b887c6417f62c62c6d7a52` | Differs from the 8,870,912-byte prototype; old game stats recipe is not applicable |
| SlayTheSpire2.pck | 1,901,378,340 | `42520eb8b0911c6c0f0bd102d92b33f41abd4d26b83489817d0a6dbd7dd48587` | Differs from all observed prototype packs; clean resources have not been read |
| release_info.json | 151 | `9dd9831b65f94478115d674c44315b096b98dc37e091d52ea84d243187e6c6cc` | User-run diagnostic identifies v0.107.1 / 59260271 |
| sts2.deps.json | 35,171 | `0620976a2fde3e57ebd1f1621efcd2da4809572cd093a61bb76f0f8ba9338837` | Different; Windows deployment transformation remains to be recovered |
| sts2.runtimeconfig.json | 357 | `bd81a252bc3f0e8bcb649b404c1da945913c5377b9d3a2c416c52730be8714c0` | Byte-identical to the prototype configuration |

The wrapper relationship is tested by verifying the uploaded prototype fixture,
locating its PE header and changing the two-byte machine field in memory only;
the result's full SHA-256 equals the user-supplied clean wrapper hash. No source
DLL is edited and no new installer is enabled. The unchanged runtimeconfig
can reuse the already inspected self-contained .NET 9.0.7 declaration. Neither
wrapper equality nor runtimeconfig equality establishes game IL equality,
achievement implementation or native game compatibility.

The user returned hash-guarded release metadata for the first installation:
`v0.107.1`, commit `59260271`, branch `v0.107.1`, date
`2026-06-18T15:43:56-07:00`. The observation is preserved as
`clean_release_v107_observation_v1.json`; its declared raw-file SHA matches the
inventory, not the serialization of that structured observation. This newer
game remains unsupported by the existing game stats recipe.

### Received matching-build source observation

The later attachment is a different complete version-2 Windows inventory:
229 regular files, no errors/exclusions/symlinks, tree checksum independently
verified as `6310b23f3fdb276a5efaa0b689676d87959d8814be15aa5b039f7cb8ee6fc5aa`.
It is preserved separately as `matching_build_inventory_v2.json` rather than
overwriting the first source evidence. Its mapped comparison, archived as
`matching_build_prototype_comparison_v1.json`, has 29 equal files, 173 differing
files, 27 source-only files and 48 prototype-only files.

- Source `sts2.dll` is 8,870,912 bytes, SHA-256
  `bdf10e3bc572d0061c7d523b8f2ff4aa998baa19bd8cac5e2474b87cbe6500ab`.
  Restoring only the inspected prototype's PE machine field to AMD64 produces
  this exact full hash. The wrapper has the same relationship established above.
- Source PCK is 1,647,470,256 bytes, SHA-256
  `c0c4b951fa6b342d379c4221e2d96eba8a8bbfce5cd7cd2049254a74f6575d41`:
  identical to the prototype's `.before-sentry-patch` pack. This now links the
  known input packed manifests to a user-supplied source observation; it is not
  proof of every game's asset provenance or a validated pack writer.
- Source `release_info.json` is 112 bytes with SHA-256
  `abd1cfcc2327940c6d2ec95e371c50f07455b670980782e68d6daa7b437dda6c`,
  identical to the prototype's metadata reporting `v0.98.2` / `f4eeecc6`.
  The two pasted v0.107.1 metadata outputs were from the other path, as clarified
  by the user. The first correct-path probe carried the other source's expected
  SHA and withheld metadata. The corrected hash-guarded probe now reports no
  errors and confirms version/branch `v0.98.2`, commit `f4eeecc6`, date
  `2026-03-06T15:52:37-08:00`. This user-supplied result is preserved separately
  as `matching_build_release_observation_v1.json`; its declared raw-file hash
  equals both inventories' metadata hash, not this observation's serialization.
- Runtimeconfig and deps hashes equal the first Windows source. Controller
  configuration now equals the prototype's counterpart.
- Active Windows `steam_api64.dll` is 7,332,264 bytes, SHA-256
  `1e3197d5eb3c9416820b0d06d450255759b7f82c007ba3025dab6acc60cfa991`.
  The 300,392-byte `.bak` file's hash equals the first installation's Steam DLL
  (`1add7f151fa644870a735ae86e68d1f019f296130d8e7c0a7ed3ecc7482dccbc`).
  There are eleven `steam_settings` files as well. These observations establish
  a replaced library relative to the other tree, not its origin or behavior.
  Ask provenance; exclude the replacement, backup and settings from the recipe.
  Do not load these files or assume that a full tree is publisher-pristine.

`prepare_managed.py` is a pure in-memory matching-build adapter. It accepts only
the two observed Windows hashes together (or the complete final pair), verifies
PE machine/PE32+ metadata and the exact counterpart hashes, then composes the
unchanged generic-v1, client023-v2 and stats013-v3 recipes. Its output hashes are
the existing validated final pair. It rejects unknown, mixed and intermediate
pairs, does not mutate inputs and returns only game/wrapper bytes. The source
images reconstructed in memory from the inspected fixtures match both observed
source hashes, enabling full byte-level tests without requiring another upload.
No source files are altered, no authentication responses are fabricated and no
Windows Steam DLL or settings are propagated. Idempotence is a paired in-memory
property, not installation/rollback or power-failure guarantees.

The recipe ID is `sts2-observed-matching-build-managed-v1`, not a supported-game
declaration. Deployment, legitimate input/dependency provenance, native runtime
acquisition, staged package construction and clean hardware acceptance still
gate integration. The user-source byte relationship does not authenticate an
original publisher distribution or establish genuine achievement functionality.

### Received original dependency graph

The uploaded matching-source `sts2.deps.json` is exactly 35,171 bytes and its
SHA-256 independently verifies as
`0620976a2fde3e57ebd1f1621efcd2da4809572cd093a61bb76f0f8ba9338837`.
The raw file remains outside the checkout as a local uploaded capture; only
`source_dependency_observation_v1.json` is intended for distribution. The
read-only `inspect_dependency_graph.py` requires a supplied expected hash,
limits input to 1 MiB, rejects duplicate/nonstandard JSON and malformed target
records, and reports canonical record hashes rather than full file contents.

Confirmed source graph:

- Active target `.NETCoreApp,Version=v9.0/win-x64`; empty signature and empty
  `.NETCoreApp,Version=v9.0` base target. The RID fallback graph is
  `win-x64` to `win`, `any`, `base`.
- Nineteen library records in the active target and metadata set, including the
  game, framework runtime pack, GodotSharp 4.5.1, 0Harmony 2.4.2.0,
  Steamworks.NET 1.0.0.0, Sentry 5.0.0 and Vortice/SharpGen dependencies.
- `sts2/0.1.0` has an explicit dependency on
  `runtimepack.Microsoft.NETCore.App.Runtime.win-x64` version `9.0.7`.
- That runtime pack declares 169 managed runtime assets and 15 native assets,
  including Windows CoreCLR/JIT, hostfxr/hostpolicy, diagnostic DLLs, compression
  and msquic. The other target records declare no native/runtimeTargets entries.
  This does not enumerate every dynamically loaded native library in the game.
- The original graph retains Windows-oriented Vortice assemblies. A package
  reference is not evidence they must be removed; defer DXGI logging changes.

Changing only `runtimeTarget.name` would leave a contradictory Windows target,
runtime-pack identity, project dependency, native asset list and RID graph.
Actual managed runtime-pack bytes also differ between Windows and Linux ARM64;
retagging them as portable game assemblies is not an appropriate substitute for
the verified ARM64 framework. Keep the exact game/third-party graph intact unless
the working deployment or API use establishes a specific additional change.

The full working prototype's
`data_sts2_linuxbsd_arm64/sts2.deps.json` (175,717 bytes) has now been uploaded.
Its raw SHA-256 independently verifies as
`ae899ff7301d1506b22d3a229ea3b4cd240f4e9585b8b9268506a7154ff65870`.
The full original bytes stay outside the checkout;
`prototype_dependency_observation_v1.json` preserves filtered record hashes.

### Recovered deployment adaptation and runtime provenance

The full source/target comparison establishes exactly these semantic changes:

- Runtime target and target-table keys: Windows x64 to Linux ARM64.
- Runtime-pack key in the active target and library metadata table: the same
  9.0.7 version, renamed from win-x64 to linux-arm64.
- Project runtime-pack dependency key: the corresponding rename. Other project
  dependencies and its runtime assembly record are identical.
- Runtime-pack native table: fifteen Windows assets replaced by fifteen Linux
  assets. All 169 managed runtime declarations remain exactly equal.
- Root RID table key: win-x64 to linux-arm64, but its values still contain
  `["win", "any", "base"]`. This is a prototype leftover, not a Linux graph.

All 17 other target records, all library metadata values after the pack-key
rename, compilation options and base target remain equal. No Vortice, Harmony,
Steamworks or Sentry dependency is removed or rewritten by this adaptation.
`dependency_graph_comparison_v1.json` records the hash-only comparison.

`adapt_deployment_graph.py` offers two explicit, in-memory modes:

| Mode | Result bytes | SHA-256 | Boundary |
| --- | --- | --- | --- |
| observed | 34,537 | `3dcc793b34e41a6a10d9a03e2f3045172abfa161a3d30ed0781d4c0a82372ffe` | Exact captured semantics, including historical Windows fallback; evidence replay only |
| official-linux | 34,573 | `cbe2588f9deda53dd55c6b4788901c57483f672f3a0fec5c6ef1663ba322dcdb` | Differs from observed semantics only in the active RID fallback list; isolated, not hardware-validated |

Both modes require the exact original input hash or their own complete output,
enforce canonical semantic and stable output-byte hashes, preserve inputs and
reject cross-mode/unknown candidates. The original prototype's UTF-8 BOM,
CRLF and deep PowerShell indentation are not reproduced; no byte-identical
175,717-byte output is claimed. Neither mode writes a file or enables a backend.
The same source deps hash is also present in the newer game, so this adapter
does not identify a supported game build; exact managed-pair/package guards
remain required. Existing working Steamworks recipes and device files are intact.

The official Microsoft.NETCore.App.Runtime.linux-arm64 9.0.7 package was fetched
over verified HTTPS from NuGet's flat-container endpoint. Its 37,093,402 bytes
have SHA-256 `0b4f51690d4bb304c1a598848e025454c6689dfb19d9833291b9bb7255bfbd87`;
the full SHA-512 matches NuGet's published `x-ms-meta-sha512` response header.
`dotnet_runtime_907_provenance_v1.json` records both digests, the official URL,
MIT license declaration, repository commit
`3c298d9f00936d651cc47d221762474e25277672`, and per-member deployment hashes.
No binary is added to Git, installed or executed.

All 186 package deployment members (169 managed DLLs, 15 native files and two
framework configs) equal the user-reported prototype's size and SHA-256 records.
All native headers identify ELF64 AArch64. `libhostfxr.so` is present in this
specific package and matches deployment, although its framework deps table
lists only fourteen native entries without hostfxr. Do not generalize this
host layout to other versions. The framework's 169 managed declarations also
equal the transplanted game graph's declarations. Its official linux-arm64 RID
fallback is `["linux", "unix-arm64", "unix", "any", "base"]`, which supplies
the sole semantic difference in the separate candidate mode.

`dotnet nuget verify --all` (SDK 8.0.425) returned exit 0 and identified Microsoft
author and NuGet repository signatures, with NU3018/NU3028 warnings because
revocation endpoints could not be reached. Full online chain/revocation
validation is not claimed. No TLS, checksum or signature settings were disabled;
the published-checksum comparison and static member inspection remain distinct
from full online certificate verification or a new runtime/device test.

### Recovered Godot engine provenance

Direct official Godot release downloads now succeed, although the GitHub API
still returns HTTP 403. The full 1,276,830,924-byte Mono export-template archive
was downloaded and verified against the official release's `SHA512-SUMS.txt`.
`godot_mono_451_provenance_v1.json` records its URL, SHA-256/SHA-512 and selected
member; no checksum validation was bypassed and no engine code executed.

`templates/version.txt` reports `4.5.1.stable.mono`.
`templates/linux_release.arm64` is an executable ELF64 AArch64 image, 63,405,320
bytes, SHA-256
`857b8242180c01648090998a53bbd6ac857ac2bfcbbced144ad847218b8275f1`.
Its complete bytes match the prototype engine's inventory record. This confirms
the deployed release export template, not the editor binary or a custom build.
The archive SHA-256 is
`c425633061bb49f4390bdcece2b9ce68b3b0be3c71095b40644d8f6f17b1146e`;
the full publisher-matched SHA-512 is retained in the provenance JSON.
The ARM64 editor archive is not needed to explain that deployed executable and
has not been downloaded or validated. The template archive remains outside Git.

### Recovered Sentry release provenance

The official Sentry 1.5.0 release asset is now downloaded and verified against
the SHA-256 displayed on its official GitHub expanded-assets page. The API
still returns HTTP 403, but the publisher release page and direct asset
download work. The 405,666,640-byte archive SHA-256 is
`90f00a44f588c9fece083178109b5cca37dbae98186c426f4d522b96a43d4d4e`.
`sentry_godot_150_provenance_v1.json` records that checksum authority, selected
members and the source tag resolved through Git transport to
`6c4d74ece1fab5eb841fc7c7135341a4abb28497`.

The ARM64 release library (4,386,096 bytes) and crash handler (850,216 bytes)
both match the prototype's full hashes and sizes. Both are ELF64 AArch64;
static dynamic-symbol inspection confirms a defined `sentry_gdextension_init`
export in the library. No binary is executed and crash reporting is not tested.
The plugin's pinned source `LICENSE.md` is MIT; preserve its notice and review
bundled native/crashpad notices before redistribution. The release zip contains
a README linking licensing, not a standalone license file.

The official 3,891-byte manifest's SHA-256 is
`56ca4fc8f7dec32c0bafdb273d69ff1af08c4addd66fc46a12924fa1a3f39773`.
It is not the 1,860-byte game manifest produced by our guarded packed-resource
adaptation. Do not replace the whole game addon/configuration with the SDK
manifest or copy the invalid loose override-test file. Preserve the existing
minimal packed-manifest recipe and choose only the verified ARM64 binaries.

Package staging, validated pack writing and remaining native dependency
provenance still gate a fresh clean conversion. The candidate RID correction is
not installed into the existing prototype and requires fresh hardware acceptance.

The first Spine device diagnostic was the bounded `probe_spine_checkout.py`.
It locates named `spine-runtimes` folders within five levels under the user's
home and `/run/media/steamos/SD512`, with a 5,000-directory cap. It skips common
cache/Steam/personal-data folders and symlinks, reads commit/branch/tracked status
and recursive submodule metadata through Git, and never requests remote URLs,
fetches, builds, file contents or Steam initialization. Git optional locks and
fsmonitor are disabled; a real synthetic-repository test verifies no changes to
its working tree or Git files. Search caps/traversal errors and failed operations
are explicit; absence is not proof that the original checkout no longer exists.
This probe supplies evidence for a reproducibility pin, not a binary-to-source
attestation. FMOD build modifications and SDK licensing remain separate inputs.

The returned result is archived as `spine_checkout_observation_v1.json`. It found
`spine-arm64-build/spine-runtimes` at commit
`e7dc1435fa4a0083ab431f1b28e083c14a1f5c68`, branch `4.2`, with no reported
submodules. Tracked status timed out, and three permission errors left the search
incomplete. This is a candidate checkout pin, not evidence of a clean worktree,
complete source search or the source that produced the deployed binary.

The upstream setup script at that exact commit clones `godot-cpp` from the moving
Godot major/minor branch and copies `spine-cpp/spine-cpp` into the extension source
directory. `probe_spine_build_inputs.py` therefore targets the known checkout and
its nested `spine-godot/godot-cpp` repository, uses a 120-second operation timeout,
and scopes outer tracked status to the relevant Spine directories. Untracked
paths are counted and listed up to 40, separately from tracked changes. Ignored
files and copied source contents are not attested; these remain further build
inputs, not implicitly proven clean by an empty status result. No fetch or build
is performed. Tests include a real modified synthetic repository and verify that
the diagnostic leaves Git metadata and working-tree bytes unchanged.

The targeted result is archived as `spine_build_inputs_observation_v1.json`.
Both operations completed without reported errors. Spine retains the same
`e7dc1435fa4a0083ab431f1b28e083c14a1f5c68` commit on `4.2`; nested godot-cpp
is at `27d9dd23c83871e0619fca5dc2cddfbfd69e926a` on `4.5`. Both report empty
tracked changes, no non-ignored untracked paths and no submodules. This resolves
the earlier status timeout for the stated scopes, not the earlier incomplete
whole search or ignored-file contents.

Upstream `.gitignore` explicitly excludes the copied Spine C++ tree, godot-cpp,
and build output directories. The pinned `spine-godot/SConstruct` compiles from
`spine_godot/spine-cpp/src/spine/*.cpp`, not the original checkout tree.
`probe_spine_copy.py` was therefore the next bounded, static device diagnostic:
compare selected C/C++ source/header hash records for the original and copied
trees, fingerprint optional custom.py/dev/API inputs without executing them,
and compare two surviving build-output paths and the deployed library against
the inventory's full SHA and size. Missing optional files are explicit, failed
trees never imply equality, differences are counted/listed up to 20, source
traversal is capped and symlinks, oversized or concurrently changed files are
refused. No source contents, compiler invocation, library loading or Steam calls
are involved. Matching files still would not demonstrate a reproducible build.

Its returned result is archived as `spine_copy_observation_v1.json`, with no
reported errors. Each selected source tree contains 158 C/C++ source/header
records; both canonical tree hashes are
`d6a1bb80fb864180e5103ed462e5fd42433fbf44e8edcba9ea753d6a763598a3`, with
zero differences. The build library, example copy and deployed library all
match the inventory's 4,328,984-byte SHA
`5af1a01af371ee9469021705ac6de8fc3cf7aa642362b1b4ea461adb2cbb3a3a`.
No `spine-godot/custom.py` or godot-cpp `dev` marker is present at the inspected
paths. These are observed input/output relationships, not a compiler invocation
record or an independently reproduced native build.

The godot-cpp API JSON is 6,581,513 bytes with SHA
`23d807e3f914f7a91b152a8a7b03638d4853f8e642b79f10ce85a43b44340bfd`.
An independent HTTPS download of that source file at the reported godot-cpp
commit has the same full hash and size; metadata is recorded separately in
`spine_upstream_api_provenance_v1.json`, with raw source outside the checkout.
The selected source-tree hash itself is user-supplied evidence, not yet compared
with an independently downloaded complete upstream Spine source tree. Toolchain
versions, generated binding inputs and license authorization still gate a fresh
build or distribution recipe; no working prototype files are changed.

The pinned root `LICENSE` is the Spine Runtimes License Agreement, updated
April 5, 2025, not MIT. It refers to Section 2 of the Spine Editor License
Agreement for integration/derivative works; its alternative permission requires
each Product user to obtain their own Spine Editor license and includes notice
requirements for redistribution. Review the applicable terms/authorization
before enabling acquisition/build/distribution automation; no public Spine
binary redistribution is enabled by this experiment. Upstream sources inspected:
[setup](https://github.com/EsotericSoftware/spine-runtimes/blob/e7dc1435fa4a0083ab431f1b28e083c14a1f5c68/spine-godot/build/setup-extension.sh),
[build](https://github.com/EsotericSoftware/spine-runtimes/blob/e7dc1435fa4a0083ab431f1b28e083c14a1f5c68/spine-godot/SConstruct),
[ignore rules](https://github.com/EsotericSoftware/spine-runtimes/blob/e7dc1435fa4a0083ab431f1b28e083c14a1f5c68/.gitignore),
[license](https://github.com/EsotericSoftware/spine-runtimes/blob/e7dc1435fa4a0083ab431f1b28e083c14a1f5c68/LICENSE).

The FMOD checkout diagnostic was `probe_fmod_checkout.py`: a depth-3,
500-directory search confined to the reported FMOD build workspace, skipping
SDK/layout/library/demo/generated directories and symlinks. It reads checkout
and submodule pins, tracked status and a bounded non-ignored build-path listing.
Only at the reported extension commit does it disclose the `SConstruct` diff
against HEAD, capped at 8,192 characters with explicit truncation and a full-diff
hash. SDK contents, logs and remote URLs are not requested. Git optional locks
and fsmonitor are disabled, diff has external drivers/text conversion disabled,
and no build or fetch occurs. Permission/cap/failure results remain explicit.
The pinned upstream SConstruct confirms the unconditional Linux `-m64` and
`-fuse-ld=gold` line; the returned device adaptation is recorded below.

`fmod_checkout_observation_v1.json` preserves the received result: 41 visited
directories, no reported errors or incomplete-search flag. The extension is at
`fda1f89a08c0048ed313b333f90b7a7258ce2e61`, with an empty branch name consistent
with detached HEAD. Nested godot-cpp is at
`e83fd0904c13356ed1d4c3d09f8bb9132bdc6b77`, reporting no tracked changes or
non-ignored build-path additions. The human-readable submodule description's
old tag does not establish the Godot API/runtime version used by this build.

The untruncated SConstruct diff independently recomputes to its reported SHA
`456323268fc44e645ab3e895f65235dfe6d3e6bd92c567388e77ebd29d63b76a`.
It guards only the Linux `-m64`/`-fuse-ld=gold` append with
`if env["arch"] != "arm64":`, preserving the existing flags for other
architectures. This confirms the reported local edit, not a fresh successful
compile or complete native recipe. The extension also reports a change to
`src/helpers/common.h`, whose contents are still unknown. The first status line
in this diagnostic is whitespace-trimmed; infer modified paths only, not which
Git status column was set.

The header diagnostic was `probe_fmod_header.py`, confined to the
two named public extension files at the known checkout. It refuses another
HEAD, reports exact base/current SHA/size and capped raw diff hashes/previews,
and checks current file bytes and HEAD again before accepting each row. Git
external diff/text conversion and optional locks/fsmonitor are disabled. No SDK
contents, build execution or new source adaptation is involved. Header changes
must be inspected before assuming they are harmless or including them in a
reproduction recipe; SDK layout, binary equality and authorization remain later
evidence gates.

The returned `fmod_source_observation_v1.json` reports no errors and untruncated
diffs for both files. The header edit prepends exactly `#include <cstdio>\n`
before the existing include guard, supplying an explicit standard header for
existing `sscanf`/`snprintf` calls; the remaining header bytes are unchanged.
The SConstruct edit is the previously observed ARM64 guard. Both original files
were independently downloaded from the pinned upstream commit; their complete
SHA/size match the reported base values. Raw sources remain outside the checkout.

`adapt_fmod_build_sources.py` now reproduces the exact current hashes from those
originals and reverses both edits to their original bytes entirely in memory.
The paired recipe accepts only a complete original pair or complete adapted pair,
is idempotent in both directions, refuses unknown/mixed/missing inputs, checks
each unique byte anchor and verifies every final hash before returning a result.
It preserves extra resources and performs no filesystem writes, native build or
backend integration. Source and result fingerprints:

| File | Original SHA-256 | Adapted SHA-256 | Bytes before/after |
| --- | --- | --- | --- |
| SConstruct | `253761c20fc57ba68301953ba1d11a6a355e4e6dc8663e5c0f19981dc81020f8` | `a83e6d09efebe83ef759d40e95f8071b9a04dfa0824801ee4d6a52fdf7ea1edb` | 7,652 / 7,687 |
| src/helpers/common.h | `7221a332c04b6f910ea9b27d2aaa1863243b3498341b50be2fa5d648529d607b` | `f4f70e508e2196af5e5283279fb4bf82979ae5abb6d95c55a67492b616a1a785` | 9,074 / 9,092 |

The actual upstream-source test also compares the complete SConstruct AST with
an independent AST transformation adding only the `arch != "arm64"` guard to
the x86 flags append, and verifies the unchanged header suffix. This is source
adaptation validation, not compilation or proof that current sources produced
the prototype binary. SDK and runtime provenance are not inferred from it.

The SDK device diagnostic was `probe_fmod_sdk.py`: bounded hashes for five
selected SDK headers, four explicit linker/SONAME alias paths, the extension
build output and three deployed libraries. It reports only header hash/size and
literal FMOD_VERSION hexadecimal definition tokens, not SDK contents. Internal
SDK-layout aliases are resolved only within the reported build root; external
targets are refused without reading them. It guards regularity, size, concurrent
file/alias changes and fingerprints ELF class/machine without loading anything.
Missing candidates are explicit; this is not a complete SDK inventory, dependency
scan, license grant or reproduced native build. Prototype comparison pins come
from the existing inventory; no publisher authenticity is inferred for SDK
files merely because they match that device observation.

### Received FMOD SDK layout

`fmod_sdk_observation_v1.json` preserves the received result without its terminal
prompt. All 13 selected paths are present, with no errors. The five SDK headers
resolve under `fmodstudioapi20315linux/api/`; fmod_common.h reports the literal
version token `0x00020315`. Core `.so`/`.so.14` aliases resolve to
`api/core/lib/arm64/libfmod.so.14.15`; studio aliases resolve to the corresponding
`libfmodstudio.so.14.15`. All four alias fingerprints match the deployed runtime
hashes and identify ELF64 AArch64. The surviving extension build output also
matches the deployed 3,281,280-byte library exactly. This closes the selected
layout/output fingerprint check, not complete SDK provenance or redistribution
authorization. No more device diagnostic is needed for this checkpoint.

### Standalone pack output milestone

`patch_pack.py` implements an out-of-place append patch for the exact observed
source pack, with arbitrary user-selected source/output paths. It retains the
complete source prefix except the eight-byte directory pointer at offset 32,
appends changed FMOD/Sentry manifests and a copied/updated resource directory,
and leaves original payload bytes, offsets and unchanged table records intact.
Old manifest payloads and the old directory remain unused in the copied prefix;
the resulting complete-file hash/layout is deliberately not the prototype's.
No asset extraction or full repacking is needed. Source SHA is computed during
the same streaming pass that copies it, reducing redundant full-pack reads.

The STS2 entrypoint accepts only the inventory-linked original pack hash/size.
Format/version/flags, path aliases, range/directory overlap, entry/table bounds,
the four required configurations and their actual MD5 values are checked before
publication. It reuses the existing hash-guarded manifest adaptation. Existing
destinations and symlinks are refused. Source descriptor/path stability retains
the Windows cross-stat handling proven by the inventory collector. Output is
fsynced and published via a same-filesystem hard link that cannot overwrite a
concurrently created destination; failures remove only the unpublished temporary
file. Hard-link support is required, and power-failure durability is not claimed.

Fourteen focused tests cover byte/offset preservation, alternate directory layouts,
streaming, actual observed manifests, unchanged clones, hash/MD5 and malformed
input refusal, destination races, failure cleanup, Windows stat precision, CLI
JSON and the release-specific source guard. An independent functional smoke test
uses the official **x86-64** Godot 4.5.1 Mono release export member from the already
checksum-verified template archive: it opens the emitted synthetic pack and
asserts both changed manifests and an unchanged asset through FileAccess. This
does not run STS2, load the ARM64 extensions or test the Frame. The real 1.6 GB
source pack is not available locally; fresh real-source/device validation remains
required. The main backend's C# rejection remains unchanged.

CLI for the isolated pack step (not a complete converter):

```bash
python3 experiments/sts2-steamworks/patch_pack.py SOURCE.pck NEW_OUTPUT.pck
```

### Shorter Critical Path

The next deliverable is standalone package staging with a launcher and explicit,
hash-verified local native inputs, not another round of build provenance probes.
The input remains an independently selected legitimate game installation, never
the already patched prototype as the complete source. User-authorized prebuilt
native components can be accepted as external inputs for the first experiment;
no redistribution or silent license permission is implied. Fresh native builds,
toolchain pinning and compiler-level reproducibility can remain separate work
without blocking that implementation. Unknown transforms, source integrity,
authentication/ownership behavior and clean-conversion acceptance are **not**
waived. Batch the eventual artifact transfer and first complete device test after
local staging/rollback verification; do not ask the user to test each helper.

### Remaining inputs

| Component | Current evidence | Required before implementation |
| --- | --- | --- |
| Clean game | Separate v0.107.1 and v0.98.2/f4eeecc6 metadata, matching-experiment fingerprints | Clarify replaced Steam DLL provenance and legitimate pristine input; direct access is not required |
| Prepared game | Inventories, full deps comparison, exact manifest transforms and locally engine-tested append writer | Complete package staging and real-source comparison of every changed file |
| Godot | Official Mono export-template archive checksum verified; release ARM64 member equals prototype | Mono cache/staging, license notices and host validation; no editor/custom build assumed |
| .NET | Official package checksum, all 186 deployment hashes and exact graph replay verified | Production cache/staging integration, full online revocation check and candidate RID hardware acceptance |
| Spine | Both source pins, 158 matching original/copied C/C++ records, build/deployment binary equality and upstream API fingerprint | Fresh pinned-source/build verification, toolchain/generated inputs and license authorization |
| FMOD | Source pins/edits, selected SDK 2.03.15 layout and build/deployment fingerprints verified | Authorized external inputs; fresh source-to-binary/toolchain verification deferred separately |
| Sentry | Publisher archive checksum verified, both ARM64 binary hashes match prototype, source tag/entry export pinned | Selected-member staging and license/third-party notices; do not replace the adapted game manifest |
| Steam API | Inspected ARM64 hash, matches user's SteamVR copy | Legitimate local acquisition route; no Valve binary redistribution |
| Launcher/assets | Launcher, inherited paths and packed extension configuration known | Standalone dependency resolution, validated pack output and asset preservation |

### User-recovered provenance (not independently artifact-verified)

- Godot [4.5.1-stable](https://github.com/godotengine/godot/releases/tag/4.5.1-stable):
  `Godot_v4.5.1-stable_mono_export_templates.tpz` and
  `Godot_v4.5.1-stable_mono_linux_arm64.zip`. The export-template checksum and
  exact deployed release member are now verified above; the editor archive
  remains unneeded/unverified. Filename or version alone is not verification.
- Microsoft.NETCore.App.Runtime.linux-arm64
  [9.0.7](https://www.nuget.org/packages/Microsoft.NETCore.App.Runtime.linux-arm64/9.0.7).
  Original target reportedly `net9.0`, runtime 9.0.7,
  `.NETCoreApp,Version=v9.0/win-x64`. Exact `.deps.json` changes and all deployed
  runtime/host package members are now recovered above. Do not assume another
  runtime package supplies every apphost/self-contained host component.
- [spine-runtimes](https://github.com/EsotericSoftware/spine-runtimes), branch
  `4.2`: `spine-godot/build/setup-extension.sh 4.5.1-stable false`, then
  `build-extension.sh linux arm64`. Output
  `bin/linux/libspine_godot.linux.template_release.arm64.so`. Branch is not a pin.
- [fmod-gdextension](https://github.com/utopia-rise/fmod-gdextension), tag
  `6.1.0-4.5.0`, commit `fda1f89a08c0048ed313b333f90b7a7258ce2e61`;
  separately acquired `fmodstudioapi20315linux.tar.gz` SDK 2.03.15.
  Guarded x86-only `-m64` and `-fuse-ld=gold` flags for ARM64. Built with
  `scons platform=linux arch=arm64 target=template_release fmod_lib_dir=... -j4`.
  Expected export `fmod_library_init`; proprietary runtimes must not be bundled
  from a public repository without authorization.
- [Sentry Godot 1.5.0](https://github.com/getsentry/sentry-godot/releases/tag/1.5.0):
  `sentry-godot-1.5.0+6c4d74e.zip`, deployed
  `addons/sentry/bin/linux/arm64/libsentry.linux.release.arm64.so` and
  `crashpad_handler`; archive, both binary hashes, full source tag and defined
  `sentry_gdextension_init` export are now verified above.
- Game reports `v0.98.2`, release identifier `f4eeecc6`; source/output hashes
  still required before claiming support for that release.
- Some IL-only PE headers reportedly changed AMD64 `0x8664` to ARM64 `0xAA64`.
  Validate each original image's CLR flags, ReadyToRun/native sections, signing,
  method bodies and exact hashes before permitting any such transformation.

The implementation must take an arbitrary user-selected directory. Neither
the user's personal paths nor access to their machine are prerequisites for
general workflow development with synthetic fixtures. Exact clean hashes and
deployment evidence remain required to enable a real build-specific recipe.

### Earlier failed clean source report (superseded)

The returned `sts2-clean-inventory.json` is a version-1 Windows-layout report
with zero files hashed, `inventory_complete: false`, and 218 identical
"file changed; close the game and rerun" errors. It supplies no usable clean
fingerprints. The pattern is consistent with the collector comparing Windows
handle-stat and path-stat identities or timestamp precision across different
APIs; it is not evidence that all game files changed. The uploaded UTF-16 JSON
was parsed successfully without modifying it.

Collector version 2 compares descriptor stats before/after and path stats
before/after separately, verifies the byte count against both sizes, and keeps
the cross-API identity guard on POSIX. It reports differing stat field names,
not raw IDs/timestamps. Synthetic Windows API tests exercise unchanged files,
real modifications, path replacements and size mismatches. The corrected
collector subsequently succeeded on Windows, as recorded above. Do not promote
the earlier failed report or unverified reverse-engineered game PE header
hashes to clean-input pins.

`inventory_package.py` is standard-library-only and can be streamed into a
Python heredoc in the user's existing SSH session. It hashes all regular
package files, including assets and backups, and reads ELF identification and
whitelisted .NET runtime identifiers. It does not follow directory or file
symlinks, load libraries, call Steam, print launcher/configuration contents,
dump the environment, or write files. External symlink targets are redacted.
Directories named `.git`, `saves`, `logs`, or `userdata` are explicitly excluded
and listed; `.godot` assets are retained. Close the game while collecting.
Filesystem access may update access times under the device's mount policy.

`inventory_complete` only means the eligible tree was read without errors.
It does not resolve external dependencies, establish engine versions from
filenames, validate ELF exports, prove portable IL, or authorize redistribution.
The tree hash covers relative file records, not excluded data or external files.
Runtime binaries outside the package still require a separate inventory once
the launcher and user-provided build records identify them.

After receiving this inventory and clean-source fingerprints, request only the
specific launcher/configuration or binary files needed to explain differences.
Then implement a standalone staged conversion with exact source guards before
connecting detection, runtime caching, CLI, or GUI. Keep unsupported .NET builds
rejected; reuse the existing backend's staging/rollback and shared CLI/GUI route.

## Validation boundary

Synthetic inventory tests cover repeatability, hashes, no writes, ELF byte order,
runtime configuration filtering, declared exclusions, symlinks, malformed files,
special files, changed-file refusal and Windows stat API differences. Existing patch tests cover deterministic
hashes and rollback; the CLR harness checks real typed IL behavior independently
of the device. No proprietary assembly or native binary belongs in this branch.

The full experiment Python suite passed 171 tests with no skips, with local
inspection fixtures and the verified runtime archives available. Local checks include the
existing IL/patch/CLR behavior coverage, eight deployment
config tests and nine packed-extension tests. The new PCK tests cover v2/v3 file
bases and directories, read-only operation, actual payload MD5 mismatches,
metadata relocation vs content changes, removals, encrypted/sparse/unknown flag
refusal, duplicate paths, symlinks, bounds, changing files and the complete
published heredoc. These are local tests, not a run on the Frame.
Sixteen manifest adaptation tests cover both captured bytes and independent
synthetic fixtures. An isolated run without full-text captures passes eight
synthetic tests and explicitly skips the optional device-capture class; no
raw game-file extract is needed for synthetic coverage. Two additional source
diagnostic tests verify the complete Bash/PowerShell Python bodies and execute
the Bash block in a synthetic directory without repository dependencies.
Five additional collector regressions cover Windows stat API differences,
descriptor changes, path replacement, byte-count mismatches and the retained
POSIX cross-API guard. All 16 inventory tests pass, including exact published
script matching. The user has now successfully executed the complete PowerShell
inventory wrapper on Windows; it has not been run on Windows in this workspace.
Nine comparison tests cover mapped counts, input preservation, metadata-only
differences, UTF-16 input, invalid/incomplete checksums and records, collisions,
archived observations and the exact clean-wrapper/prototype PE relationship.
The current focused run passes eight managed-adaptation tests, including two
new release-observation checks binding metadata to the correct inventory and
keeping v0.107.1 separate from the matching source. Those tests also cover both
archived source observations, game and
wrapper source/counterpart identities, complete output hashes, unchanged inputs,
idempotence, rejection of unknown/mixed/intermediate pairs and metadata/output
guards. These are local in-memory tests, not a new conversion run or device test.

Seven dependency-inspection tests pass, including synthetic schema/duplicate and
hash refusal, bounds, unknown-content redaction, CLI UTF-16 read-only handling,
symlink refusal, archive-to-inventory linkage and optional actual-capture
reproduction (executed with the local upload). Source contents remain unmodified.
Both full graphs have now been inspected above. Eleven deployment-adaptation
tests cover independent synthetic graphs, input preservation, idempotence,
unknown/cross-mode/platform refusal, semantic/byte pins, full captured replay,
unchanged non-runtime records, the isolated RID correction and all official
package member hashes. Optional actual-capture/package tests were executed
with the local uploaded files and downloaded artifact. Preserve raw captures
outside distributable fixtures and continue excluding the unverified Windows
Steam replacement.
Four runtime-provenance tests additionally pass with both downloaded artifacts:
full Godot template/Sentry archive checksums, selected-member hashes/ELF headers,
prototype linkage and the defined Sentry entry symbol. Four Spine-probe tests
pass for bounded/symlink searches, read-only command scope, failure privacy and
actual Git repository preservation. Four targeted Spine-build diagnostic tests
also pass for scoped operations, missing/symlink guards, bounded untracked output,
failure privacy and modified synthetic Git tree preservation. Six source-copy
tests cover deterministic hash summaries, changed/missing/extra sources, bounded
traversal, failed-tree withholding, symlink/size/concurrent-change guards, binary
inventory comparisons and the received checkout pins. Two further tests validate
the received copy/output observation and the independently downloaded pinned API
source. Four FMOD diagnostic tests cover bounded/guarded diff disclosure, traversal
and symlink limits, failure privacy, unknown-commit withholding and real modified
Git metadata preservation. Five header-diagnostic tests cover exact raw-byte
hashes, expected-HEAD/path guards, failure privacy, bounded diffs, concurrent
changes and staged/unstaged real synthetic Git edits with no metadata writes.
They also verify the archived linker-guard diff hash and preserve the unknown
header-change finding. Seven source-adaptation tests cover exact upstream replay,
AST/header preservation, paired idempotence/restoration, unknown/mixed input and
anchor/output guards. Five SDK diagnostic tests cover metadata disclosure,
internal/external aliases, size/concurrent-change and ELF byte-order handling,
missing inputs, no writes and prototype pins. An additional test validates the
received SDK/layout result. Fourteen pack-writer tests cover byte/offset retention,
streaming, exact manifest replay, malformed inputs, failure cleanup, destination
races, portable stat checks, CLI/source guards and the independent official
Godot FileAccess smoke test. All these checks
are included in the completed 171-test run; they do not establish a fresh
conversion or device acceptance.

Reproduce the hash-only comparison locally:

```bash
python3 experiments/sts2-steamworks/compare_inventories.py \
  experiments/sts2-steamworks/clean_inventory_v2.json \
  experiments/sts2-steamworks/prototype_inventory_v1.json
```
The existing repository suite reports 30 passes and two pre-existing failures
in the GodotSteam data-copy tests (boolean identity assertions against the
helper's Path/None return values). No existing test or backend was weakened.

Final hardware acceptance must use original legitimate files and a fresh output
directory, not this prototype. Do not open an implementation PR or claim a
supported conversion until local integration tests and that clean run succeed.
