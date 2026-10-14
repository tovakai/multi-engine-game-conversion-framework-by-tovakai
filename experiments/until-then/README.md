# Until Then ARM64 research

This is an isolated experimental compatibility recipe, not an approved release
backend. It targets Steam build 23785927, Godot 4.1.4 and the exact source hashes
in source-profile.json. No original game files or Steam configuration are patched.
Game content and original DLLs are provided locally by the user and are never
committed or redistributed.

## Behavior replacements

Independent prototypes implement the required JSON Patch, camera interpolation
and seeded NPC coloring behavior. Native C++ replacements register JsonUtils,
InterpolatedCamera3D and Colorizer. The original native NpcBasic class is not
implemented: text scenes do not instantiate it; any later requirement must be
resolved before support is advertised.

Run the Windows oracle with a user-owned installation:

    python experiments/until-then/verify_prototypes.py "<Steam game directory>"

The runner copies only the engine and two DLLs into a fresh ignored workspace;
it never loads the game pack or touches saves. Source DLL hashes must match.
Current results: 255 exact JSON diff/round-trip comparisons, seven malformed-patch
checks, 36 camera checks (idle/physics, perspective/orthogonal, disabled state),
and 2,560 color comparisons including global RNG state. Linux ARM64 native
replacements pass the same comparisons against these verified prototypes.
These are compatibility checks, not gameplay acceptance.

## Native sources and SDK

Research builders operate only under ~/.cache/megcfbt/research/until-then:

- Godot 4.1.4: fe0e8e55752b0c2e64997025717b491703e0f8ad.
- Godot C++ bindings: 4b0ee133274d67687b6003b8d5fdaf7b79cf4921.
- JSON library: nlohmann JSON 3.10.4 (MIT); downloaded header checksum recorded.
- InkCPP developer fork: fe1b761f47ecd1c04d2dc366d3d817957f4eb608.
- Threen 1.0.1: 4ee5588cb8ee203048ab66c89377e29e78ab82a3.
- Preserved FMOD-for-Godot fork: 2046fb9ef051c4e3936f363d01ba5784052a787f.
- GodotSteam GDExtension: 84ece1a226b8fd099333940e7a3b8367efb59370,
  using Proton SDK 1.58 headers from 5b89db940e0ebe3a137a6009a3589232fe084c09.
  Calls use the Frame's genuine native Steam API; no fake ownership or Steamworks
  success is supplied. Initialization does not establish achievement support.
- Owner-supplied FMOD Studio API 2.02.35 Linux SDK, SHA256
  855381248a85b6457b96090c9f9c0b070a51f10be6bf07b4a6456a12f8aff807.
  Original Windows DLLs report 2.02.11. Bank/audio compatibility requires testing.

The maintained GodotSteam source is on Codeberg. The FMOD fork discovered on the
developer's account is a different, legacy binding system; it is not substituted
for the actual integration identified inside the original library.

Narrow source adaptations cover Godot 4.0-to-4.1 initialization ABI, exported enum
visibility and modern compiler header requirements. Two invalid unused Embree
print helpers were corrected for GCC 15. A separate explicit resource-overlay
hook loads converted-package descriptors before settings/GDExtensions. Without
its environment variable, main-pack loading follows normal Godot behavior.
Apply the hook between builds, never while an existing compile is running.

resource_overlay.py creates a small PCK containing six Linux descriptors and a
hash-gated thumbnail-script adaptation for a custom five-argument loader call;
the original main PCK stays byte-identical. Runtime libraries are copied into the
converted package, and experimental test saves use a separate custom directory.

## Frame startup evidence (2026-10-14)

The private SD-card package loads all six extensions in a matching native ARM64
Godot runtime. FMOD runtime initialization and genuine Steam initialization pass.
The old C++ SDK?s GNU-unique inline registration symbols must not be shared
between extension libraries. Research builds hide static SDK exports and use
-fno-gnu-unique with local symbol binding; Threen also registers its UI bindings
explicitly. This fixes missing Control, Node3D and FileAccess callbacks. The focused story probe opens the original first Ink binary and creates a
valid runner. FMOD is released before extension unload, and the shutdown probe
now exits with code 0. Headless-only font warnings remain visible in logs. The experimental shortcut and all four artwork images
were registered through the running Steam client, without a restart.

The main game PCK remains SHA-256 identical to the source profile. The overlay
adapts one thumbnail-loading call to stock Godot?s four-argument signature.
Original-engine probes establish matching existing-resource results, but the
custom fifth parameter?s scheduling semantics remain unverified.

## User-confirmed device checks

On Steam Frame, the experimental non-Steam entry launches visibly, plays audio,
accepts controller input and works through its menus. After the binding fix,
the initial morning scene and transition toward school are playable. Saving
works. The running executable was verified through /proc as a native Linux
AArch64 ELF, not FEX or Proton. Saved-game reload and normal shutdown with the
latest FMOD fix still require confirmation.

## Remaining gates

Broader story/Ink serialization coverage, audio throughout gameplay, camera
transitions, NPC appearance, saved-game reload and normal exit with the latest
cleanup fix remain required. The successful opening scenes are not full-game
compatibility acceptance. No GUI support, original-entry linking,
asset deduplication, playtime or achievement support is authorized by these
prototype/build results. Do not publish v0.1.1.0 or merge this research into its
release PR on that basis.

Third-party sources retain their own licenses. FMOD SDK and user-owned game data
are not included in this repository; obtain them independently. Preserve runtime
license notices when making any test package. Builds are research inputs and
must not be relabeled as final release artifacts.
