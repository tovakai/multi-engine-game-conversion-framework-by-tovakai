# Controller validation on the Frame

These probes are development tools. They are not injected into ordinary
converted games. See [the controller setup guide](../../docs/controller-normalization.md)
for the opt-in conversion feature.

## Window probe

Run `python3 input_probe.py` through a separate non-Steam shortcut with the
experimental profile selected. It needs Tk. The window logs key presses and
releases, focus changes, mouse movement, held drag, and mouse button events to
`/tmp/megcfbt-controller-input-events.jsonl`.

The Frame controllers and an 8BitDo Ultimate 2 passed movement, R3 pointer
switching, click/drag, and switching back during the 2026-10-15 session. Both
needed their own controller-type profile. The tested Frame client also required
the explicit shortened-ID routing assignment described in the setup guide.

## Actual-game checks

Use separate game copies and separate Steam shortcuts. Do not copy existing
saves into the test. Keep the controller selection receipts beside each copy.
Only change launchers or install observers in these copies.

For Ren'Py, pass `--savedir /absolute/path/to/test-saves` to the game launcher.
The session's test uses Ren'Py 8.3.7. Check menus and choices, confirm/back,
pointer hover/clicks, settings-slider drag, and both R3 transitions. Check that
pointer movement does not simultaneously move keyboard/gamepad focus.

For RPG Maker MV, use the updated NW.js launcher so it retains the graphics
session Steam supplies. Keep NW.js browser storage separate with
`--user-data-dir=/absolute/path/to/test-browser-data`. Keep local game saves
inside the test copy, and give `LOCALAPPDATA` and `APPDATA` test-only paths.
The session's test uses MV 1.6.1. On 2026-10-16 the user confirmed the requested
controls worked in both the isolated Ren'Py and MV games; overlay/disconnect
checks subsequently passed in MV without stuck movement or mouse buttons.
The controller setup guide records the supported scope.

To observe MV input, load `nwjs_probe.js` after the engine scripts in the copied
game's `index.html`. Set `MEGCFBT_CONTROLLER_TEST_LOG` to an absolute writable
JSONL path before launch. Its parent directory must already exist. The probe
records control-key down/up, mouse-button events, focus changes, and changed
engine/gamepad state at 100 ms intervals. It neither remaps nor consumes events.
Short presses can fall between state samples; use the event records alongside
the state samples and the visible game behavior. Remove the observer after the
test; synchronous logging can affect performance.

Check each controller independently:

1. D-pad movement, left-stick movement, menu navigation, confirm/back, and run.
2. Hold D-pad and stick together, then release either while holding the other.
3. R3 enables pointer; RT clicks and drags; LT right-clicks where supported.
4. Pointer movement does not also move the character or change menu focus.
5. R3 disables pointer and restores native right-stick/trigger output.
6. Open/close the Steam overlay while moving or holding a mouse button.
7. Disconnect/reconnect and check for stuck directions/buttons and changed
   controller indices. Restore refuses a different controller type at the
   backed-up index.

Engine startup, profile parsing, and visible pointer motion alone do not prove
that these acceptance checks pass. Record outcomes separately for each runtime
and game. MV results do not establish compatibility with MZ, mkxp-z or EasyRPG.
