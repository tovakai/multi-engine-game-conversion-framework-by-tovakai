# Celeste native ARM64 prototype

Release target: 0.1.0.2. The converter profile is implemented in `celesteframe/`;
this directory contains its source preparation tools and runtime SDK recipe.

The audited input is the owner's vanilla Steam **Windows XNA Celeste 1.4.0.0**
installation. `Celeste.exe` SHA-256:
`1a1e117add967c0f26ad470a49d4ff442435209265bf1fdda623821d797e80b5`.
The preparer rejects other executables and writes a separate copy.

The prototype retargets the XNA assembly references to FNA 23.10, removes the
managed executable's 32-bit restriction, and adapts FMOD 1.10 calls to the
owner-supplied FMOD Studio API 2.03.15 Linux ARM64 libraries. The FMOD SDK must be
obtained separately; it is not part of a public runtime bundle.

Steam initialization, stats and callbacks use the actual installed ARM64 Steam
client. The Steam adapter initializes real client interfaces used by Celeste,
without requesting legacy music and matchmaking APIs removed from the Frame
library. It does not replace Steam initialization or achievements with stubs.
The Linux Steamworks.NET wrapper is built from official tag 20.0.0 with Linux
callback packing and AnyCPU managed code.

Pinned upstream sources:

| Component | Commit |
| --- | --- |
| FNA 23.10 | `d0a0892f17dd8bebd36319294509cdca8ae8c810` |
| FNA3D | `95ee2be9933a1e3f6007b1483eb6533cec1eaf10` |
| FAudio | `a26a9a8ebab96a2fa99ee6aa01af1c76f71725fb` |
| Theorafile | `9cddd3fb0d4ebc0b2b253e8c976ae6b95e8aec5d` |
| Steamworks.NET 20.0.0 | `4dafa26fbd032c83c1970298cc93d66f47edfb59` |

## Hardware findings, 2026-10-12

The copied game reached `GAME DISPLAYED` and `DONE LOADING` on Steam Frame with
.NET 8.0.31 ARM64, FNA3D Vulkan and Turnip Adreno 750. Process mappings show
ARM64 .NET, FNA3D, FMOD core/studio, and the actual Valve ARM64 Steam API.
The owner confirmed menu, music and gameplay with an external 8BitDo gamepad,
then confirmed saved-game loading and movement, jumping, climbing, dashing and
audio with the Frame controllers after relaunching with them as primary.

An SSH launch detected controllers but did not route their input correctly.
The Steam shortcut test provides an appropriate Steam Input and Gamescope
context. When multiple controllers are connected, select the desired primary
controller through Steam's controller order settings. This profile preserves
Celeste's existing controller selection behavior.

Windows CLI inspection and conversion passed with the officially built Linux
Steamworks.NET wrapper. The ordinary Frame ZIP installer registered `Celeste`
and applied all four artwork slots. Integrated package gameplay and public
runtime distribution checks are still pending.

## Build the open runtime SDK

On a native ARM64 Frame with SDL2 development files, .NET SDK 8 (including the
8.0.31 runtime) and the framework checkout, run:

```sh
python3 experiments/celeste/build_sdk.py --work /path/to/new/build-directory \
  --dotnet-sdk /path/to/dotnet-sdk --fmod-sdk /path/to/fmodstudioapi20315linux.tar.gz
```

The recipe checks out pinned FNA and Steamworks.NET sources, builds graphics,
audio and preparation tools, and assembles licenses, source and provenance.
FMOD is used only to compile the ABI adapter. The output archive excludes
proprietary FMOD and Steam client libraries and all game files. Conversion adds
the owner's checksum-verified FMOD ARM64 libraries to the private game package.

No game data or proprietary native libraries belong in this repository or a
public converter release. Owner-input archives and hardware logs remain under
the ignored `build/` directory.
