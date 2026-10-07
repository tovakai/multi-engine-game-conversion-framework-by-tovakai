#!/usr/bin/env bash
# Package the tested Godot 3.7-dev1 + GodotSteam 3.30 ARM64 build for tovakai.
# This intentionally does not download game content or bundle the Steamworks SDK.
set -euo pipefail

usage() {
    echo "Usage: $0 GODOT_SOURCE_DIR ARM64_LIBSTEAM_API_SO OUTPUT_DIR" >&2
    echo "Requires the locally compiled, patched Godot 3.7-dev1/GodotSteam 3.30 build." >&2
    exit 2
}
[[ $# -eq 3 ]] || usage

SOURCE="$(realpath "$1")"
STEAM_LIB="$(realpath "$2")"
OUTPUT="$(realpath -m "$3")"
BINARY="$SOURCE/bin/godot.x11.opt.arm64"
RECIPE="godot-3.7-dev1-godotsteam-3.30-arm64"

[[ -f "$BINARY" && -f "$STEAM_LIB" ]] || {
    echo "Missing compiled Godot binary or native Steam API library" >&2
    exit 1
}
[[ -f "$SOURCE/modules/godotsteam/godotsteam.cpp" ]] || {
    echo "GodotSteam source module not found" >&2
    exit 1
}
[[ "$(git -C "$SOURCE" rev-parse HEAD)" == "a117d512b00f1646db174e703e7e888519b64608" ]] || {
    echo "Expected pinned Godot 3.7-dev1 source commit" >&2
    exit 1
}
if ! command -v readelf >/dev/null; then
    echo "readelf is required" >&2
    exit 1
fi
for file in "$BINARY" "$STEAM_LIB"; do
    readelf -h "$file" | grep -q 'Machine:.*AArch64' || {
        echo "Not an AArch64 ELF: $file" >&2
        exit 1
    }
done
for symbol in SteamInternal_FindOrCreateUserInterface SteamInternal_SteamAPI_Init; do
    readelf -Ws "$STEAM_LIB" | grep -q "$symbol" || {
        echo "Steam API library missing $symbol" >&2
        exit 1
    }
done
# Validate compiled module API markers, not just the source tree.
grep -a -q 'get_godotsteam_version' "$BINARY" || {
    echo "Binary does not appear to contain GodotSteam" >&2
    exit 1
}

[[ ! -e "$OUTPUT" ]] || {
    echo "Output exists, refusing overwrite: $OUTPUT" >&2
    exit 1
}
mkdir -p "$OUTPUT"
cp "$BINARY" "$OUTPUT/godot.arm64"
cp "$STEAM_LIB" "$OUTPUT/libsteam_api.so"
chmod +x "$OUTPUT/godot.arm64"

python3 - "$OUTPUT" "$RECIPE" "$BINARY" "$STEAM_LIB" <<'PY'
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
recipe = sys.argv[2]
def digest(path):
    h = hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
manifest = {
    "recipe": recipe,
    "status": "experimental",
    "godot_source_commit": "a117d512b00f1646db174e703e7e888519b64608",
    "godotsteam_source_tag": "v3.30",
    "steamworks_headers": "1.62",
    "steam_api": "native Linux ARM64 (Steamworks 1.63-compatible)",
    "requires_canvas_item_fix": True,
    "files": {
        "godot.arm64": digest(root / "godot.arm64"),
        "libsteam_api.so": digest(root / "libsteam_api.so"),
    },
}
(root / "runtime.json").write_text(json.dumps(manifest, indent=2) + "\n")
PY

echo "Runtime bundle ready: $OUTPUT"
echo "Set TOVAKAI_GODOTSTEAM_ARM64_RUNTIME=$OUTPUT when running the converter."
