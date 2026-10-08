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

Before merging this feature, still test a clean Windows GUI download/conversion,
offline cache reuse and a fresh converted archive on Steam Frame.

No game payloads or proprietary Steamworks SDK headers should be published.

## User experience

When a published recipe matches, the converter automatically downloads and
caches the runtime. The GUI shows a separate download bar and logs status.
On later conversions it uses the cache. If the download fails or verification
fails, conversion stops with a clear error; it never substitutes an unrelated
runtime. Unsupported custom Godot builds still require manual handling.
