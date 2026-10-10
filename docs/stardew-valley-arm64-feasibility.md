# Stardew Valley native ARM64 feasibility

Research date: 2026-10-10. Status: promising candidate; not implemented or tested on Steam Frame in this investigation.

## Local installation

Read-only inspection of `C:\Program Files (x86)\Steam\steamapps\common\Stardew Valley` found:

| Component | Observed version |
| --- | --- |
| Stardew Valley assembly | 1.6.15.24356 |
| Runtime configuration | net6.0, Microsoft.NETCore.App 6.0.32 |
| MonoGame DesktopGL dependency | 3.8.0.1641 |
| SkiaSharp dependency | 2.80.3-preview.93 |
| Steamworks.NET dependency | 20.0.0.0 |
| GalaxyCSharp dependency | 3.133.7.0 |

The installation includes Windows native .NET components and native graphics/audio/platform libraries. Copying the directory and substituting an ARM64 executable alone would not produce a native port. Its managed assemblies make a runtime replacement approach plausible, subject to native interop and framework compatibility. No game files were modified or executed.

## Strongest available route: mainline MonoGame port

[Producdevity's mainline PortMaster project](https://github.com/Producdevity/portmaster-stardew-valley-mainline) explicitly targets the regular Windows Steam installation, rather than the compatibility branch. Source inspected at revision `986097ce2e586abb799c40dfd7386b288fa8ae1b`.

Its documented approach supplies ARM64 .NET 6.0.32, a patched MonoGame DesktopGL framework, native libraries and an assembly preparation tool. The project remains experimental. This is evidence for feasibility, not evidence of compatibility with our Frame or exact installed build.

The [preparation tool](https://github.com/Producdevity/portmaster-stardew-valley-mainline/blob/986097ce2e586abb799c40dfd7386b288fa8ae1b/build/src/MainlineGameDataPatcher/Program.cs) removes conflicting Windows runtime components, rewrites runtime/dependency configuration, normalizes managed assemblies and changes game methods. Changes include content paths, fullscreen/display behavior, input and audio category handling. These are substantial game-specific adaptations: do not apply them universally to every MonoGame game. Some may be unnecessary on Frame, which has a different graphics and input environment.

The build supplies ARM64 SkiaSharp 2.80.3, while our source declares a preview version. ABI compatibility must be tested. The patched MonoGame fork must be pinned and audited separately before a reproducible runtime recipe can be published.

### Steam is a separate compatibility question

The inspected [Steam shim](https://github.com/Producdevity/portmaster-stardew-valley-mainline/blob/986097ce2e586abb799c40dfd7386b288fa8ae1b/build/src/native/steam_api64_stub.c) returns false from Steam initialization and supplies inert callbacks. It does not establish working Steam integration, achievements or online multiplayer.

For Frame, investigate using its installed ARM64 Steam library with the game's managed Steamworks wrapper, verifying the required API symbols and versions. Preserve the established Frame graphics environment around initialization. Do not substitute a successful initialization response. Galaxy/GOG integration also needs an explicit supported path; presence of Galaxy assemblies in the Steam install does not prove it is required for offline gameplay or that ARM64 GOG support exists.

## Alternative: compatibility branch

The [official compatibility guide](https://www.stardewvalley.net/compatibility/) documents switching the Steam/GOG installation to the compatibility branch and warns about differing mod compatibility. The [existing PortMaster Stardew port](https://portmaster.games/detail.html?name=stardewvalley) uses that branch. This provides a fallback Mono-based approach, but would require a different user-supplied installation. Prefer the mainline approach for our untouched-install GUI workflow if Frame validation succeeds.

## Redistribution and provisioning

The inspected mainline repository is [MIT licensed](https://github.com/Producdevity/portmaster-stardew-valley-mainline/blob/986097ce2e586abb799c40dfd7386b288fa8ae1b/LICENSE). Its packaged MonoGame notice uses Ms-PL. Those licenses provide a basis for reuse with their required notices; they do not license retail game data or waive separate dependency obligations. Audit the exact patched fork and every bundled native dependency before publication. Publish software-only runtimes and patch tools, never retail assemblies/assets or users' saves. Use the established Frame-side Steam dependency mechanism unless a particular library's redistribution is demonstrably permitted.

[Microsoft lists .NET 6 as out of support](https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core). Establish compatibility against the matching runtime first, then assess the final .NET 6 patch and a supported major version separately. Do not silently force a major runtime upgrade and assume compatibility.

Our existing verified-download infrastructure can supply checksummed, versioned software bundles and cache them. A .NET framework runtime has a nested directory layout, whereas the current native runtime archive format is flat. Integration needs a safe nested bundle representation or reconstruction scheme, with exact member allowlists, path/symlink rejection and atomic installation. Validate native ELF files as ARM64 and managed assemblies as managed code; do not reject every managed PE as a Windows-only executable.

Run preparation against the output copy during Windows conversion. Users should receive a prepared ZIP and should not need to compile or run a patcher on Frame. The converter will need a host-compatible preparation tool, recipe identity, supported assembly/version checks and failure without modifying the source. Reuse general .NET/MonoGame detection and provisioning where appropriate, but keep Stardew-specific assembly transformations in a narrowly guarded compatibility profile.

## Suggested implementation and acceptance sequence

1. Pin and audit the MonoGame fork and dependencies; reproduce a software-only ARM64 runtime. Start with vanilla Stardew 1.6.15.
2. Prepare a separate copy of the installation; test first with Frame's native graphics stack rather than assuming the PortMaster GL4ES wrapper is necessary.
3. Verify title screen, new game, music/sound, text entry, gamepad navigation, gameplay, sleeping to save, process restart and save loading. Measure frame pacing and check window/Frametop behavior.
4. Verify real Steam integration separately. Test multiplayer only after local gameplay works; label offline limitations explicitly if real integration remains unavailable.
5. Integrate automatic detection, checksum-pinned downloads, cache reuse and packaging. Test the frozen Windows GUI with a clean cache and untouched source installation.
6. Add SMAPI as a separate optional capability after vanilla acceptance. The upstream project documents SMAPI 4.5.2 support, but mods with Windows/x64 native dependencies or framework-specific Harmony patches require their own validation.

No Frame startup, gameplay, saves, performance, Steam integration or SMAPI compatibility was verified during this research. No converter eligibility was changed and no runtime was published.
