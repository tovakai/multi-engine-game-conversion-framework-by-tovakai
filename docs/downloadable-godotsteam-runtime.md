# Downloadable GodotSteam runtime

Supported custom Godot games should use the normal **Convert** button. The
runtime downloader is SHA-256 pinned, caches verified archives and reports
byte-level progress in the GUI.

## Publishing the first runtime

The runtime archive **has not been published yet**. The shipped
`rpgmframe/godot_runtime_index.json` deliberately contains no enabled recipes.
Do not advertise automatic Windows conversion until the following steps are
complete:

1. Strip a **copy** of the tested Godot ARM64 executable; keep the working
   unstripped binary untouched.
2. Test the stripped executable on Steam Frame with the original Brotato PCK.
3. Create a flat `tar.gz` containing `godot.arm64` and `runtime.json`.
   For the initial version, include the known-working ARM64 `libsteam_api.so`
   only if redistribution is permitted. Otherwise adapt the launcher to use
   the installed Frame copy and test the new packaging end-to-end.
4. Upload the archive to a versioned GitHub Release asset.
5. Compute the archive's SHA-256 and add the pinned GitHub Release URL and hash
   to the index under
   `godot-3.7-dev1-godotsteam-3.30-steamworks-1.62-frame-arm64-v1`.
6. Test download, offline cache reuse, corrupted download rejection and a
   clean Windows GUI conversion, followed by a fresh Steam Frame launch.

No game payloads or proprietary Steamworks SDK headers should be published.

## User experience

When a published recipe matches, the converter automatically downloads and
caches the runtime. The GUI shows a separate download bar and logs status.
On later conversions it uses the cache. If the download fails or verification
fails, conversion stops with a clear error; it never substitutes an unrelated
runtime. Unsupported custom Godot builds still require manual handling.
