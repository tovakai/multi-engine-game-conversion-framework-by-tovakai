# The Last Sovereign: RGSS input compatibility

The Last Sovereign 1.2.2 is an RPG Maker VX Ace game. Its Cidiomar input
script uses Ruby 1.9's removed `DL::CPtr` API and Windows keyboard functions;
its controller script uses XInput. Merely packaging it with mkxp-z previously
failed at startup with `uninitialized constant Input::DL`.

RPGMFrame now packages a shared modern-Ruby input preload after the runtime's
Win32 wrapper. It provides bounded, owned Fiddle allocations with the legacy
integer-byte pointer interface, refreshes actual SDL keyboard state, maps the
first connected SDL controller into XInput's state layout, and uses SDL UTF-8
text events for the legacy text-entry method. Rumble is explicitly unsupported.
The adapter does not implement or report success for Steamworks APIs.

The game also contains one trailing comma in a return expression that modern
Ruby rejects. A SHA-256-gated adaptation removes that comma from the exact
audited `Battle Bust Config` script **in memory**. Changed or unrecognized
scripts remain untouched. The original encrypted archive is never rewritten.

The pinned ARM64 mkxp-z runtime on Steam Frame passed a 180-frame startup probe
and a synthetic input regression fixture covering allocation bounds, keyboard
release, mouse input, alias-safe native polling, Unicode text, controller
button/axis layouts, packet changes and disconnects. Inspection through router
conversion and ZIP packaging is covered by automated tests.

The user reported "Works good" after launching the repaired existing entry
from SteamVR and being asked to check its menu and controllers. Saving and
relaunch were not separately confirmed. Steamworks achievements are unsupported/unverified. The
existing non-Steam installation remains the available workflow for this backend.

New conversions include the preload automatically. Existing conversions can
be repaired by adding `scripts/preload/megcfbt_rgss_input.rb` to their payload
and appending `../scripts/preload/megcfbt_rgss_input.rb` to the payload's
`game/mkxp.json` preload list after its Win32 wrapper. Preserve the previous
configuration before repair and restart only the game to load the new script.
