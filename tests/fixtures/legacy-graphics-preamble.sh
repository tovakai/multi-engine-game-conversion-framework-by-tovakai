#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Folder transfers through Windows can lose Linux executable permissions.
for binary in "$ROOT/nw" "$ROOT/chrome_crashpad_handler" "$ROOT/mkxp-z.aarch64" "$ROOT/godot.arm64"; do
    [[ -f "$binary" && ! -L "$binary" && ! -x "$binary" ]] || continue
    chmod u+x "$binary" 2>/dev/null || true
done

import_graphics_env() {
    local pid="$1"
    local key value
    while IFS='=' read -r key value; do
        case "$key" in
            DISPLAY|WAYLAND_DISPLAY|XDG_RUNTIME_DIR|XAUTHORITY)
                export "$key=$value"
                ;;
        esac
    done < <(tr '\0' '\n' < "/proc/$pid/environ")
}

if command -v pgrep >/dev/null 2>&1; then
    plasma_pid="$(pgrep -n plasmashell || true)"
    if [[ -n "$plasma_pid" && -r "/proc/$plasma_pid/environ" ]]; then
        plasma_runtime="$(
            tr '\0' '\n' < "/proc/$plasma_pid/environ" |
                sed -n 's/^XDG_RUNTIME_DIR=//p' |
                tail -n 1
        )"
        plasma_xauth="$(
            tr '\0' '\n' < "/proc/$plasma_pid/environ" |
                sed -n 's/^XAUTHORITY=//p' |
                tail -n 1
        )"

        if [[ "$plasma_runtime" == */frametop || "$plasma_xauth" == */frametop/* ]]; then
            import_graphics_env "$plasma_pid"
        elif [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
            import_graphics_env "$plasma_pid"
        fi
    fi
fi

if [[ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]]; then
    user_bus="/run/user/$(id -u)/bus"
    if [[ -S "$user_bus" ]]; then
        export DBUS_SESSION_BUS_ADDRESS="unix:path=$user_bus"
    fi
fi

# Steam API initialization can replace DISPLAY before the engine creates its
# window. Keep the selected Frame desktop while forwarding the real API calls.
if [[ ( "${XDG_RUNTIME_DIR:-}" == */frametop || "${XAUTHORITY:-}" == */frametop/* )
      && -f "$ROOT/libframe_steam_env.so" ]]; then
    export TOVAKAI_FRAME_PRESERVE_GRAPHICS=1
    export LD_PRELOAD="$ROOT/libframe_steam_env.so${LD_PRELOAD:+:$LD_PRELOAD}"
fi

