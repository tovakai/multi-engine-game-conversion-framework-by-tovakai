"""Shared Frame-aware launcher templates for RPGMFrame backends."""

from __future__ import annotations

import shlex


_FRAME_ENV_PREAMBLE = r'''#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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



def godot_launcher_body(pack_relative: str) -> str:
    pack = shlex.quote(pack_relative)
    return _FRAME_ENV_PREAMBLE + f'''cd "$ROOT/game"
exec "$ROOT/godot.arm64" --main-pack "$ROOT"/{pack} "$@"
'''
