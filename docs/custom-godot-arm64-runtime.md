# Custom Godot ARM64 runtimes

Some Windows Godot games are not built with an official stable engine. Brotato
1.1.14.6 is the first concrete test case:

- PCK header: Godot 3.7.0
- executable: `3.7.dev.custom_build`
- embedded engine build hash: `74e86be5492080f6a4e903a973f2f4f7e9471af2`
- built-in GodotSteam: 3.31

For these games, substituting a stock stable Godot runtime is unsafe. tovakai
therefore requires an explicit matching Linux ARM64 runtime bundle.

## First runtime candidate

The initial Brotato experiment deliberately starts from the public Godot
3.7-dev1 baseline, commit:

`a117d512b00f1646db174e703e7e888519b64608`

and compiles it for native Linux ARM64 with GodotSteam 3.31. This is a
compatibility candidate, not a claim that it exactly reproduces Brotato's
private/custom engine tree.

The builder is:

`scripts/build-custom-godot-arm64.sh`

## Why native ARM64 first

Godot 3.x's X11 build logic supports ARM64 output on an ARM64 host, but its
cross-compilation path is not a general x86-to-ARM solution. The first recipe
therefore builds natively on Linux ARM64 so that engine compatibility can be
tested independently from a cross-toolchain.

Once the runtime is proven, a reproducible cross-build/container can be added
as a separate layer.

## Steamworks SDK

GodotSteam requires the Steamworks SDK headers and runtime library. tovakai
does not download, vendor, or redistribute Valve's SDK.

The user supplies a Steamworks SDK directory when invoking the builder. Linux
ARM64 requires a Steamworks SDK containing:

`sdk/redistributable_bin/linuxarm64/libsteam_api.so`

which means SDK 1.63 or newer.

The script copies the ARM64 Steam API library only into its disposable build
workspace and resulting local runtime bundle.

## GodotSteam source

By default the builder attempts to fetch GodotSteam v3.31 from the upstream
Codeberg repository. If that is unavailable, provide a local source checkout:

```bash
scripts/build-custom-godot-arm64.sh \
  --steamworks-sdk /path/to/steamworks_sdk \
  --godotsteam-src /path/to/godotsteam-3.31
```

The source directory must contain the normal Godot module files such as
`SCsub` and `godotsteam.cpp`.

## Build prerequisites

The current recipe expects a native ARM64 Linux environment with:

- Git
- Python 3
- SCons
- GCC/G++
- pkg-config
- Linux/X11 development packages for X11, Xcursor, Xinerama, Xext, XRandR,
  XRender, Xi, and OpenGL

The script checks these before starting a long engine build.

## Resulting runtime bundle

A successful build produces a directory containing at least:

```text
godot.arm64
libsteam_api.so
runtime.json
```

`godot.arm64` and any sibling `.so` files are copied into the converted game
package. The generated launcher prepends the package root to
`LD_LIBRARY_PATH`, allowing modules such as GodotSteam to resolve
`libsteam_api.so`.

## Using it in tovakai

Custom Godot detections expose the runtime selector instead of permanently
disabling conversion.

Select the generated runtime directory. tovakai validates `godot.arm64` as an
AArch64 ELF binary, then permits the conversion despite the source game's
otherwise-unknown compatibility status.

The first useful result is not necessarily a successful game launch. An engine
error from the candidate runtime is actionable evidence about what differs
between the public 3.7-dev1 baseline and the game's custom engine build.
