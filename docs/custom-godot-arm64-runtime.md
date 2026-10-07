# Custom Godot ARM64 runtimes

Some Windows Godot games are not built with an official stable engine. Brotato
1.1.14.6 is the first concrete test case:

- PCK header: Godot 3.7.0
- executable: `3.7.dev.custom_build`
- embedded engine build hash observed at runtime:
  `74e86be5492080f6a4e903a973f2f4f7e9471af2`
- built-in GodotSteam: 3.31

The original private/custom Godot source is not available, so tovakai does not
pretend to reproduce it byte-for-byte. Instead it builds a compatible native
runtime whose game-facing API matches what the PCK expects.

## Proven Steam Frame compatibility recipe

The first working recipe is:

1. Godot 3.7-dev1, upstream commit
   `a117d512b00f1646db174e703e7e888519b64608`
2. upstream Godot 3.x CanvasItem/CanvasItemMaterial cast fix from PR #123099
3. a release-safe missing-Variant-method guard matching the successful diagnostic build
4. GodotSteam 3.30, commit
   `f73d138b56fe971a940dd0498e8b9d0fc8fdcffd`
5. Steamworks 1.62 C++ header surface
6. the Steam Frame's installed native ARM64 `libsteam_api.so`
7. Zink/Turnip forced for the custom Godot 3.x launcher

Brotato's Windows executable reports GodotSteam 3.31, but 3.31 uses Steam's
newer flat API. The Frame ARM64 Steam library tested here exposes the classic
`SteamInternal_*` interface path instead. GodotSteam 3.30 preserves the
game-facing Godot API needed by Brotato while using that classic Steam API.

This compatibility substitution has been hardware-tested for roughly 30
minutes of actual Brotato gameplay on Steam Frame, not merely to first boot.

## Automatic conversion path

For a Godot 3.7.0 custom/development export with the built-in GodotSteam marker,
tovakai now offers the recipe automatically on a compatible Linux ARM64 host.

The backend:

- finds the native Frame Steam API at
  `/opt/steamvr/bin/linuxarm64/libsteam_api.so`
- fetches the pinned Godot and GodotSteam sources
- fetches Valve Proton's vendored Steamworks 1.62 header tree
- normalizes Proton's named-union/generated-header changes back to the C++ SDK
  semantics GodotSteam 3.30 expects
- applies the upstream CanvasItem fix and the release-safe Variant guard
- builds the ARM64 Godot runtime
- launches this custom Godot 3.x recipe through Zink/Turnip, matching the hardware-tested path
- caches the finished runtime
- bundles `godot.arm64`, `libsteam_api.so`, and runtime provenance
- copies a game's `steam_data.json` beside the runtime when the original
  export provides one

The source PCK and game data remain untouched.

## Build host

The automatic recipe currently requires native Linux ARM64.

tovakai first tries an existing distrobox named:

`tovakai-godot-build`

If that container has the normal compiler/SCons/X11 development toolchain, it
is used automatically. Otherwise the same dependencies may be installed on the
native host.

The required build commands are:

- Git
- Python 3
- SCons
- GCC/G++
- pkg-config

The required pkg-config development packages are X11, Xcursor, Xinerama, Xext,
XRandR, XRender, Xi, and OpenGL.

A manual custom-runtime override remains available when automatic building is
not possible.

## Steamworks provenance

tovakai does not vendor or redistribute Valve's Steamworks SDK binaries.

The ARM64 Steam API shared library is taken from the user's installed Steam
Frame runtime. The build recipe obtains the 1.62 compatibility headers from
ValveSoftware/Proton at a pinned revision and patches only the compatibility
transformations Proton applies to those headers.

The path can be overridden with:

`TOVAKAI_STEAM_API_ARM64=/path/to/libsteam_api.so`

The distrobox name can be overridden with:

`TOVAKAI_GODOT_DISTROBOX=my-build-box`

## Cache and workspace

Automatic runtime output is cached under a hidden runtime cache beside the
selected conversion output unless `RPGMFRAME_CACHE_DIR` is configured.

The large source/build workspace is also placed beside the conversion output so
a Steam Frame with a small internal home partition can keep the multi-gigabyte
engine build on the same storage volume as the converted game.

## Standalone builder

The developer helper now invokes the same code path as the application:

```bash
scripts/build-custom-godot-arm64.sh
```

Optional overrides:

```bash
scripts/build-custom-godot-arm64.sh \
  --work-dir /path/with/plenty/of/space \
  --steam-api /path/to/libsteam_api.so \
  --distrobox tovakai-godot-build \
  --output /path/to/runtime-bundle
```

Keeping the standalone helper and GUI/CLI on one implementation is intentional:
the experimental recipe should not quietly diverge from the runtime the
application actually uses.
