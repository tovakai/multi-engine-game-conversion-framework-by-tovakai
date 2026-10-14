#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MEGCFBT_RESOURCE_OVERLAY="$ROOT/game/untilthen-native-overlay.pck"
export LD_LIBRARY_PATH="$ROOT/game/addons/fmod/native/linux:$ROOT/game/addons/godotsteam/linux${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
cd "$ROOT/game"
exec "$ROOT/runtime/godot.arm64" --path "$ROOT/game" --main-pack "$ROOT/game/UntilThen.pck" "$@"
