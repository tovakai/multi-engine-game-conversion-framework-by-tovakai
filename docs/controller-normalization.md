# Controller normalization and right-stick pointer support

Experimental implementation recorded 2026-10-15. The converter can bundle an
opt-in Steam Input profile for Ren'Py and RPG Maker. Steam on the Frame parses
the profile for its paired controllers and accepts per-shortcut selection.
The user confirmed movement, R3 pointer, click/drag and switching back on the
Frame controllers and an 8BitDo Ultimate 2 in the diagnostic. Isolated Ren'Py 8.3.7 and RPG Maker MV 1.6.1 games subsequently passed their
control checks on 2026-10-16: Ren'Py menu/choice navigation, A/B, pointer clicks
and slider dragging; MV navigation, movement, actions and pointer switching.
The MV dashboard and 8BitDo disconnect/reconnect checks also passed with no
stuck movement or mouse button. MZ, mkxp-z and EasyRPG remain unverified.
This is separate from the deferred low-spec optimization research.

## Using the experimental profile

The unified conversion GUI has an experimental controller-profile checkbox for
Ren'Py and RPG Maker. The equivalent build option is `--controller-profile`.
It bundles setup files; conversion does not select a layout in Steam.
To add the files to an existing converted output, run:

```sh
python -m megcfbt controller-profile /path/to/converted-build
```

Optional `--sensitivity 125 --deadzone 9000` tunes the pointer profile when
preparing it. Defaults are 100 and 8000. Existing profile assets are never
silently overwritten; use a fresh output to regenerate them. For extracted
Frame ZIPs, select the converted payload directory containing the game's
launcher rather than the package wrapper. Recreate an existing ZIP after
adding assets if distributing it.

On the Frame, with Steam running and controllers awake, open a terminal in the
converted game directory:

```sh
./setup-controller-profile.sh --list
./setup-controller-profile.sh --appid SHORTCUT_ID
./setup-controller-profile.sh --appid SHORTCUT_ID --apply
# Required by the Frame client tested on 2026-10-15:
./setup-controller-profile.sh --appid SHORTCUT_ID --frame-routing --apply
# To return to the previous selection:
./setup-controller-profile.sh --appid SHORTCUT_ID --frame-routing --restore
./setup-controller-profile.sh --appid SHORTCUT_ID --restore
```

The command without `--apply` only publishes a uniquely named template and
asks Steam to parse it. `--apply` saves the previous per-game layout URL before
selecting the profile. `--restore` refuses to replace a newer user selection.
Keep `.megcfbt/controllers/selection-*.json` until restoring. Backup creation
is exclusive and flushed before changing Steam; restore also checks the saved
controller type at that index. If controller indices change after reconnecting,
check `--list` before restoring. Unsupported Steam selection types are rejected. Enable Steam
Input for the entry first. The entry may have been added manually or by another
tool; our install script is not required. Launch through that Steam entry.
Direct desktop launches retain their existing input behavior.

The default controller type is `controller_steamframe_pair`. Additional
experimental templates can be selected using `--controller-type` for
`controller_generic`, `controller_xboxone`, `controller_xbox360`,
`controller_neptune`, `controller_ps4`, `controller_ps5` and
`controller_triton`. The generic template passed the 8BitDo diagnostic; the
other controller families have not been tested on their hardware.
Use `--controller-index` when the listing shows another index. The tested
8BitDo used index 1 and `--controller-type controller_generic`; include those
options in its preview/apply commands, including `--frame-routing`. Restore
requires the matching index and routing flag.

### Frame controller routing workaround

On the tested client, Steam selected the correct layout for the full shortcut
ID but activated input under `shortcut_id & 0xFFFFFF`. Assigning only the normal
shortcut layout produced no inputs. Assigning the matching shortened ID worked
for both controllers; restoring its default and restarting reproduced the
failure. This is a confirmed requirement of this diagnostic on this client,
not a claim about all Steam versions or all games.

`--frame-routing` explicitly targets that shortened ID instead of the full
shortcut ID, with a separate `selection-frame-routing-*.json` backup. It checks
that the parent is an existing non-Steam shortcut, the shortened ID matches it,
the ID is outside the reserved low range, and no other listed Steam entry owns
that ID or shares its shortened ID. It also checks for a collision again immediately before writing.
Shortened IDs can collide with other shortcuts or future Steam entries; this
experimental workaround is not a universal Steam fix. Restore it when removing
the layout. Do not apply it globally or change Steam's desktop/dashboard layouts.

Restart the game through Steam after setup. Default layouts are restored with
Steam's clear-selection API; saved explicit layouts are restored by their URL.

| Control | Game controls (initial mode) | Pointer mode |
| --- | --- | --- |
| D-pad / left stick | Arrow keys | Arrow keys |
| R3 | Enable pointer mode | Return to game controls |
| Right stick | Native right stick | Relative mouse movement |
| RT | Native trigger | Left click; hold to drag |
| LT | Native trigger | Right click |
| A / B / Y | Enter / Escape / Escape | Same |
| X | Ren'Py: H; RPG Maker: Shift | Same |
| Start / Back | Escape / Ren'Py: Tab, RPG Maker: Escape | Same |
| Bumpers | Ren'Py: Page Up/Down; RPG Maker: Q/W | Same |

R3 is reserved for switching modes. Selecting this profile replaces the selected
layout with these bindings; it does not merge an arbitrary game's custom layout.
No game scripts are injected. Steam provides ordinary keyboard/mouse events,
including held mouse buttons. This cannot add mouse interaction to a game that
never implemented it. Custom controls and plugins still need game-specific checks.

Setup uses Steam's local debugging interface at `127.0.0.1:8080`; it fails with
an error if the interface is unavailable. Its controller-selection methods are
internal client APIs and may change. Templates use content-addressed names and
checksums; personal templates are not overwritten. Setup neither enables Steam
Input globally nor restarts Steam or the display session.

## Validation so far

Automated checks cover profile bindings, portable packaging, checksums,
per-shortcut selection backups, restoration, disabled Steam Input and refusing
to overwrite a later layout. On the live Frame, Steam recognized both action
sets and accepted the profile for a separate diagnostic non-Steam entry. The
asset-free probe in `experiments/controller-input/input_probe.py` opened through
Steam on its inherited display with the correct Steam game identity.
Existing game selections were left unchanged. The user confirmed movement,
R3 pointer switching, click/drag and switching back on the Frame controllers and
8BitDo Ultimate 2. Recorded ordinary key press/release and mouse press/drag/release
events corroborated the test. Removing the shortened-ID assignments and restarting
made inputs stop; reapplying them restored the working setup. This validates the
diagnostic path, not compatibility with every supported engine or game. Complete
the remaining disconnect/overlay and additional-engine acceptance checks below.

In the 2026-10-16 game checks, the user reported all requested controls working
in the isolated Ren'Py 8.3.7 copy and reported the MV 1.6.1 copy working. MV
telemetry independently recorded all four directional keys reaching the engine,
confirm/cancel states and ordinary mouse-button events. Both games opened in
gamescope under their own Steam shortcut IDs. Their original entries, layouts
and save data were left separate. This is functional input evidence, not a
full-game completion or performance certification.

The user subsequently confirmed the MV dashboard checks (holding a direction
and holding RT in pointer mode, releasing before returning) and 8BitDo
disconnect/reconnect all passed without stuck inputs. These observations apply
to the tested setup; they do not certify overlay/reconnect behavior in every
engine, game or controller family.

## Required behavior

Converted Ren'Py and RPG Maker games should offer consistent controller input
and a right-thumbstick mouse-pointer option for interfaces that do not work
with ordinary controller navigation. Pointer support is part of the requested
feature scope, not an optional future stretch goal.

For RPG Maker, both D-pad and left stick should support movement and menu
navigation. Preserve the game's movement rules, including four-direction versus
eight-direction behavior. For Ren'Py, normalize the equivalent menu/choice
navigation and standard actions while retaining game-specific controls where
possible.

The pointer option must provide real usable mouse interactions, not only a
cursor graphic:

- Right stick controls pointer velocity. Releasing it stops the pointer without
  snapping back to the center.
- Configurable deadzone, speed and response curve support both large movements
  and small targets. A precision modifier is worth testing.
- Provide left-click and right-click bindings. Preserve mouse-down while held
  and mouse-up on release so dragging works where the game supports it.
- Keep D-pad and left-stick navigation available alongside pointer control.
- Prevent the right stick from also navigating menus or firing another action.
- Avoid duplicate controller/keyboard/mouse actions from the same binding.
- Release held inputs on focus loss, controller disconnect and exit. Verify that
  overlays and Steam's own UI do not receive unintended background-game input.
- Preserve existing keyboard/mouse operation. Do not silently overwrite a user's
  existing Steam Input layout.

A starting layout to test is D-pad/left stick for directions, right stick for
pointer, right trigger for left mouse button and left trigger for right mouse
button. Trigger choices remain provisional: games may already use them for
rollback, skip or other important actions. A native binding and its emulated
mouse counterpart must not both fire unintentionally.

## Existing support and injection points

| Family | Existing upstream behavior | Candidate conversion intervention |
| --- | --- | --- |
| Ren'Py | D-pad and sticks map to focus/navigation events; `config.pad_bindings` exposes actions | Add a version-compatible `.rpy` initialization file to the converted copy, merging or explicitly overriding selected bindings |
| RPG Maker MV/MZ | Standard gamepad input combines D-pad buttons 12–15 with left-stick axes 0–1 | Add a separate compatibility script initialized at the appropriate point after relevant engine/plugins; preserve custom input handling |
| XP/VX/VX Ace via mkxp-z | Current upstream defaults bind D-pad and left stick to directional actions | Verify our pinned runtime and saved bindings first; use runtime configuration or narrowly scoped Ruby compatibility code if necessary |
| 2000/2003 via EasyRPG | Documented movement controls include D-pad and left stick | Verify Player configuration and delivered controller events before adding overrides |

The existing MV/MZ compatibility script is injected before the engine scripts.
That hook cannot simply modify `Input` immediately: it may not exist yet, and
later plugins may replace it. A new normalization hook needs explicit startup
ordering and compatibility checks. The mkxp backend already supports Ruby
preloads, but games can also redefine input later in their own scripts.

Ren'Py custom screens that bind specific keys, custom displayables and minigames
may bypass ordinary navigation actions. Check the actual runtime generation;
current documentation is not proof that every older supported release exposes
identical APIs.

## Preferred Frame implementation: Steam Input

### Prerequisite: launch into the intended Steam display session

The user reports converted games opening on the Frametop desktop rather than
the Steam-managed gamescope display while Frametop is active. Repository
inspection found a concrete contributor: `_FRAME_ENV_PREAMBLE` in
`rpgmframe/launchers.py` previously imported the Plasma process's graphics variables whenever
its runtime or Xauthority indicates Frametop, even if the incoming launch
environment already has a display. This preamble is shared by RPGMFrame and
several native backends. The bundled Steam API graphics guard can then preserve
that selected desktop environment across Steam initialization.

The clarified policy is automatic: a game launched directly from the desktop
keeps the desktop session; a game launched through its Steam entry keeps Steam's
session. The shared launcher now leaves the caller's DISPLAY, WAYLAND_DISPLAY,
XDG_RUNTIME_DIR and XAUTHORITY intact, including unset values. It never imports
Plasma's environment, even when a headless invocation supplies no display.
Headless callers must supply their intended graphics session explicitly.

The optional bundled Steam API graphics guard now protects either inherited
display session, rather than activating only for Frametop. It forwards real
Steam calls as before. Steam identity and launch tracking variables are not
rewritten. No compositor is started or restarted, and no display number is
hardcoded. No new launch-target flag is needed for this policy.

RenFrame's full-runtime and grafted launchers already preserve their incoming
graphics environment. Executable regression tests now cover both paths, along
with NW.js, mkxp-z, Godot and the shared native preamble. Tests exercise distinct
Steam and desktop environments with a competing Plasma process, unset X11 or
Wayland fields, argument forwarding and optional guard activation.

This fix depends on Steam/the desktop supplying the correct initial session;
an external launch-option wrapper that explicitly reroutes to Frametop still
needs separate diagnosis. Pointing a manually started process at gamescope alone
does not establish Steam Input association. Check backend-specific SDL/Qt/browser
overrides if a title still selects the wrong display.

The initial session-routing investigation could not reach the Frame. A later
live Ren'Py 8.3.7 test opened in gamescope with its own Steam shortcut identity,
and the user confirmed its controls worked. An isolated MV 1.6.1 test also opened on Steam's display with its own app ID;
its passive observer confirmed the inherited display and engine startup. Existing installed packages and built converter binaries were
not patched; regenerate affected packages with the updated converter to obtain
the new launcher. Test this prerequisite before claiming that controller
normalization fixes Frame input.

The experimental implementation uses per-shortcut Steam Input layouts.
Valve documents analog-stick relative-mouse output and emulated mouse buttons.
This can deliver ordinary mouse events to SDL/Ren'Py and NW.js/browser games
without maintaining a separate virtual pointer implementation per engine.

Our prior Frame report observed keyboard/mouse devices without a gamepad exposed
in that particular session. Establish what the game actually receives when
launched through its normal Steam shortcut: raw controller input, emulated
keyboard/mouse, or both. An engine-side patch cannot read an axis the runtime
never receives.

Continue validating the packaged per-shortcut layout and reversible setup helper. Do not
assume that setting a layout automatically is available through a stable API.
If selection requires the Steam UI, provide a concrete import/selection path.
Validate the Frame's actual controller and launch environment before advertising
support; generic Steam Input documentation is feasibility evidence only.

## Engine-side pointer fallback

If a fallback independent of Steam is needed, assess each engine separately:

- Ren'Py has `renpy.set_mouse_pos`, but its documentation says this is unlikely
  to work on Linux Wayland. Continuous analog reading, cursor visibility, hover,
  click and drag dispatch also require implementation. Default Ren'Py bindings
  use the right stick for focus navigation, so pointer mode must suppress that
  conflict. Triggers have native actions too.
- MV/MZ can potentially integrate a virtual cursor with their mouse/touch
  handling, but must correctly map physical/window coordinates to the logical
  canvas, including scaling and letterboxing. DOM events and direct engine
  hooks are not interchangeable for every plugin.
- mkxp-z and EasyRPG need separate investigation. Generating mouse events does
  not add hit testing or clickable menus to games that never supported a mouse.
  Existing mouse scripts/plugins must be compatible with the replacement runtime.

Prefer ordinary mouse events where possible. A drawn cursor that does not
trigger the game's existing hover/click/drag logic is not a successful fallback.
Do not assume a system-wide input daemon or privileged device access is required
before testing Steam Input's existing route.

## Acceptance checks

1. Test one representative Ren'Py game and one MV/MZ game through their normal
   Steam shortcuts on the Frame, including a mouse-dependent screen.
2. Verify D-pad alone, stick alone, both held together, and releasing either
   while the other remains held. Check menus, movement, diagonals and repeat.
3. Verify pointer speed near the deadzone and at full deflection, all screen
   edges, hover, single click, held click/drag, release and right-click.
4. Repeat windowed/fullscreen and with display scaling/letterboxing. Confirm
   the clickable location matches the displayed cursor.
5. Test focus loss, Steam overlay, disconnect/reconnect and switching between
   physical mouse and controller. No stuck movement, clicks or phantom actions.
6. Check that one press produces one action, particularly triggers in Ren'Py,
   and that moving the right stick does not also change menu focus.
7. Extend to mkxp-z and EasyRPG with separate evidence and explicit mouse-support
   limitations. Preserve saves and user mappings throughout.

## Sources

- [Ren'Py keymaps and gamepad defaults](https://www.renpy.org/doc/html/keymap.html)
- [Ren'Py pointer positioning and platform limitations](https://www.renpy.org/doc/html/other.html#renpy.set_mouse_pos)
- [RPG Maker MV input source](https://github.com/rpgtkoolmv/corescript/blob/master/js/rpg_core/Input.js)
- [RPG Maker MZ input source](https://developer.rpgmakerweb.com/rpg-maker-mz/Input.js.html)
- [mkxp-z upstream default bindings](https://github.com/mkxp-z/mkxp-z/blob/dev/src/input/keybindings.cpp)
- [EasyRPG controls](https://wiki.easyrpg.org/user/player/buttons)
- [Steam Input source modes](https://partner.steamgames.com/doc/features/steam_controller/input_source_modes)
- [Steam Input legacy mouse/keyboard bindings](https://partner.steamgames.com/doc/features/steam_controller/legacy_mode)
- [Existing Frame input observations](hardware-feedback-2026-10-11.md)
