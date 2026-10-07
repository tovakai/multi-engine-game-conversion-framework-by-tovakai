#!/usr/bin/env bash
set -euo pipefail

GODOT_REF_DEFAULT="a117d512b00f1646db174e703e7e888519b64608"
GODOTSTEAM_REF_DEFAULT="v3.31"
GODOTSTEAM_REPO_DEFAULT="https://codeberg.org/godotsteam/godotsteam.git"

GODOT_REF="${GODOT_REF:-$GODOT_REF_DEFAULT}"
GODOTSTEAM_REF="${GODOTSTEAM_REF:-$GODOTSTEAM_REF_DEFAULT}"
GODOTSTEAM_REPO="${GODOTSTEAM_REPO:-$GODOTSTEAM_REPO_DEFAULT}"
WORK_DIR="${WORK_DIR:-$PWD/.runtime-work/godot-3.7-dev-godotsteam-3.31}"
OUTPUT_DIR="${OUTPUT_DIR:-$PWD/dist/runtimes/godot-3.7-dev-godotsteam-3.31-arm64}"
STEAMWORKS_SDK="${STEAMWORKS_SDK:-}"
GODOTSTEAM_SRC=""
JOBS="${JOBS:-}"
CLEAN=0

usage() {
    cat <<'EOF'
Build a Linux ARM64 Godot 3.7-dev + GodotSteam 3.31 runtime candidate.

This script intentionally requires a user-supplied Steamworks SDK. The SDK is
not downloaded, vendored, or redistributed by tovakai.

Usage:
  scripts/build-custom-godot-arm64.sh --steamworks-sdk PATH [options]

Options:
  --steamworks-sdk PATH   Steamworks SDK root, or its sdk/ directory (required)
  --godotsteam-src PATH  Existing GodotSteam 3.31 source tree instead of cloning
  --godot-ref REF        Godot source commit/ref
  --godotsteam-ref REF   GodotSteam source ref used when cloning
  --work-dir PATH        Build workspace
  --output PATH          Runtime bundle output directory
  -j, --jobs N           Parallel SCons jobs
  --clean                Remove the workspace before starting
  -h, --help             Show this help

The first supported build mode is native ARM64 Linux. Godot 3.x's X11 build
logic does not provide a general x86->ARM cross-compilation path, so keeping
this first recipe native makes the result much easier to reason about.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --steamworks-sdk)
            STEAMWORKS_SDK="$2"
            shift 2
            ;;
        --godotsteam-src)
            GODOTSTEAM_SRC="$2"
            shift 2
            ;;
        --godot-ref)
            GODOT_REF="$2"
            shift 2
            ;;
        --godotsteam-ref)
            GODOTSTEAM_REF="$2"
            shift 2
            ;;
        --work-dir)
            WORK_DIR="$2"
            shift 2
            ;;
        --output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -j|--jobs)
            JOBS="$2"
            shift 2
            ;;
        --clean)
            CLEAN=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ -z "$STEAMWORKS_SDK" ]]; then
    echo "ERROR: --steamworks-sdk PATH is required." >&2
    exit 2
fi

case "$(uname -m)" in
    aarch64|arm64)
        ;;
    *)
        echo "ERROR: this first runtime recipe must be built on native Linux ARM64." >&2
        echo "       Current architecture: $(uname -m)" >&2
        exit 2
        ;;
esac

missing=0
for cmd in git python3 scons pkg-config gcc g++; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Missing build command: $cmd" >&2
        missing=1
    fi
done
if [[ "$missing" -ne 0 ]]; then
    exit 2
fi

for pkg in x11 xcursor xinerama xext xrandr xrender xi gl; do
    if ! pkg-config --exists "$pkg"; then
        echo "Missing pkg-config development package: $pkg" >&2
        missing=1
    fi
done
if [[ "$missing" -ne 0 ]]; then
    echo "Install the missing Linux/X11 development packages before building." >&2
    exit 2
fi

if [[ -f "$STEAMWORKS_SDK/public/steam/steam_api.h" ]]; then
    SDK_DIR="$(cd "$STEAMWORKS_SDK" && pwd)"
elif [[ -f "$STEAMWORKS_SDK/sdk/public/steam/steam_api.h" ]]; then
    SDK_DIR="$(cd "$STEAMWORKS_SDK/sdk" && pwd)"
else
    echo "ERROR: could not find public/steam/steam_api.h under $STEAMWORKS_SDK" >&2
    exit 2
fi

STEAM_ARM64="$SDK_DIR/redistributable_bin/linuxarm64/libsteam_api.so"
if [[ ! -f "$STEAM_ARM64" ]]; then
    echo "ERROR: Steamworks SDK has no Linux ARM64 libsteam_api.so." >&2
    echo "       SDK 1.63 or newer is required for the ARM64 Steamworks runtime." >&2
    exit 2
fi

if [[ "$CLEAN" -eq 1 ]]; then
    rm -rf "$WORK_DIR"
fi
mkdir -p "$WORK_DIR"

GODOT_DIR="$WORK_DIR/godot"
GODOTSTEAM_WORK="$WORK_DIR/godotsteam"

if [[ ! -d "$GODOT_DIR/.git" ]]; then
    echo "==> Fetching Godot source"
    rm -rf "$GODOT_DIR"
    git init -q "$GODOT_DIR"
    git -C "$GODOT_DIR" remote add origin https://github.com/godotengine/godot.git
fi

echo "==> Checking out Godot $GODOT_REF"
git -C "$GODOT_DIR" fetch -q --depth 1 origin "$GODOT_REF"
git -C "$GODOT_DIR" checkout -q --detach FETCH_HEAD

rm -rf "$GODOTSTEAM_WORK"
if [[ -n "$GODOTSTEAM_SRC" ]]; then
    if [[ ! -f "$GODOTSTEAM_SRC/SCsub" || ! -f "$GODOTSTEAM_SRC/godotsteam.cpp" ]]; then
        echo "ERROR: --godotsteam-src does not look like a GodotSteam module tree." >&2
        exit 2
    fi
    echo "==> Copying supplied GodotSteam source"
    mkdir -p "$GODOTSTEAM_WORK"
    cp -a "$GODOTSTEAM_SRC/." "$GODOTSTEAM_WORK/"
else
    echo "==> Fetching GodotSteam $GODOTSTEAM_REF"
    if ! git clone -q --depth 1 --branch "$GODOTSTEAM_REF" "$GODOTSTEAM_REPO" "$GODOTSTEAM_WORK"; then
        rm -rf "$GODOTSTEAM_WORK"
        echo "ERROR: GodotSteam clone failed." >&2
        echo "       Supply a local v3.31 source tree with --godotsteam-src PATH." >&2
        exit 2
    fi
fi

echo "==> Staging user-supplied Steamworks SDK"
rm -rf "$GODOTSTEAM_WORK/sdk"
mkdir -p "$GODOTSTEAM_WORK/sdk"
cp -a "$SDK_DIR/public" "$GODOTSTEAM_WORK/sdk/"

# GodotSteam versions predating official Linux ARM64 support may still resolve
# the 64-bit Linux library through redistributable_bin/linux64. Keep the actual
# ARM64 library in both locations inside this disposable build tree. This does
# not modify or redistribute the user's SDK.
mkdir -p \
    "$GODOTSTEAM_WORK/sdk/redistributable_bin/linuxarm64" \
    "$GODOTSTEAM_WORK/sdk/redistributable_bin/linux64"
cp -a "$STEAM_ARM64" "$GODOTSTEAM_WORK/sdk/redistributable_bin/linuxarm64/libsteam_api.so"
cp -a "$STEAM_ARM64" "$GODOTSTEAM_WORK/sdk/redistributable_bin/linux64/libsteam_api.so"

if [[ -z "$JOBS" ]]; then
    if command -v nproc >/dev/null 2>&1; then
        JOBS="$(nproc)"
    else
        JOBS=4
    fi
fi

echo "==> Building Godot ARM64 release template with GodotSteam"
(
    cd "$GODOT_DIR"
    scons -j"$JOBS" \
        platform=x11 \
        tools=no \
        target=release \
        arch=arm64 \
        bits=64 \
        production=yes \
        lto=none \
        speechd=no \
        custom_modules="$GODOTSTEAM_WORK"
)

BINARY="$(find "$GODOT_DIR/bin" -maxdepth 1 -type f -name 'godot.x11.opt*' | sort | head -n 1)"
if [[ -z "$BINARY" || ! -f "$BINARY" ]]; then
    echo "ERROR: Godot build completed but no release template was found." >&2
    exit 1
fi

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"
cp -a "$BINARY" "$OUTPUT_DIR/godot.arm64"
chmod +x "$OUTPUT_DIR/godot.arm64"
cp -a "$STEAM_ARM64" "$OUTPUT_DIR/libsteam_api.so"

GODOT_SOURCE_SHA="$(git -C "$GODOT_DIR" rev-parse HEAD)"
if [[ -d "$GODOTSTEAM_WORK/.git" ]]; then
    GODOTSTEAM_SOURCE_SHA="$(git -C "$GODOTSTEAM_WORK" rev-parse HEAD)"
else
    GODOTSTEAM_SOURCE_SHA="supplied-source-tree"
fi
GODOT_VERSION_OUTPUT="$(
    LD_LIBRARY_PATH="$OUTPUT_DIR" "$OUTPUT_DIR/godot.arm64" --version 2>/dev/null |
        head -n 1 || true
)"

cat > "$OUTPUT_DIR/runtime.json" <<EOF
{
  "kind": "godot-custom",
  "architecture": "aarch64",
  "godot_ref_requested": "$GODOT_REF",
  "godot_source_sha": "$GODOT_SOURCE_SHA",
  "godot_version_output": "$GODOT_VERSION_OUTPUT",
  "godotsteam_ref_requested": "$GODOTSTEAM_REF",
  "godotsteam_source_sha": "$GODOTSTEAM_SOURCE_SHA",
  "steamworks_arm64_runtime": "user-supplied",
  "candidate_for": "Godot 3.7 development exports with built-in GodotSteam 3.31"
}
EOF

echo
echo "Runtime bundle built:"
echo "  $OUTPUT_DIR"
echo
echo "Contents:"
ls -lh "$OUTPUT_DIR"
echo
echo "Next step: select this directory as the custom runtime in tovakai."
