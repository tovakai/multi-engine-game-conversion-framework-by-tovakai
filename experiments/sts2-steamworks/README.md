# STS2 Steamworks investigation

## Current Milestone: Standalone Converter

See [HANDOFF.md](HANDOFF.md) for the publication boundary, precise test coverage,
generated/supplied file origins, preserved Steam recipe provenance, remaining
reproducibility work and physical Frame acceptance procedure.

`convert_sts2.py` now implements the complete isolated, out-of-place pipeline
for the exact v0.98.2 source recipe. Standard-library Python on Windows or Linux
is sufficient. It accepts any installation directory, three pinned official
archives and five explicitly supplied, hash-verified native files. It stages,
validates, publishes to a new directory and optionally creates a portable tar.
No proprietary binaries, prototype game files or SDK builds are prerequisites
for the conversion software itself. Actual clean conversion/Frame acceptance
remain pending. See [STANDALONE.md](STANDALONE.md) for the single consolidated
preparation, conversion, transfer, Steam launch, rollback and failure procedure.

Latest local validation: **196 tests passed, no skips**, using the supplied
inspection fixtures and cached official artifacts. This includes a relocated,
stdlib-only CLI integration test, real managed recipes, official archive
extraction, independently read synthetic packs, failure cleanup and tar transfer
round-trip. The complete successful fixture output has 226 manifest-tracked
files. Required but locally unavailable game/native inputs remain synthetic in
these tests; this is not a clean-source or actual-Frame acceptance claim.

`package_converter.py NEW.zip` packages only the fixed software, profile,
documentation and license allowlist, excluding inspection captures, games, SDKs
and native/runtime binaries. The distribution needs Python 3.10+ only.

The sections below retain the historical investigation and its evidence limits;
older statements about incomplete converter work describe those earlier stages.

This experiment is isolated from the conversion backends. The Frame is remote;
local verification does not establish device compatibility. The user reports
that startup works on the Frame after generic-v1, client023-v2, and stats013-v3,
and subsequently confirmed gameplay, audio, mouse, gamepad, and Frame controls.
This is user-reported prototype success, not validation of a clean conversion,
stats writes, achievements, authentication, cloud synchronization, or extended
play/save testing. The historical results below explain the context and stats
compatibility changes.

The integration task is isolated on `feature/sts2-arm64-conversion`. See
[INTEGRATION.md](INTEGRATION.md) for recovered dependency provenance and the
remaining reproduction gates. The initial read-only Frame inventory used the
complete standalone Bash block in [FRAME_INVENTORY.md](FRAME_INVENTORY.md).
Do not use the already prepared prototype as a final converter input.

The prototype inventory has now been received, its canonical checksum verified,
and its hash-only file records archived in `prototype_inventory_v1.json`.
The completed focused deployment diagnostic is `probe_deployment_config.py`, published
as a complete Python heredoc in the conversation. It reads only nine verified
launch/deployment/configuration files; it does not launch STS2 or hash the large
PCK backups again. Review the returned launcher text before sharing publicly.

Its response is preserved in `prototype_deployment_v1.json`: the deployment
declares self-contained .NET 9.0.7 / Linux ARM64, but the loose Sentry manifest
is an invalid override-test file. Do not incorporate that file into a recipe
or assume it was loaded. The completed read-only device step used the complete block
in [FRAME_PACKED_EXTENSIONS.md](FRAME_PACKED_EXTENSIONS.md), inspecting actual
packed extension manifests and comparing declared resource metadata.

That packed-resource result has now been received: current FMOD and Sentry
manifests contain the real ARM64 mappings, while Spine and the extension list
are unchanged across the three observed packs. `adapt_packed_manifests.py`
reproduces the exact FMOD/Sentry manifest bytes with idempotent, hash-guarded
in-memory edits. It is a resource adaptation helper, not a complete conversion
recipe; pack output is now implemented separately in `patch_pack.py` below.
The full-text captures are ignored local fixtures; only hash-only packed
observations are intended for distribution. Synthetic adaptation tests run
without the captures; optional local capture tests additionally validate the
actual observed bytes.

The corrected version-2 inventory has now succeeded on the user's Windows
installation: 218 hashes, no errors, and a locally verified tree checksum.
`clean_inventory_v2.json` preserves the hash-only observations;
`compare_inventories.py` reproduces `clean_prototype_comparison_v1.json` after
mapping only the Windows data-directory name to the prototype's ARM64 name.
The clean wrapper matches the inspected pre-patch wrapper with its PE machine
field restored to AMD64, but the clean game DLL and pack differ substantially.
Do not apply the old game stats patch to this new input or assume the prototype
release is the current clean release. The first installation's release metadata
now identifies `v0.107.1` / `59260271`, not the prototype build.

A second returned inventory, kept separately as `matching_build_inventory_v2.json`,
contains 229 files and matches both inspected managed originals after PE machine
restoration. Its pack is identical to the prototype's pre-Sentry backup and its
release-info hash equals the prototype's. `prepare_managed.py` reproduces the
validated final managed pair from those exact source bytes in memory, with no
file writes, Steam calls, new patch offsets or package/backend integration.
The corrected metadata probe now also confirms `v0.98.2` / `f4eeecc6`, stored
in `matching_build_release_observation_v1.json` and tied to that inventory's
release-info hash. This is not yet a clean-installation converter: the second tree contains an
unverified replacement Windows Steam DLL, its backup and `steam_settings`.
Do not copy those into the output or infer publisher-pristine provenance from
matching game hashes. The original matching-build `sts2.deps.json` has now been
received and its 35,171-byte SHA verified against the inventory.
`inspect_dependency_graph.py` reproduces `source_dependency_observation_v1.json`
without distributing the raw file: the graph declares win-x64, 19 libraries,
169 managed runtime-pack assets and 15 Windows-native assets. Individual library
record hashes retain comparison evidence for the game/third-party dependencies.
The full working prototype graph is now received and hash-verified as well.
`adapt_deployment_graph.py` replays every observed structured change from the
original: 17 other target records, all 169 managed runtime declarations and all
library metadata values are preserved. Stable JSON serialization is deliberate,
so replay is semantically exact, not byte-identical to PowerShell formatting.

The observed graph retains a Windows RID fallback under its Linux key. An
explicit, separate `official-linux` candidate changes only that list to the
official framework's `linux`, `unix-arm64`, `unix`, `any`, `base` fallbacks.
The candidate is hash-guarded and tested but not installed or device-validated.
No existing Steamworks recipe or working prototype has been changed.

The official NuGet ARM64 9.0.7 package is now fingerprinted in
`dotnet_runtime_907_provenance_v1.json`: its SHA-512 matches the official HTTPS
response header, and all 186 package deployment files equal the prototype's
reported hashes, including hostfxr and all 15 AArch64 native files. NuGet's
signature verifier returned exit 0 with revocation-server warnings; full online
chain/revocation validation is not claimed. Raw captures and runtime binaries
remain outside the checkout. The official Godot Mono 4.5.1 export-template
archive also passes its published SHA-512 checksum, and its
`templates/linux_release.arm64` member equals the prototype engine's full hash
and size. `godot_mono_451_provenance_v1.json` records the exact release-member
origin; no editor or custom build is required to explain that executable.
Sentry's official 1.5.0 archive passes its publisher-displayed SHA-256, and both
selected ARM64 native members match the prototype. Source tag and entry export
are pinned in `sentry_godot_150_provenance_v1.json`. Its larger official manifest
is not adopted in place of our adapted game resource; third-party notice review
remains required. Package staging and remaining native provenance
still gate converter integration and fresh hardware acceptance.

The first Spine device request was `probe_spine_checkout.py`, provided as a complete
standalone Python heredoc. It searches only bounded directory depths under home
and the experiment's SD card for `spine-runtimes` checkouts, skips common
cache/Steam/personal-data folders and symlinks, and reports read-only Git commit,
branch, tracked changes and submodule metadata. It performs no fetch/build or
binary execution and disables Git optional locks/fsmonitor. No found checkout
or an incomplete search is an explicit unresolved source pin, not inferred
provenance. Four local tests cover bounds, command scope, failures and actual
synthetic Git repository/index preservation.

The returned candidate pin is `e7dc1435fa4a0083ab431f1b28e083c14a1f5c68`
on branch `4.2`, archived in `spine_checkout_observation_v1.json`. Tracked status
timed out and permission errors made discovery incomplete; no clean-worktree or
binary/source correspondence is claimed. The next targeted device request is
`probe_spine_build_inputs.py`: scoped tracked changes, bounded untracked path
listing and the nested `godot-cpp` commit. It uses longer operation timeouts and
does not fetch, build or disclose source contents. Four additional local tests
verify output/error handling, refusal guards and modified Git tree preservation.
The targeted response is archived in `spine_build_inputs_observation_v1.json`:
Spine keeps the same commit, nested godot-cpp is pinned to
`27d9dd23c83871e0619fca5dc2cddfbfd69e926a`, and both reported status scopes are
clean with no non-ignored untracked paths. The actual build compiles an ignored
copy of the Spine C++ tree, so the follow-up static check was `probe_spine_copy.py`:
selected original/copied source hashes, optional build-input fingerprints and
build-output/deployed library equality against the known inventory. It neither
builds nor executes anything. Spine's pinned license is not MIT; authorization
and required notices must be reviewed before distribution automation.
The returned `spine_copy_observation_v1.json` reports 158 matching original/copied
source records and identical build, example and deployed library fingerprints.
Optional custom.py/dev markers are absent. The API JSON also matches a separate
upstream download at the pinned godot-cpp commit, recorded without raw source in
`spine_upstream_api_provenance_v1.json`. This does not establish a reproducible
native build or license authorization. The FMOD checkout diagnostic targeted only
FMOD checkout/submodule pins, status and the guarded SConstruct diff using
`probe_fmod_checkout.py`. SDK files and logs are not disclosed or executed.
The received `fmod_checkout_observation_v1.json` confirms the extension commit,
godot-cpp `e83fd0904c13356ed1d4c3d09f8bb9132bdc6b77` and exact ARM64 guard
around the two x86 linker flags. Its diff hash is independently verified, but an
additional `src/helpers/common.h` modification initially prevented calling the local edits
fully recovered. The follow-up diagnostic was `probe_fmod_header.py`: guarded
base/current hashes and bounded diffs for that header and SConstruct only.
No source patch, SDK inspection or compilation is performed.
Its result, `fmod_source_observation_v1.json`, shows only an explicit `<cstdio>`
include added before the existing header guard. Both base files match separate
upstream downloads at the pinned commit. `adapt_fmod_build_sources.py` reproduces
the exact observed pair, restores the originals, preserves extra resources and
refuses mixed/unknown pairs, with unique anchors and complete output hashes.
All operations are in memory; no native build or file installation is enabled.
Seven adaptation tests include actual upstream source bytes, full SConstruct AST
preservation except the architecture guard, paired idempotence and reversal.
The read-only Frame diagnostic, `probe_fmod_sdk.py`, fingerprints selected
SDK headers/aliases and compares surviving build/deployed libraries with the
prototype inventory. It discloses no SDK contents and loads/builds nothing;
external alias targets are refused. Five synthetic tests cover its metadata,
link boundary, size/change/ELF guards, no writes and comparison pins.
Its received result is recorded as `fmod_sdk_observation_v1.json`: all 13 paths
exist, the SDK version token is 2.03.15, internal aliases resolve to the ARM64
`.so.14.15` runtimes, and both runtimes plus the extension build output match
deployed fingerprints. This completes the pending selected-file check; fresh
native build reproduction and license authorization are separate work.

`patch_pack.py` now provides actual out-of-place PCK output, keeping all original
asset bytes/offsets and appending only new manifests/directory metadata. It
guards the full original source SHA/size, reuses the exact manifest recipes,
refuses overwrite/symlink/invalid inputs and cleans failed unpublished output.
Fourteen local tests include an independent official Godot 4.5.1 x86-64 reader
smoke test, byte/offset preservation and the received manifest bytes in synthetic
packs. No real source pack or Frame test has been run here. Its CLI accepts
selected SOURCE.pck and NEW_OUTPUT.pck paths; this is a pack step, not a complete
game converter. See INTEGRATION.md's Shorter Critical Path: move to standalone
staging using explicit authorized, hash-verified native inputs, defer fresh native
rebuilds, and batch the eventual device handoff. No further diagnostic is needed
from the user for this milestone.
Eight source-copy tests and four FMOD diagnostic tests cover hashes, privacy,
bounds, guards and real Git metadata preservation. Five further header-diagnostic
tests pass for raw-byte hashing, scope, guard/failure withholding, concurrent
change refusal and staged/unstaged synthetic diff coverage. The full suite passes
171 tests with no skips and local fixtures/artifacts available.

The user supplied the output of `collect_startup.py`, following a game
popup reporting `k_ESteamAPIInitResult_FailedGeneric`. The installed DLL hash
matches `808393ad362ef694e506d6b722bf4357014b1f2cdb19256d0f467c89b9ac02de`.
Startup log lines 530-535 report initialization attempted, Steam running,
successful loading of `steamclient.so`, and then `FailedGeneric` with an empty
error message. Both retries report the same result. The earlier entry-point
exception is absent from the supplied Steam log context. The log does not name a
failed interface or explicitly expose the native initialization result.
`collect_startup.py` reads the hash and log without changing files.

The user then ran `probe_context.py`, which initializes genuine Steam in a
separate process and replays all 26 interface acquisitions from the uploaded
context in order. It uses the GameSearch/MusicRemote generic redirects, the
pipe-only Utils signature, and the context's exact NetworkingUtils user/server
fallback. It verifies the native and patched managed hashes before loading the
library, records native initialization separately, and stops at the first zero
pointer. It modifies no DLLs and performs shutdown after successful native
initialization. This is an active native probe, with normal Steam initialization
side effects.

The supplied ordered-probe result has native initialization result 0, an empty
native error message, nonzero `SteamClient021`, and HSteamUser/HSteamPipe both 1.
The first 11 interface requests, through GameSearch, return nonzero pointers.
The first zero pointer is HTTP, requested as
`STEAMHTTP_INTERFACE_VERSION003` through
`SteamAPI_ISteamClient_GetISteamHTTP`. The probe stops there and calls shutdown.
No probe errors are reported; both native and patched managed hashes match.
This establishes the first failing check in the separate-process replay.

The user then ran `probe_http.py`, comparing that exact HTTP version through the
dedicated accessor, the genuine generic accessor, and
`SteamInternal_FindOrCreateUserInterface`. The dedicated and generic declarations
in the uploaded assembly have identical signatures and both use Cdecl. The
internal getter takes only HSteamUser and the version string. This focused probe
performs no HTTP operations, changes no DLLs, and does not replace the requested
interface with another version.

The supplied HTTP result confirms native initialization result 0 with no error
message and matching hashes. The dedicated HTTP accessor returns zero, while
both the generic accessor and `SteamInternal_FindOrCreateUserInterface` return
the same nonzero pointer for `STEAMHTTP_INTERFACE_VERSION003`. Shutdown was
called. This establishes a genuine alternate route for the requested version;
it does not test HTTP operations or identify why the dedicated accessor fails.

An incremental `http-generic-v2` recipe is prepared locally. It accepts only the
verified v1 DLL and changes the HTTP wrapper's call operand at file offset
2897 / `0xB51` from `0x06000548` to the existing generic native method
`0x0600053D`. Only one additional byte changes (`0x48 -> 0x3D`). The candidate
hash is `c85f06c0aa27c8e498e4d4bd8c73ed818f810d2ba7e1565bb3c415230eb269af`.
Local parsing confirms 1995 other managed method bodies unchanged, including
the full context and its guards. Both incremental install/restore chains were
tested locally. The v2 backup preserves the v1 DLL; restoring v2 first permits
restoration of v1 to the original. The existing v1 recipe remains the default.

The HTTP candidate has not been installed on the Frame. The subsequent test
was `probe_context.py --http-generic`: it replays the same context requests while
using the confirmed generic HTTP route only inside the native probe, leaving the
installed DLL untouched. The output marks this as `http_generic_override` on a
v1 installation and stops at any later zero pointer. It also recognizes an
installed v2 DLL by its exact hash and uses the corresponding route automatically.
The user executed the HTTP-override context replay. HTTP now returns a nonzero
pointer, and the next failure is UGC: the dedicated
`SteamAPI_ISteamClient_GetISteamUGC` returns zero for
`STEAMUGC_INTERFACE_VERSION020`. Native initialization again returns 0 with no
error, both hashes match, and shutdown is called. Native output includes
`Missing interface adapter for STEAMUGC_INTERFACE_VERSION020 Controller`.
This suggests a native accessor dispatch/layout mismatch rather than proving
that UGC itself is unavailable. The HTTP candidate remains uninstalled on the Frame.

The user then ran `probe_http.py --interface UGC --disassemble`. The route probe
now supports the two verified HTTP/UGC signatures while preserving its default
HTTP behavior. It requests the exact UGC version through dedicated, generic,
and internal user-interface routes. It also reads embedded `SteamClientNNN`
strings and, if available, uses `objdump` to capture the GenericInterface, HTTP,
and UGC native accessor instructions. Static output explicitly reports missing
tools, command errors, truncation, and whether a symbol label was found. Version
strings alone do not establish the active client contract.

The UGC native declaration and the generic native declaration in the uploaded
DLL have identical signatures and use Cdecl. No UGC redirect or interface-version
substitution is implemented. No optional-interface omissions are implemented.
These diagnostics perform no interface methods beyond pointer acquisition and
modify no game files.

The supplied UGC result confirms native initialization result 0, matching hashes,
and shutdown. The dedicated accessor returns zero; the generic and internal user
routes return the same nonzero pointer for the exact requested UGC version.
The native library embeds `SteamClient017` and `SteamClient023`. Disassembly
shows thin vtable dispatches at byte offsets 96 (GenericInterface), 184 (HTTP),
and 200 (UGC). On ARM64 these are slots 12, 23, and 25 respectively.

Comparison with Valve's SDK headers vendored in Proton establishes the mismatch:

| Accessor | SteamClient021 (SDK 1.62) | Native / SteamClient023 (SDK 1.63) |
| --- | --- | --- |
| GenericInterface | slot 12 / 96 bytes | slot 12 / 96 bytes |
| HTTP | slot 24 / 192 bytes | slot 23 / 184 bytes |
| UGC | slot 26 / 208 bytes | slot 25 / 200 bytes |

In the 021 layout, slot 23 is `BShutdownIfAllPipesClosed` and slot 25 is
`GetISteamController`. The latter explains the observed Controller adapter
message. Sources:

- [SDK 1.62 client header](https://github.com/ValveSoftware/Proton/blob/proton_10.0/lsteamclient/steamworks_sdk_162/isteamclient.h)
- [SDK 1.63 client header](https://github.com/ValveSoftware/Proton/blob/proton_10.0/lsteamclient/steamworks_sdk_163/isteamclient.h)

This identifies a matching client contract, not the library's SDK provenance or
runtime availability of that contract. The next single device test is
`probe_context.py --client-version SteamClient023` with the installed v1 DLL and
without `--http-generic`. It requests 023 only inside the probe, preserves both
existing generic redirects, and uses dedicated HTTP/UGC accessors and all original
interface versions and null guards. No client-version patch was installed for
this probe. The HTTP v2 candidate remains on hold.
JSON marks the requested version and the probe-only override. Nonzero pointers
still do not establish interface-method ABI compatibility or genuine game
authentication/ownership success.

Local reproducible call-recorder tests cover both client layouts, exact routes,
all 26 early-stop guards, unavailable client, failed initialization, and shutdown:

```bash
python3 -m unittest discover -s experiments/sts2-steamworks -p 'test_probe_context.py' -v
```

## Confirmed SteamClient023 context acquisition

The user supplied the Frame version-3 probe result: native initialization 0 with
empty error text, no probe errors, HSteamUser/HSteamPipe 1, nonzero
`SteamClient023`, all 26 interface pointers nonzero, and shutdown called.
Both hashes match the inspected native library and installed generic-v1 DLL.
`http_generic_override` and `installed_http_generic_redirect` are both false;
HTTP and UGC work through their dedicated native accessors. This validates the
client version for context acquisition on the Frame, not interface-method ABI
compatibility, gameplay, authentication, or ownership.

`client023-v2` is the next isolated recipe; it accepts only generic-v1 and is
an alternative to the uninstalled HTTP v2, not a layer on top of it. It changes
one byte at file offset 360492 / `0x5802C` (`0x31 -> 0x33`) in the UTF-16
user-string entry at offset 360466 / `0x58012`, changing `SteamClient021` to
`SteamClient023`. Target SHA-256:
`7dd9a985d68666096bdf8941497cc38e911561179998119a151373d9ea928db5`.
The shared `ldstr` token is `0x700006FD`. Static inspection of every managed
method finds exactly two references: `CSteamAPIContext.Init` and
`CSteamGameServerAPIContext.Init`. Both now request the native library's client
contract. No game-server test has been performed. No IL instructions, native
imports, individual interface versions, null guards, authentication/ownership
calls, or method bodies change relative to v1; the two v1 redirects remain.

Generate without installation:

```bash
python3 experiments/sts2-steamworks/patch_accessors.py /path/to/Steamworks.NET.generic-v1.dll --recipe client023-v2 --output /path/to/Steamworks.NET.client023-v2.dll
```

With STS2 closed, explicit installation uses
`Steamworks.NET.dll.before-client023-v2` as its verified, non-overwritten v1
backup. Restore this layer before restoring generic-v1:

```bash
python3 experiments/sts2-steamworks/patch_accessors.py --recipe client023-v2 --install
python3 experiments/sts2-steamworks/patch_accessors.py --recipe client023-v2 --restore
```

These repository commands are for local/tool-transfer workflows. The user runs
a complete self-contained Python heredoc in their existing Frame SSH terminal,
without a dependency on this checkout. The user subsequently reported successful
managed Steam initialization with this recipe; game startup now fails in stats
initialization, as recorded below.

Local dnfile/dncil validation confirms the exact one-byte difference, only the
two shared string references, and all 1996 managed method bodies unchanged from
generic-v1. Reproducible installer and probe checks run with the original wrapper
fixture explicitly provided (installer tests otherwise report a skip):

```bash
STS2_WRAPPER_DLL=/path/to/Steamworks.NET.frame.dll python3 -m unittest discover -s experiments/sts2-steamworks -p 'test_*.py' -v
```

These checks test local temporary files and mock native calls, not the Frame.
The ordered probe now recognizes the client023-v2 hash and selects 023 by
default for that DLL, avoiding accidental replay of the old layout after
installation. An explicit client-version override is still marked in JSON.

## Stats initialization investigation

The user reports `Steamworks initialization succeeded!` on the Frame, followed
by `EntryPointNotFoundException: SteamAPI_ISteamUserStats_RequestCurrentStats`
from `SteamUserStats.RequestCurrentStats`, `SteamStatsManager.Initialize`, and
`NGame.GameStartup`. Preserve the working client023-v2 patch. The reported
settings and real Steam remote-storage writes do not establish server cloud
synchronization, stats, achievements, authentication, ownership, or gameplay.
DXGI system-info logging and controller action-cache errors are deferred;
there is no evidence yet establishing a causal relation to the stats exception.

Static inspection of the uploaded wrapper shows `RequestCurrentStats()` calls
`InteropHelp.TestIfAvailableClient`, `CSteamAPIContext.GetSteamUserStats`, then
`NativeMethods.ISteamUserStats_RequestCurrentStats` and returns its bool result.
The native import has signature `00010218` (bool result, pointer argument) and
Cdecl. The wrapper contains no game-specific readiness/callback logic.
Only this wrapper was available at that stage; the actual game assembly was required
to inspect the manager, surrounding initialization, return-value consumption,
callback registration/handlers, readiness fields, and reads/writes of those
fields before choosing a patch. No fake callback is implemented.

Valve's SDK 1.63 header vendored in Proton comments out RequestCurrentStats,
states that Steam synchronizes stats and achievements before the game process
begins, and changes the stats interface to version 013. The managed context
still requests version 012. Static inspection of the native stats thunks is
also needed to check actual ABI compatibility before relying on remaining
stats/achievement methods. This is a question to verify, not a reason to change
interface versions blindly or fake readiness. Source:
[SDK 1.63 stats header](https://github.com/ValveSoftware/Proton/blob/proton_10.0/lsteamclient/steamworks_sdk_163/isteamuserstats.h).
The user's linked partner documentation returned HTTP 403 to the cloud fetch;
the public header provides independent evidence of the changed contract.

`locate_stats_artifacts.py` reads DLL identifiers and hashes without executing
code, following directory symlinks, writing files, or initializing Steam.
Identifier hits are only candidate locations, not decoded IL or proof of
callback dependencies. It records the installed wrapper/native hashes and
prints exact SCP retrieval commands (replace FRAME_HOST) for candidate game
assemblies and the native library. No fresh game run is requested until the
actual IL is inspected and an evidence-supported patch is tested locally.

The user supplied the locator result: 185 DLLs scanned, no errors, and the
working wrapper/native hashes both match. The only game candidate is
`data_sts2_linuxbsd_arm64/sts2.dll`, 8870912 bytes, SHA-256
`3f41afab3a499e40ddcc017ab672a1efdf236b038ac17b6badfdd825f19f7481`, with
SteamStatsManager, RequestCurrentStats, and UserStatsReceived_t identifier hits.
The native library is 381904 bytes with the previously recorded hash. Both
binaries were subsequently uploaded and their hashes verified locally;
identifier hits alone did not establish the game's callback dependency.

## Actual stats IL and isolated stats013-v3 candidate

`inspect_stats.py` decoded all 46701 managed method bodies with no errors and
disassembled all 44 native stats thunks. The game has no strong-name signature
or ReadyToRun header. Findings from the supplied game assembly:

- `SteamStatsManager.Initialize` is MethodDef `0x06000F7C`, RVA `0x58D48`, file
  offset `356168 / 0x56F48`, with a 12-byte header and 82-byte IL body.
- It checks `SteamInitializer.Initialized`, resets user/global readiness and
  cached global damage, registers the real `Callback<UserStatsReceived_t>`,
  calls RequestCurrentStats (discarding its bool), then runs RefreshGlobalStats
  through TaskHelper.RunSafely. This is the only game call to RequestCurrentStats.
- OnUserStatsReceived checks AppID 2868840 and EResult.OK before setting
  `_userStatsReady`; the only read of this private field gates
  IncrementArchitectDamage. The startup state machine calls Initialize and
  next awaits its cloud-save task, not user stats readiness.
- Global stats have their own genuine RequestGlobalStats async call-result,
  GetGlobalStat, and readiness path. These methods remain unchanged.
- In the supplied game DLL, AchievementsUtil initializes NullAchievementStrategy,
  Unlock is already a ret-only method, and there are no direct Steam achievement
  API MemberRefs. The experiment did not introduce these behaviors and does not
  change them or establish working Steam achievements.

Every native stats thunk matches the SDK 1.63/version-013 slot order: GetStatInt32
uses slot 0, GetAchievement slot 5, StoreStats slot 9, RequestGlobalStats slot 37,
and all 40 remaining thunks match too. Version 012 contains RequestCurrentStats
at the beginning, so feeding its pointer to these newer thunks is incompatible.
The factory must request 013 before relying on their results.

`patch_stats.py` implements a paired `stats013-v3` candidate:

| File | Verified Source SHA-256 | Candidate SHA-256 | Changed Bytes |
| --- | --- | --- | --- |
| Steamworks.NET.dll | `7dd9a985d68666096bdf8941497cc38e911561179998119a151373d9ea928db5` | `e214b36dda06df40901cd5b0fb043045b7aa626475c0154f7ca421bb725fde14` | 1 |
| sts2.dll | `3f41afab3a499e40ddcc017ab672a1efdf236b038ac17b6badfdd825f19f7481` | `c27aedddd408500ab05ac3c045f41c3f224e3db19c4a6904b5581cc4f588351c` | 54 |

The wrapper changes only the user-stats factory version's last digit at file
offset 360744. SteamClient023, the two generic redirects, all wrapper method
bodies, and all authentication/ownership APIs remain unchanged.

The game changes only Initialize's existing 94-byte region. Instead of calling
the absent obsolete export, it performs the existing genuine
`SteamUserStats.GetStat("architect_damage", out int value)` and assigns its bool
result to `_userStatsReady`. A false result leaves readiness false; an exception
propagates rather than inventing success. This makes no stats writes. The same
real callback is registered and retained; its handler and AppID/result guards
are unchanged, and no callback is emitted or manually invoked by the adaptation.
The compiler-generated delegate cache optimization is removed to make room for
the read in the existing body, not the callback registration. It reuses existing
single-int local signature `0x11000004`, preserves max-stack 2/code-size 82/no EH,
and inserts four NOPs before the final ret. All other 46700 game method bodies
are byte-identical. Global-stat operations, leaderboard operations, achievements,
DXGI logging, controller input, save writes, and Steam authentication/ownership
paths are untouched. This is not a blanket stub of RequestCurrentStats: its
wrapper and native declaration remain unchanged for other callers.

The patcher defaults to read-only `--action inspect`. Installation requires the
known native hash and both known assembly hashes, preflights both backups,
creates exclusive `.before-stats013-v3` backups, preserves permission bits, and
atomically replaces individual files (wrapper first). It verifies the final
pair and rolls back changed files on a caught failure, refusing to overwrite
concurrent unknown changes. Two separate files cannot be atomically replaced
together: an abrupt process/power failure can leave a mixed pair. Verified
backups allow completing installation or restoring that pair. Restore changes
the game first and returns the wrapper to working client023-v2, not the original
unpatched DLL. Do not restore older layers before this one.

Reproducible local checks, with the original wrapper and supplied game/native
paths substituted for the environment variables:

```bash
python -m pip install -r experiments/sts2-steamworks/requirements-inspection.txt
python experiments/sts2-steamworks/inspect_stats.py "$STS2_GAME_DLL" "$STS2_NATIVE_LIBRARY"
STS2_WRAPPER_DLL=/path/to/original/Steamworks.NET.frame.dll STS2_GAME_DLL=/path/to/sts2.dll STS2_NATIVE_LIBRARY=/path/to/libsteam_api64.so python -m unittest discover -s experiments/sts2-steamworks -p 'test_*.py' -v
python experiments/sts2-steamworks/patch_stats.py --data /path/to/verified/fixture --action generate --output-dir /path/to/empty/output
dotnet build experiments/sts2-steamworks/clr-stats-tests/StatsTests.csproj --artifacts-path /tmp/sts2-clr-tests --nologo
dotnet /tmp/sts2-clr-tests/bin/StatsTests/debug/StatsTests.dll /path/to/empty/output/sts2.dll
```

Validation: 31 Python tests passed with all fixtures and inspection dependencies
present; all 44 stats thunk slots verified; all 46700 other game bodies and all
1996 wrapper bodies unchanged. The .NET 8 build had zero warnings/errors, and
five CLR checks passed using the candidate's exact IL with tokens rebound to
typed mocks: uninitialized guard, read false/true, exception propagation, and
reinitialization. No game assembly or native Steam library is executed locally.
The CLR caught an initial invalid placement of padding after the final ret;
that candidate was never sent to the Frame and the corrected final-ret layout
was rerun successfully. Installer tests cover exact hashes, permissions,
idempotence, unknown hashes, symlinks, backup protection, injected replacement
failure/rollback, mixed-pair recovery, generation, and restoration.

After receiving the paired installer and one-launch instructions, the user
reported "It works!". Record this as user-reported Frame startup success for
stats013-v3. No fresh installer hashes, startup log, stat values, or callback
payloads accompanied that result. It does not establish stats writes,
achievements, authentication, cloud synchronization, or gameplay compatibility.
Keep both patches and backups together. Controller input is the next deferred
investigation: first establish whether its action-cache errors persist after
successful startup, rather than assuming the earlier exception caused them.
GodotFrame integration remains out of scope pending fuller isolated validation.

Local checks verify exact HTTP/UGC route arguments, zero pointers, native init
failure, shutdown, version-string collection, optional disassembly output, and
JSON preflight refusal using call recorders. No native Steam calls were made
locally.

Local checks verify the candidate's single IL call change, both recipe hash and
backup chains, the HTTP-only probe override, and stopping at a subsequent failed
check. No native Steam calls were made locally.

Local checks verify all three route signatures and exact version arguments,
zero-pointer handling, native initialization failure, shutdown, and JSON preflight
refusal using call recorders. No real Steam calls were made locally.

Local checks compare every requested version string against the actual context
IL and verify order, both generic routes, Utils arguments, the NetworkingUtils
fallback, stopping at each of the 26 possible failures, shutdown, and JSON
preflight refusal. These checks use call recorders and do not run Steam locally.
The replay does not execute the managed wrapper inside Godot, dispatch game
callbacks, or establish ownership/authentication success.

The user reports a missing `SteamAPI_ISteamClient_GetISteamGameSearch` entry
point in `steam_api64`, reached from `Steamworks.CSteamAPIContext.Init()` through
`SteamAPI.InitEx()` and `MegaCrit.Sts2.Core.Platform.Steam.SteamInitializer`.
The log reports successful loading of the Frame's
`/home/steamos/.local/share/Steam/linuxarm64/steamclient.so` before the exception.
This does not establish that managed initialization, authentication, or ownership
verification completes. AppID is 2868840.

The user also reports 938 managed symbol candidates, 876 native matches, and
62 missing exports. Reported missing names include GameSearch, MusicRemote,
`SteamAPI_ISteamFriends_GetUserRestrictions`,
`SteamAPI_ISteamFriends_SetPersonaName`, and
`SteamAPI_ISteamUserStats_RequestCurrentStats`. This points toward a wrapper/API
surface mismatch, rather than wholesale absence of Steam. The actual managed
assembly was subsequently supplied and inspected locally. Native library
evidence comes from the user's executed Frame diagnostics.

## User-supplied Frame diagnostic

The user executed the read-only Python diagnostic on the Frame and supplied its
JSON output. It reports `aarch64`, no inspection errors, and 1117 dynamic exports
in each of these AArch64 shared libraries:

- `/opt/steamvr/bin/linuxarm64/libsteam_api.so`
- `/run/media/steamos/SD512/sts2-arm64-proto/data_sts2_linuxbsd_arm64/libsteam_api64.so`

Both have SHA-256
`9d354c631f01f7318bc00e8fa29842b83678f4293b52d0d5c11806edd76a7f4b`
and SONAME `libsteam_api.so`. Both lack GameSearch exports and the five named
missing exports above. Both export `SteamInternal_SteamAPI_Init`,
`SteamAPI_InitFlat`, `SteamInternal_CreateInterface`,
`SteamInternal_FindOrCreateUserInterface`, `SteamAPI_ISteamApps_BIsSubscribedApp`,
and `SteamAPI_ISteamUser_GetAuthSessionTicket`. Static availability does not
establish successful authentication or ownership verification. The absence of
`SteamAPI_Init` and `SteamAPI_InitEx` alone does not imply broken initialization:
the internal initialization entry point used by upstream managed `InitEx()` is
available.

The managed assembly is at
`/run/media/steamos/SD512/sts2-arm64-proto/data_sts2_linuxbsd_arm64/Steamworks.NET.dll`,
with SHA-256
`474a2af1328c2a2b32bedf8376ed46a50958423313856659ac05bee677d8fdd3`.
`readelf` is installed; `dotnet`, `ilspycmd`, and `monodis` are absent from PATH.
This assembly was subsequently uploaded for local metadata and IL inspection.
No process mappings were collected, and no compatibility patch was tested in
this first diagnostic.

## Inspection of the uploaded wrapper

The user supplied `Steamworks.NET.frame.dll`. Local static inspection confirms
the recorded SHA-256 exactly. Its assembly version is 1.0.0.0, its target
framework attribute is .NET 8.0, and its informational version attribute is
`1.0.0+c49be60d78117d599e17f278ab752151e27863d1`. These attributes do not by
themselves identify a released Steamworks.NET package version. No strong-name
signature is present.

The actual 61-byte `SteamAPI.InitEx()` method calls
`NativeMethods.SteamInternal_SteamAPI_Init` with a null interface-version-check
pointer. It proceeds to `CSteamAPIContext.Init()` only on native result zero.
The 990-byte context method acquires and checks interfaces eagerly, including
`SteamClient021`, `SteamMatchGameSearch001`, and
`STEAMMUSICREMOTE_INTERFACE_VERSION001`. GameSearch and MusicRemote pointers are
each stored and immediately compared with zero; acquisition failures return
false. Neither acquisition is optional in this assembly.

Both public accessor wrappers have 40-byte IL bodies with a UTF-8 handle and
try/finally disposal. Their native declarations and
`NativeMethods.ISteamClient_GetISteamGenericInterface` have identical signatures:
`0004181811873c11873812874c`. All import from `steam_api64` with Cdecl calling
convention, returning a native pointer and taking a native instance pointer,
32-bit HSteamUser, 32-bit HSteamPipe, and UTF-8 string handle.

This permits an isolated patch that redirects the existing native call targets
to the real generic-interface accessor without removing mandatory context
checks. The user ran `probe_interfaces.py` on the Frame to establish whether the
real Steam client returns these versioned interfaces before implementation.
This probe performs genuine native Steam initialization for AppID
2868840 in its own process, queries Apps as a control and the two interfaces,
then shuts down after successful initialization. It verifies the recorded native
library hash before loading it. It does not modify the prototype or apply a
patch. Native Steam may produce its normal initialization logs or other client
side effects; this is an active probe rather than static inspection.

The probe reports JSON on stdout and native logs on stderr. Exit status 0 means
all three pointers are nonzero, 2 means a preflight/init/inspection error, and 3
means successful initialization with at least one unavailable interface. Pointer availability does not
prove authentication, ownership verification, or successful gameplay.

## Confirmed interface availability and isolated patch

The user supplied the executed Frame probe result: native initialization returned
0 with an empty error message, both HSteamUser and HSteamPipe were 1, and
`SteamClient021` was nonzero. The real generic accessor returned nonzero pointers
for AppsControl (`STEAMAPPS_INTERFACE_VERSION008`), GameSearch
(`SteamMatchGameSearch001`), and MusicRemote
(`STEAMMUSICREMOTE_INTERFACE_VERSION001`). Shutdown was called. The native library
hash still matched `9d354c631f01f7318bc00e8fa29842b83678f4293b52d0d5c11806edd76a7f4b`.
This demonstrates interface acquisition through the real service, without
establishing individual GameSearch/MusicRemote operations or game compatibility.

`patch_accessors.py` changes only two IL `call` operands in the uploaded wrapper:

| Wrapper | Operand File Offset | Original Token | Replacement Token |
| --- | --- | --- | --- |
| `SteamClient.GetISteamGameSearch` | 2777 / `0xAD9` | `0x06000544` | `0x0600053D` |
| `SteamClient.GetISteamMusicRemote` | 3169 / `0xC61` | `0x0600054C` | `0x0600053D` |

`0x0600053D` is the existing
`NativeMethods.ISteamClient_GetISteamGenericInterface` declaration. Both wrappers
retain their original instance pointer, user and pipe handles, version strings,
UTF-8 handle lifetime, and try/finally disposal. Context acquisitions and zero
checks remain intact. Steam initialization, ownership checks, authentication
ticket calls, callbacks, and shutdown are unchanged. All original native import
declarations remain present; the patch does not add native exports or fake any
Steam responses. Other missing native methods are outside this patch.

The only changed bytes are `0x44 -> 0x3D` at offset 2777 and `0x4C -> 0x3D` at
offset 3169. The patched DLL has SHA-256
`808393ad362ef694e506d6b722bf4357014b1f2cdb19256d0f467c89b9ac02de`.
Local parsing confirmed the two redirected call operands and 1994 other managed
method bodies unchanged, with method sizes, signatures, and exception handlers
preserved. Installer tests covered generation, hash guards, exclusive output
creation, backup protection, permissions, installation, repeat installation,
and restoration. The subsequent user-supplied hash and failing startup log are
described above; the source of the generic result remains unconfirmed.

The patcher uses only Python's standard library. Default behavior generates a
separate DLL and leaves the input untouched:

```bash
python3 patch_accessors.py /path/to/Steamworks.NET.frame.dll --output /path/to/Steamworks.NET.generic-v1.dll
```

On the Frame, close STS2 before installation. The explicit install operation
uses the prototype path by default, verifies the exact original hash, creates
`Steamworks.NET.dll.before-generic-v1` without overwriting an existing backup,
and atomically replaces the assembly while preserving permission bits:

```bash
python3 patch_accessors.py --install
```

The restore operation accepts only this patch's exact hash and the verified
original backup:

```bash
python3 patch_accessors.py --restore
```

The initial device test used the user's existing STS2 launch command after
installation. The failing startup log required the ordered context probe, which
identified HTTP. The confirmed HTTP route now requires replay of the candidate
context before installing the next incremental patch. Keep each test to the
current change and use actual results to determine further work.

Local reproducible static inspection uses the pinned dependencies in
`requirements-inspection.txt` and the command:

```bash
python inspect_managed.py /path/to/Steamworks.NET.frame.dll
```

Local validation has checked the uploaded DLL's signatures and decoded IL,
the probe's architecture refusal, and its call ordering and shutdown behavior
using call recorders. No real Steam API calls or Frame tests were performed
locally. Game call sites have not been inspected.

## Upstream source comparison

Public Steamworks.NET source demonstrates eager GameSearch and MusicRemote
acquisition with immediate failure on a zero pointer in `CSteamAPIContext.Init()`:

- [2024.8.0, commit a2fc889](https://github.com/rlabrecque/Steamworks.NET/blob/a2fc889ab2672981ec3e6225d551d86ce6923121/com.rlabrecque.steamworks.net/Runtime/Steam.cs)
- [2025.162.1, commit af71004](https://github.com/rlabrecque/Steamworks.NET/blob/af710043b9097e8ffedf74d67503c3a7eb498260/com.rlabrecque.steamworks.net/Runtime/Steam.cs)

[2025.164.1, commit c21a8f0](https://github.com/rlabrecque/Steamworks.NET/blob/c21a8f0e31c56ae8707130967faf491f7dd7c0d8/com.rlabrecque.steamworks.net/Runtime/Steam.cs)
contains neither interface in its context. This is supporting evidence, not an
identification of STS2's wrapper version or a reason to replace the whole assembly.
Inspect the shipped context, interface constants, native declarations, and game
call sites before choosing a patch. If acquisition is unnecessary for STS2,
removing that acquisition and its paired zero-pointer check is a candidate for
an isolated change; blindly returning success from `Init()` is not.

## First diagnostic

From the local repository, replace `FRAME_HOST` with the user's SSH destination:

```bash
ssh FRAME_HOST 'python3 - /run/media/steamos/SD512/sts2-arm64-proto/' \
  < experiments/sts2-steamworks/diagnose.py
```

The script is streamed over SSH without creating a file on the Frame. It needs
Python 3 and `readelf` on the Frame, reads the prototype directory and the known
SteamVR ARM64 library location, and prints JSON to paste back. It reports missing
paths and inspection errors explicitly. It does not execute game binaries, load
libraries, initialize Steam, change files, or read environment variable values.
Library discovery does not follow directory symlinks; use `--library` for an
additional known path.

The report includes library SHA-256 hashes, ELF architecture and loader metadata,
selected genuine Steam exports, GameSearch exports, Steam-named assembly paths
and hashes, and available disassembly tools. An exported symbol only demonstrates
static availability. Absence from a
candidate does not establish that the candidate is actually loaded by STS2.

If a later diagnostic has an existing STS2 process ID, `--pid PID` additionally
reads that process's Steam shared-library mappings. It does not start a process.
The optional mapping probe uses paths visible to the SSH session; container mount
namespaces may require additional inspection.

## Next decision

Use the exception and report to determine whether the problem is library
selection, a wrapper/API version mismatch, or a missing flat export over a
supported real interface. Any forwarding implementation requires the exact
wrapper signature, matching native ABI and interface version, and evidence that
the underlying real Steam service supports the requested operation. A missing
symbol alone does not justify a stub, an authentication bypass, or disabling
Steam initialization. Ownership and authentication must remain genuine.

Integrate nothing into the conversion framework until an isolated change has
been tested on the Frame and the user has supplied results.
