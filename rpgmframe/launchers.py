"""Shared Frame-aware launcher templates for RPGMFrame backends."""

from __future__ import annotations

import shlex


_FRAME_ENV_PREAMBLE = r'''#!/usr/bin/env bash
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

'''


def nwjs_launcher_body() -> str:
    return _FRAME_ENV_PREAMBLE + r'''# Windows-authored NW.js plugins frequently expect these environment variables.
export LOCALAPPDATA="${LOCALAPPDATA:-${XDG_DATA_HOME:-$HOME/.local/share}}"
export APPDATA="${APPDATA:-${XDG_CONFIG_HOME:-$HOME/.config}}"
export USERPROFILE="${USERPROFILE:-$HOME}"

cd "$ROOT"
exec "$ROOT/nw" "$ROOT" "$@"
'''


def mkxp_launcher_body() -> str:
    return _FRAME_ENV_PREAMBLE + r'''# mkxp-z's Linux build honors SRCDIR before reading mkxp.json. Point it at
# the copied game so the package remains relocatable and gameFolder can stay ".".
export SRCDIR="$ROOT/game"

# mkxp-z currently truncates fractional drawable/window scale factors when
# converting mouse coordinates. Disable SDL HiDPI backing so pointer and game
# coordinates remain in the same pixel space on fractional-scale desktops.
export SDL_VIDEO_HIGHDPI_DISABLED="${SDL_VIDEO_HIGHDPI_DISABLED:-1}"

cd "$ROOT"
exec "$ROOT/mkxp-z.aarch64" "$@"
'''



def godot_launcher_body(
    pack_relative: str,
    *,
    force_zink: bool = False,
    adjacent_pack: bool = False,
) -> str:
    pack = shlex.quote(pack_relative)
    zink = (
        '''# The proven Godot 3.x custom runtime on Steam Frame uses Zink over
# Turnip instead of the host GLX path.
export MESA_LOADER_DRIVER_OVERRIDE="${MESA_LOADER_DRIVER_OVERRIDE:-zink}"
export GALLIUM_DRIVER="${GALLIUM_DRIVER:-zink}"

'''
        if force_zink
        else ""
    )
    pack_argument = '' if adjacent_pack else f' --main-pack "$ROOT"/{pack}'
    return _FRAME_ENV_PREAMBLE + f'''# Custom Godot modules such as GodotSteam
# may ship shared libraries beside the engine runtime.
steam_arm64_dir="/opt/steamvr/bin/linuxarm64"
if [[ -d "$steam_arm64_dir" ]]; then
    export LD_LIBRARY_PATH="$ROOT:$steam_arm64_dir${{LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}}"
else
    export LD_LIBRARY_PATH="$ROOT${{LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}}"
fi

{zink}cd "$ROOT/game"
exec "$ROOT/godot.arm64"{pack_argument} "$@"
'''
