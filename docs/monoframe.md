# MonoFrame: audited managed-game profiles

MonoFrame includes separate Stardew Valley MonoGame/.NET 6 and
[Celeste XNA/FNA/.NET 8](backends/celesteframe.md) profiles. Each retains its own
source hashes, runtime SDK, dependencies, launcher and Steam capability contract.
Celeste requires the owner-supplied FMOD 2.03.15 Linux SDK. Legacy CelesteFrame
imports and packages remain supported; new conversions report MonoFrame.

Windows uses the existing self-contained host preparers. Linux ARM64 uses its
native SDK runtime; Linux x64 uses a native `dotnet` on PATH with the preparer's
required .NET runtime. Missing/wrong-architecture host tools fail with setup
guidance rather than trying to execute the ARM64 game runtime on a PC.

## Stardew Valley

MonoFrame prepares the unmodified Steam Windows installation of Stardew Valley
1.6.15.24356 for a native Linux ARM64 .NET 6.0.32 runtime. Detection checks the
game, GameData and MonoGame assembly hashes before applying the compatibility
profile. Modified installations, SMAPI and other game versions are not covered.

SMAPI possibilities and a proposed implementation plan are recorded in
[SMAPI ARM64 research](smapi-arm64-research-and-plan.md). Implementation is deferred.

Preparation runs against a copied installation. The SDK includes a self-contained
Windows x64 preparation tool, so conversion does not require an installed .NET SDK
or compilation on Windows. Frame packages contain the Linux runtime and supporting
libraries; host preparation tools are excluded.

The runtime is based on the [mainline port preparation tool](https://github.com/Producdevity/portmaster-stardew-valley-mainline/tree/986097ce2e586abb799c40dfd7386b288fa8ae1b)
and its [MonoGame fork](https://github.com/Producdevity/MonoGame/tree/3874df98675039d368e77dca50d9a00ac970537e).
The framework patch preserves Stardew's reference-type AudioCategory ABI,
composes SpriteBatch's global and explicit matrices, and restores SDL mouse
coordinate updates. The Steam bridge forwards supported legacy calls to the real
Frame-side Steam API. It does not emulate successful Steam initialization or
bundle the proprietary Steam client library.

## Validation and remaining work

On Steam Frame, the native title menu renders. User testing has confirmed
character creation, keyboard name entry, movement, tools and sleeping to save.
Pointer and gamepad input, saves and loading have subsequently been confirmed
when launching the Windows-generated package through Steam. Pointer behavior in
the earlier Konsole test was inconsistent across launches. These tests do not
establish full gameplay compatibility, multiplayer or SMAPI support.

The initial manual test launcher selected an XDG configuration directory that did
not exist. .NET returned an empty application-data directory, causing relative
save paths. Generated launchers now create the configuration directory before
starting the runtime. Both preserved test saves are discovered by the initialized
game's load-menu code after correcting the directory. Entering gameplay from a
saved game has subsequently been confirmed by user testing through Steam.

A Python-hosted Windows conversion has completed, with ZIP integrity and unchanged
original assembly hashes verified. The software SDK is published as a versioned
[runtime release](https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/releases/tag/runtime-monoframe-stardew-1615-arm64-v1)
and registered for automatic checksum-verified download and cache reuse. The
frozen Windows GUI passed a clean-cache conversion using its drop handler and
Convert button, with automatic download progress and no runtime override.

The runtime matches the game's .NET 6.0.32 version. [.NET 6 is out of support](https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core);
migrating the game to a supported .NET release needs separate compatibility work.

Test packages should be installed using `install-to-steam.sh` and launched from
their Steam shortcut when checking Steam Input. The earlier Konsole launcher
forced Steam application environment IDs and is not a controller acceptance test.

The software SDK includes third-party license notices and source provenance. Game
assets, saves and Steam libraries must stay out of public runtime artifacts.
# Steam library linking candidate

The audited vanilla Stardew Steam profile can use the v0.1.1.0 shared guided
installer. The original must be installed through Steam on Frame. Original files,
saves and mods are never changed by linking. Steam online features remain
unverified. See [setup and restoration](steam-library-integration.md).
