# Downloadable GodotSteam runtime

Supported custom Godot games should use the normal **Convert** button. The
runtime downloader is SHA-256 pinned, caches verified archives and reports
byte-level progress in the GUI.

## Published Brotato compatibility runtime

The first runtime is published as the prerelease
`runtime-godot-3.7-dev1-godotsteam-3.30-arm64-v1`.

Its archive contains only `godot.arm64` and `runtime.json`. The generated
launcher uses the Frame-installed native Steam API from
`/opt/steamvr/bin/linuxarm64`; the release asset does not bundle
`libsteam_api.so`.

The archive SHA-256 is pinned in the application:

`f87130aa44fae591a098eb03df8a419f84b47d25100756f04bb645e44102e34a`

The stripped runtime was validated with a complete Brotato 1.1.14.6 gameplay
run on Steam Frame, including successful native Steam initialization,
online status and ownership detection.

No game payloads or proprietary Steamworks SDK headers should be published.

## Godot 3.5.1 compatibility runtime

Godot 3.5.1 exports with built-in GodotSteam now use the same automatic Windows
conversion path. The runtime prerelease is
[`runtime-godot-3.5.1-godotsteam-3.30-arm64-v1`](https://github.com/tovakai/multi-engine-game-conversion-framework-by-tovakai/releases/tag/runtime-godot-3.5.1-godotsteam-3.30-arm64-v1).

The recipe preserves Godot source `6fed1ffa313c6760fa88b368ae580378daaef0f0`
and GodotSteam 3.30 source `f73d138b56fe971a940dd0498e8b9d0fc8fdcffd`,
including the legacy dictionary initialization adapter. The adapter forwards
actual Steam API results. Only debug symbols were removed from the tested engine.

Archive SHA-256:
`6abe8ccc6099a37c677fae5b5fea906df1ce35a2d9e1e0bdec1e98d08c361cfa`

The archive contains the engine, receipt, engine/component license notices,
compatibility source patches and a source-build worker. It contains no Steam API
binary, Steamworks SDK headers or game content. Generated launchers resolve
Frame's installed `/opt/steamvr/bin/linuxarm64/libsteam_api.so` automatically.
Windows conversion and ZIP creation require no SDK selection, SSH or compilation.
Other ARM64 devices must supply a compatible native Steam library themselves.

Cassette Beasts' animated 3D title screen was rendered natively with the packaged
engine and Frame's installed Steam library. The old Steam initialization failure
is resolved. A nonfatal Godot 3.5 X11 keyboard-layout warning uses its QWERTY
fallback. A subsequent test of the frozen Windows GUI's ZIP accepted an injected
E key in Frame's desktop session and advanced to the update notices. Physical
controller input, extended gameplay, save/load and online features remain
unverified; automatic provisioning does not certify full game compatibility.

On 2026-10-10, frozen-GUI verification passed clean-cache conversions for Cassette
Beasts, Brotato, Silly Linguine and Unnamed Space Idle. Each used the real shipped
drop handler, enabled Convert button, runtime downloader and ZIP builder without
a runtime override. Cassette Beasts' repeated conversion reported no runtime
download. ZIP CRC/required contents and original source hashes/mtimes passed.
The final Windows regression run passed 290 tests with two symlink-privilege
skips. Hardware verification used the ZIP produced by the frozen Windows GUI,
not a separately prepared SDK or manually edited game package.

## Godot 4.6.0 and 4.7.2

Silly Linguine and Unnamed Space Idle use existing checksum-pinned upstream
GodotSteam ARM64 export templates, with their upstream Steam libraries. No
duplicate project runtime releases are needed. These recipes download on Windows
and record adjacent-PCK loading capability; generated packages use `godot.pck`
beside the executable rather than the rejected `--main-pack` override.

## Frozen-GUI verification

Release checks can exercise the actual packaged GUI without native dialog focus:

```powershell
& '.\Multi-Engine Game Conversion Framework by tovakai.exe' `
  --verify-gui-conversion 'C:\path\to\original-game' `
  --output-dir 'C:\path\to\empty-test-output' `
  --receipt 'C:\path\to\gui-verification.json'
```

The output directory must already exist and be separate from the source. Set
`RPGMFRAME_CACHE_DIR` to a new test cache to verify first-download behavior. The
runner invokes the real GUI drop handler and enabled Convert button; detection,
downloads, cache validation and packaging are unchanged. Only modal completion
dialogs are suppressed. The JSON receipt records frozen status, widget eligibility,
download progress, output and errors. Source hashing and hardware tests remain
separate checks. Normal application startup opens the usual interactive GUI.

## User experience

When a published recipe matches, the converter automatically downloads and
caches the runtime. The GUI shows a separate download bar and logs status.
On later conversions it uses the cache. If the download fails or verification
fails, conversion stops with a clear error; it never substitutes an unrelated
runtime. Unsupported custom Godot builds still require manual handling.
