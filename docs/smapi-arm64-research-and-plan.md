# SMAPI on MonoFrame: research and implementation plan

Research date: 2026-10-12. Status: research recorded; implementation deferred at
the user's request. No SMAPI converter implementation or
Frame testing performed for this investigation. All new inspection was done on
Windows, using public sources and a checksum-verified official installer.

## Recommendation

SMAPI support is a credible extension of MonoFrame. Keep the working vanilla
Stardew 1.6.15 / .NET 6.0.32 profile and add a separately versioned, opt-in SMAPI
profile. Start with the loader, bundled defaults, small event-driven mods and
Content Patcher fixtures. Establish ARM64 Harmony patching before claiming support
for the broader ecosystem or large overhauls.

The main uncertainty is runtime method patching and compatibility with the rebuilt
MonoGame framework, rather than an absence of a native .NET runtime. Our current
runtime already runs Stardew on ARM64. SMAPI and many mods contain managed code,
but some depend on native libraries, architecture-specific code or exact game
method bodies. Compatibility must be reported per tested configuration.

Do not replace the validated vanilla runtime, change the original installation,
require users to compile on Frame, or silently launch a modded save without its
mods. No Frame connection, process launch, installation or configuration change is
part of this research task.

## Evidence and reproducible inputs

| Item | Inspected input | What it establishes |
| --- | --- | --- |
| Current converter | `358b8fa`, `monoframe/` | Vanilla conversion, verified downloads, host preparation and Frame ZIP infrastructure already exist |
| SMAPI release | 4.5.2; released 2026-03-22 | A concrete release to evaluate against our Stardew profile |
| SMAPI source | `821167e5c511bf3a2d98f604e5e838561c469219` | Loader, manifest handling, build settings and Harmony initialization can be audited |
| Official installer | `SMAPI-4.5.2-installer.zip`, 41,889,142 bytes | Contains an inspectable Linux payload; installer was not executed |
| Installer SHA-256 | `dd01ddca7b566bfe0d3b3d2d03833496abc56c53da976241f2ab443f5484acc4` | Locally computed digest matched the release asset digest |
| Mainline port | `986097ce2e586abb799c40dfd7386b288fa8ae1b` | Existing optional SMAPI staging and validation fixture source |
| Current Pathoschild Harmony fork | `16078eb398cd9089bb1e752583097d9db04232d2` | A maintainer fork identifying itself as Harmony 2.4.2; candidate for evaluation, not an adopted dependency |

The [SMAPI website](https://smapi.io/) currently offers 4.5.2 and requires Stardew
1.6.14 or newer. Our 1.6.15 build meets that version requirement; this does not
establish ARM64 compatibility. The [official release](https://github.com/Pathoschild/SMAPI/releases/tag/4.5.2)
and its [asset metadata](https://api.github.com/repos/Pathoschild/SMAPI/releases/tags/4.5.2)
provide the release inputs above.

Private research receipts are under `build/smapi-research/`: the source checkout,
official installer, extracted Linux payload and `payload-audit.json`. These are
research artifacts, not changes to the converter or the user's installed game.
The local Steam installation had no `Mods`, `StardewModdingAPI` or `smapi-internal`
entry when inspected, so no real user mod collection was available to audit.

## Technical findings

### 1. The official Linux launcher is x64; much of its payload is managed

Static inspection of the verified Linux payload found:

| File | Observed format | Consequence |
| --- | --- | --- |
| `StardewModdingAPI` | ELF, machine 62: x86-64 | Do not execute or package this apphost as the ARM64 launcher |
| `StardewModdingAPI.dll` | AMD64 PE, CLR flags `0x1` | IL-only managed assembly, but architecture metadata needs assessment/preparation |
| `ConsoleCommands.dll`, `SaveBackup.dll` | AMD64 PE, CLR flags `0x1` | Bundled default mods need the same architecture assessment |
| `0Harmony.dll` | I386 PE, CLR flags `0x1` | Managed code; an I386 header alone does not mean native x86 machine code |
| `MonoMod.Common.dll` | I386 PE, CLR flags `0x1` | Managed implementation with native/runtime detour responsibilities |

The intended launch is the bundled ARM64 `dotnet` host running the prepared
`StardewModdingAPI.dll`. Merely copying the official x64 apphost cannot work.
The [SMAPI project](https://github.com/Pathoschild/SMAPI/blob/4.5.2/src/SMAPI/SMAPI.csproj)
targets .NET 6 and x64. The inspected runtime configuration disables tiered
compilation; retain that setting when preparing the runtime configuration.

The payload's runtime configuration contains comments. Preparation must support
that JSON syntax rather than passing it blindly to Python's strict JSON parser.
Keep the complete .NET runtime layout: reflection, dynamic assembly loading,
serialization and generated methods are essential to modding. NativeAOT or
trimming are unsuitable shortcuts for this initial implementation.

### 2. There is useful upstream SMAPI preparation, but it needs adaptation

The pinned mainline port's preparation tool already accepts an SMAPI bundle,
optional external mod directory and optional patch assembly. It stages loader
files, prepares runtime/dependency metadata, aligns game assembly identities and
can recursively normalize mod assemblies. Its validation script includes a small
fixture that subscribes to a content event and injects WAV/OGG audio data.
These are reusable starting points, not results from our Frame environment.
[Preparation source](https://github.com/Producdevity/portmaster-stardew-valley-mainline/blob/986097ce2e586abb799c40dfd7386b288fa8ae1b/build/src/MainlineGameDataPatcher/Program.cs),
[fixture source](https://github.com/Producdevity/portmaster-stardew-valley-mainline/blob/986097ce2e586abb799c40dfd7386b288fa8ae1b/build/src/FixtureSmapiMod/ModEntry.cs).

Important differences for MonoFrame:

- Perform preparation on Windows in the converted copy, using our self-contained
  host tool. Normal users should receive a prepared package.
- Preserve our reference-type AudioCategory, SpriteBatch matrix, SDL coordinate
  and real Steam bridge changes. Do not revert to upstream offline Steam stubs or
  dummy audio replacements.
- Preserve SMAPI's loader/dependency requirements rather than assuming copying
  the game's `.deps.json` is sufficient for every SMAPI/Harmony combination.
- Audit assembly version alignment against the pinned supported game. Changing
  assembly identity cannot make incompatible game APIs compatible.
- Normalize only demonstrably managed, IL-only assemblies. The upstream check
  for a CLR header is not a sufficient guard against mixed-mode/native payloads.
- Audit SMAPI's `smapi-internal` tree explicitly. Top-level game normalization
  alone does not establish that every nested dependency is loadable on ARM64.

The upstream `StardewPatches.Mainline` assembly defines an entry-point attribute
and prints an initialization message; it contains no actual patches. Its smoke
tests load this marker via `MONOGAME_PATCH`. It is not an ARM64 Harmony
implementation. The inspected official SMAPI Linux payload does not contain a
`StardewPatches.dll` to compare with that marker. There is no basis here to claim
the marker disables SMAPI's own Harmony logic, or that importing it solves that
logic's compatibility requirements. Inspect any use before adopting it.
[Marker source](https://github.com/Producdevity/portmaster-stardew-valley-mainline/blob/986097ce2e586abb799c40dfd7386b288fa8ae1b/build/src/StardewPatches.Mainline/ModEntryPoint.cs).

### 3. Harmony is the first major validation gate

The official 4.5.2 payload contains a `2.2.2.0` version string in `0Harmony.dll`.
Its dependency source pins MonoMod.Common 22.3.5.1. SMAPI uses a custom Harmony
build and applies a `MiniMonoModHotfix` during normal initialization when
`FixHarmony` is enabled. That hotfix reflects into private Harmony and MonoMod
types, so replacing a DLL can break SMAPI even if public patch APIs remain
compatible. [Dependency versions](https://github.com/Pathoschild/SMAPI/blob/4.5.2/src/Directory.Packages.props),
[custom Harmony documentation](https://github.com/Pathoschild/SMAPI/blob/4.5.2/docs/technical/smapi.md),
[hotfix source](https://github.com/Pathoschild/SMAPI/blob/4.5.2/src/SMAPI/Framework/TemporaryHacks/MiniMonoModHotfix.cs).

The bundled MonoMod binary includes ARM-platform and .NET 6 detour type names.
This is evidence of ARM-related implementation, not proof of the exact Linux
ARM64/CoreCLR hook path. Do not label that stack universally unsupported based on
its age or the absence of a class named `ARM64`.

There is a stronger modern candidate: [Harmony 2.4](https://github.com/pardeike/Harmony/releases/tag/v2.4.0.0)
announces ARM64 support across operating systems. The current
[Pathoschild fork](https://github.com/Pathoschild/Harmony/tree/16078eb398cd9089bb1e752583097d9db04232d2)
identifies itself as 2.4.2 and uses the thin distribution with dependencies managed
separately. That supports evaluating a maintained ARM64 stack; it does not prove
SMAPI 4.5.2 is compatible with a drop-in replacement.

Recommended order:

1. Establish the unmodified pinned Harmony/MonoMod baseline with a real ARM64
   patching fixture on a separate ARM64 Linux runner when implementation begins.
2. If that fails, evaluate the pinned Pathoschild 2.4.2 fork and its exact
   dependency graph against .NET 6.0.32.
3. Adapt SMAPI's legacy internal hotfix only with source-level evidence and
   targeted tests. Do not blanket-disable it to hide initialization errors.
4. Consider HarmonyX only as a fallback after API/internal compatibility analysis;
   similar public names do not establish interchangeability.

Even a mod which never calls Harmony cannot automatically bypass this gate,
because SMAPI itself invokes Harmony during initialization.

### 4. Mod compatibility has several distinct layers

| Mod category | Initial assessment | Required evidence |
| --- | --- | --- |
| JSON/image/map content packs | Promising; assets are largely architecture-independent | Their framework mod loads, assets apply correctly, paths work on Linux |
| Pure managed event-driven mods | Promising | Loader/API compatibility, lifecycle events, config and save data work |
| Harmony prefix/postfix mods | Plausible after the detour gate | Actual method interception and correct unpatching on ARM64 |
| Transpiler/reverse-patch mods | Higher risk | Expected game IL still matches our prepared assemblies |
| Mods using Windows or x64 native libraries | Cannot be assumed portable | A legal matching ARM64 library and compatible ABI |
| Graphics/audio/native-hook mods | Higher risk | Required MonoGame members, interop, renderer and audio behavior |
| Large dependency-heavy overhauls | Later validation target | Every dependency, new locations/events, saves and acceptable performance |

Content Patcher is an appropriate early target because it provides a useful
content-pack workflow. Its packs may contain JSON and assets, but the framework
itself is a code mod and must pass compatibility testing.
[Content Patcher author guide](https://github.com/Pathoschild/StardewMods/blob/develop/ContentPatcher/docs/author-guide.md).

Suggested representative candidates are Content Patcher, Generic Mod Config Menu,
SpaceCore, Farm Type Manager and Stardew Valley Expanded. These are proposed
tests, not compatibility claims. Before testing, pin each selected release and
read its actual manifests; do not guess dependency versions from a familiar mod
name. Expanded should be a later workload, not the first proof of loader support.
[Expanded upstream](https://github.com/FlashShifter/StardewValleyExpanded).

Static inspection should collect mod IDs/versions, minimum game/API versions,
required dependencies, content-pack framework IDs, duplicate IDs, native imports,
target frameworks and MonoGame member references. Detect Linux-sensitive case
collisions, hardcoded path assumptions and platform-specific helper executables.
Do not mistake every `.dll` for native code. Reflection, runtime loading and
transpilers limit static certainty: a clean scan means no known blocker was
found, not that a mod is certified.

Distinguish an active dependency from an unused alternative bundled under
`runtimes/win-x64` or `runtimes/linux-x64`. A multi-platform mod may also ship a
valid ARM64 alternative. Resolve the selected platform's dependency graph before
blocking conversion; the mere presence of an unused Windows DLL is not a failure.

## Proposed converter design

### Source detection and mode selection

Separate immutable game identity checks from the presence of SMAPI. Today
`matches_stardew()` rejects `StardewModdingAPI.dll` outright; removing that check
alone would be incorrect. Identify the supported game first, then inspect
installed loader/mod state as a separate capability.

Recognize a clean game, a normal SMAPI installation with the supported underlying
game, and an unsupported/modified game separately. Retain the core assembly hash
guard. Assess known installer changes to configuration files explicitly; never
broaden acceptance to arbitrary modified game assemblies.

Offer explicit Vanilla and experimental SMAPI conversion modes. Existing mods
should select or recommend SMAPI once a validated recipe exists. A clean game
can opt into SMAPI and add mods later. Bundled ConsoleCommands/SaveBackup should
not accidentally trigger an implicit modded mode. Read manifests as structured
data, not with upstream shell regular expressions.

Do not execute source mods during conversion. Inspect their files and prepare
copies. Report known blockers by mod ID with actionable reasons. Do not quietly
drop an incompatible mod or fall back to vanilla after SMAPI initialization fails.

### Runtime provisioning and preparation

Use a separate versioned SMAPI supplement, referencing the existing pinned
MonoFrame base runtime. Its capability metadata should record game profile,
SMAPI source/release, Harmony variant/version, MonoMod dependencies, preparation
tool version, native requirements and validation status. Cache identity must
include those versions; do not mutate the published vanilla v1 archive.

Reuse verified downloads, file allowlists, checksums, atomic installation and
cache reuse. Prefer the official Linux payload as the starting point. If a
modified loader is necessary, publish a clearly identified source-built variant
with exact patches and build inputs. Do not present a custom build as an
unmodified official release or reuse upstream attestations for modified bytes.

Preparation should remove the incompatible native apphost, retain required
loader/toolkit files, prepare managed architecture metadata, preserve runtime
settings, resolve dependencies and copy the user's mods/config/assets into a
writable output folder. Every mutation remains confined to the converted copy.
Handle strong names, ReadyToRun and mixed-mode assemblies explicitly rather than
forcing all files to IL-only.

Proposed package shape:

```text
StardewValley-frame/
  launch.sh
  launch-vanilla.sh
  install-to-steam.sh
  Mods/                         # copied user mods and writable configurations
  .megcfbt/
    package.json
    mod-compatibility-report.json
  payload/
    launch.sh
    game/
      Stardew Valley.dll
      StardewModdingAPI.dll
      StardewModdingAPI.runtimeconfig.json
      smapi-internal/
      Content/
    runtime/                    # existing validated ARM64 base and supplement
```

Launch SMAPI with the bundled `dotnet` host and an absolute `SMAPI_MODS_PATH`.
The official source supports that variable and `SMAPI_NO_TERMINAL`; a normal
Steam launch should not require a terminal window stealing focus. Provide a
separate diagnostic launch mode and accessible SMAPI log file.
[Launch options](https://github.com/Pathoschild/SMAPI/blob/4.5.2/docs/technical/smapi.md).

Keep the working Steam registration and graphics environment handling. Preserve
Steam's launch context; do not reintroduce the manual test's forced application
environment IDs. Preserve the save-directory creation fix. Define the app-data
root consistently across normal and diagnostic launches so changing launch mode
does not make saves appear missing.

### Save handling and failure behavior

Keep vanilla and modded launch modes explicit. For validation, use a separate
save/config profile with copied saves. Back up before a mod/version change, never
overwrite original saves, and verify SaveBackup's output location is writable.
Some mods add data that vanilla cannot interpret; a vanilla launcher must not be
an automatic recovery path for that save.

Record the mod inventory used by a converted package. Surface startup failure
with the log location and failed dependency/mod where known. Adding/removing a
mod should not silently rewrite the runtime cache. Reusing an existing output
must preserve or deliberately migrate user configs, mod data and backups rather
than replacing them with default files.

## Proposed repository changes when implementation begins

| Area | Planned change |
| --- | --- |
| `monoframe/profiles.py` | Separate supported base-game identity from installed SMAPI/mod detection; retain hash guards |
| New SMAPI profile module | Pin loader/patching versions and supported capabilities independently of vanilla |
| New mod inspection module | Read manifests and managed/native dependency information; produce a compatibility report |
| `monoframe/runtime.py` and runtime index | Resolve and verify a versioned supplement using the existing shared cache infrastructure |
| `monoframe/backend.py` | Prepare SMAPI and copied mods, preserve runtime properties, select entry assembly and stable writable paths |
| Windows preparation tool | Safe managed normalization or an AnyCPU source-build route; source-level compatibility fixes where needed |
| `megcfbt/router.py` and GUI | Explicit mode selection, conversion eligibility, mod report and actionable blockers |
| Frame package metadata/launchers | Record the selected mode; expose mod/log folders and a separately invoked vanilla launcher |
| Tests and documentation | Prove patch behavior, frozen GUI provisioning, mod/save functionality and vanilla regressions |

Building the managed loader as AnyCPU from pinned source is an alternative to
normalizing official assembly headers. Compare both during the dependency audit.
It may produce a clearer maintained variant if Harmony integration needs source
changes anyway. It still does not port native code or prove mod compatibility.

## Licensing and distribution

SMAPI is under [LGPL v3](https://github.com/Pathoschild/SMAPI/blob/4.5.2/LICENSE.txt).
It is a plausible redistributable runtime dependency, subject to the license's
notice, source and replacement/relinking requirements. Prefer carrying the exact
corresponding source and build/patch instructions with a modified SDK. Audit all
bundled dependencies independently and retain their notices. This is an
engineering distribution plan, not a completed legal review of a future bundle.

Do not distribute Stardew game assemblies/assets or the proprietary Steam library
in a runtime release. User mods belong only in that user's converted output.
Do not automatically download or republish arbitrary mod collections or assume
one mod's license covers another. A mod with a separately licensed native SDK
would need its own provisioning rule, potentially the existing user-supplied SDK
pattern. No such proprietary prerequisite was identified for core SMAPI itself.

## Implementation phases and exit criteria

### Phase 1: dependency and architecture audit

Work locally and in ordinary CI; no Frame work is needed to start.

- Pin SMAPI/Harmony/MonoMod sources and hashes; establish the complete dependency
  and native-import graph, including nested loader files.
- Compare required game/MonoGame APIs with our rebuilt framework and current
  preparation rewrites.
- Inspect installer effects on Windows game config and mod assembly identities.
- Decide whether the original SMAPI 4.5.2 stack can be retained or requires a
  narrowly documented modern-Harmony variant.

Exit criterion: a reproducible candidate dependency set and explicit unresolved
ARM64 tests. No production detection eligibility change yet.

### Phase 2: ARM64 patching proof away from Frame

On a separate native Linux ARM64 CI runner, test .NET 6.0.32 with synthetic
assemblies first. If only emulated ARM64 CI is available, label those results as
emulated and retain native hardware validation as a later gate.

- Harmony prefix, postfix, transpiler, reverse patch, unpatch and patch chaining.
- Instance/static/generic methods, struct returns and exception behavior.
- SMAPI's internal hotfix and relevant assembly resolution.
- Demonstrated changes in return values/side effects, not just a startup banner.
- Repeat patches and save-related serialization after reflection/patching.

Exit criterion: demonstrable patch behavior on the target architecture, without
fake success responses or unexplained skipped fixes. If this fails, investigate
the modern maintainer fork before expanding the converter surface.

### Phase 3: isolated SMAPI package preparation

- Add a separate recipe and managed preparation support in a working branch.
- Test clean sources and SMAPI-installed sources without touching originals.
- Verify architecture classification, native rejection, dependency metadata,
  JIT settings, mod-path quoting and target-only packaging.
- Add meaningful cases for missing/duplicate dependencies, source mutations,
  corrupt archives, cache reuse, profile mismatch and writable save/config paths.
- Retain vanilla conversion and existing backend regression checks.

Exit criterion: a reproducible Windows-prepared package containing no x64
launcher or host SDK tools needed on Frame, with source integrity verified.

### Phase 4: loader and representative mods

On the separate ARM64 test environment, use legally supplied private game data;
never place retail assets or real saves into public CI artifacts.

| Test | Required observation |
| --- | --- |
| SMAPI plus its two default mods | Loader initializes; both defaults load; backup/log paths are writable |
| Small owned fixture | GameLaunched, asset, input and save events actually run |
| Content Patcher plus a tiny owned pack | A visible texture/data change applies and survives restart |
| Owned Harmony fixture | Prefix/postfix/transpiler modify real game behavior and can unpatch |
| Pinned config-menu mod | Menu input and configuration persistence work |
| Audio fixture | WAV, decoded OGG and streamed OGG are audible and controllable |
| Mod serialization fixture | Added mod data survives sleep, exit, load and subsequent save |

Only after those pass, evaluate a pinned SpaceCore/Farm Type Manager/Expanded
dependency set. Record enabled mods and patch failures, inspect new locations and
events, and compare startup time, frame time, memory and save size with vanilla.

Exit criterion: the selected mod configurations have functional evidence beyond
title-screen startup. Unsupported native dependencies remain clearly reported.

### Phase 5: frozen Windows GUI acceptance

- Drop a clean game with SMAPI explicitly selected; repeat with a supported
  SMAPI-installed source and its copied `Mods` folder.
- Convert with an empty cache and no local .NET SDK or runtime override.
- Verify automatic selection, download progress, checksums, cache reuse,
  actionable failure messages and complete ZIP contents.
- Verify originals remain unchanged, and vanilla conversion still works.
- Check reconversion behavior against user-edited output configurations.

Exit criterion: a normal end-user workflow that creates a self-contained package
without requiring mod reinstallation or manual runtime compilation.

### Phase 6: later Frame acceptance, outside this research task

After the earlier gates pass, arrange a separate Frame test session. Launch
through Steam and verify pointer/controller input, text entry, mod menus, audio,
gameplay, sleep/save, exit/relaunch/load and backups. Test an existing copied save
as well as a new modded save. Do not change Frametop to mask converter failures.

Exit criterion: label only the exact SMAPI version and tested mod configurations
as verified. Multiplayer, large overhauls and full-game compatibility remain
separate claims requiring their own tests.

## Scope and decisions

Recommended first delivery: experimental SMAPI loader support, a reliable mod
folder and logs, the two bundled defaults, an owned fixture and a small Content
Patcher configuration. Broader Harmony-dependent support follows the patching
gate; general mod management, automatic Nexus downloads, Android SMAPI and
support for every Stardew version are outside that first delivery.

The next useful work is Phase 1 plus the small synthetic ARM64 Harmony proof.
Avoid spending effort on a polished GUI or publishing a runtime until the loader
and patching stack have passed those gates. No trustworthy calendar estimate is
available before that compatibility result; packaging is comparatively routine,
while framework/patching differences could require substantial source work.

Outstanding questions are whether the bundled legacy detour path works on our
exact .NET runtime, which hotfix changes a modern Harmony variant needs, which
specific mod versions should form the initial test set, and whether any game
method rewrites break their transpilers. This draft deliberately does not answer
those questions with unperformed hardware tests.
