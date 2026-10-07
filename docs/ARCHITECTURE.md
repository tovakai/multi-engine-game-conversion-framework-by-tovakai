# Architecture

**Multi-Engine Game Conversion Framework by Tovakai** is a staged merger, not a rewrite.

The public application layer owns engine detection, user-facing inspection, output selection, progress reporting, CLI behavior, and the desktop GUI. Engine-specific conversion remains behind adapters backed by the proven RenFrame and RPGMFrame implementations.

## Current shape

~~~text
Multi-Engine Game Conversion Framework by Tovakai
                     |
          unified detector / builder
              /             \
         Ren'Py             RPGMFrame family
           |                 /      |       \
    RenFrame sdkarm       mkxp-z   NW.js   Godot
       backend           XP/VX/Ace MV/MZ   native ARM64
~~~

This separation is deliberate. Each backend contains compatibility knowledge that was learned through real games and hardware testing. The first unified releases preserve that behavior intact while common infrastructure moves upward only when it is genuinely shared.

## Rules for future refactoring

1. A backend-specific compatibility fix stays in its backend unless another engine demonstrably needs the same abstraction.
2. The unified layer chooses engines and normalizes results. It should not silently duplicate engine internals.
3. Existing hardware discoveries should become synthetic regression tests before code is moved.
4. Runtime downloads remain checksum-verified and architecture-validated.
5. Source games should not be modified by the unified application. Ren'Py directory input is copied to a temporary working tree before the inherited converter runs.
6. Ambiguous engine detection fails closed rather than guessing.

## Proven conversion routes

The inherited backends have been exercised on Steam Frame hardware:

- Ren'Py through ARM sdkarm replacement on tested modern titles, plus selected legacy compatibility profiles.
- RPG Maker MV/MZ through Linux ARM64 NW.js.
- RPG Maker XP through Linux ARM64 mkxp-z, including legacy mkxp migration and fractional-scale pointer handling.
- Godot 4.x through an exact matching official Linux ARM64 runtime.

Hardware success is evidence for a conversion route, not a universal compatibility guarantee. Native plugins, unusual codecs, platform integrations, and game-specific assumptions can still require targeted work.

## Provenance

The bootstrap imported code from these repository states:

- RenFrame compatibility/runtime branch: a571e75d4b5b21d8494c2a1181d367af631eb4d3
- RenFrame mod-library tooling branch: 59e09b263067b4782118c4d50ed4fab993a0d774
- RPGMFrame main: ec54754e5832f3665df9107b75020c65b7b6c735

The old repositories remain historical records. Cross-engine application work belongs here.
