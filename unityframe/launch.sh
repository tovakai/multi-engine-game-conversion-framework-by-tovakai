#!/usr/bin/env bash
# Experimental Hollow Knight Windows ARM64 player under a pinned ARM64 Proton.
set -euo pipefail
die() { printf '%s\n' "$*" >&2; exit 1; }
game_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
[ "$(uname -m)" = aarch64 ] || die 'This experiment requires an ARM64 Linux host.'
python3 "$game_dir/.hk-arm64/verify.py" "$game_dir"
proton_dir=${HK_ARM64_PROTON:-}
if [ -z "$proton_dir" ]; then
    proton_dir=$(python3 "$game_dir/.hk-arm64/find_proton.py")
fi
[ -n "$proton_dir" ] && [ -x "$proton_dir/proton" ] || die 'Set HK_ARM64_PROTON to your ARM64 Proton installation directory.'
proton_dir=$(cd -- "$proton_dir" && pwd)
proton_version=$(awk '{print $2}' "$proton_dir/version")
case "$proton_version" in
    proton-11.0-2c|proton-11.0-2c-arm64|proton-11.0-2e|proton-11.0-2e-arm64) ;;
    *) die "Unsupported Proton version: $proton_version" ;;
esac
unix_client="$proton_dir/files/lib/wine/aarch64-unix/lsteamclient.so"
[ -f "$unix_client" ] || die 'ARM64 lsteamclient unix library is missing.'
prefix="$game_dir/.hk-arm64/compatdata"
runtime="$prefix/pfx/drive_c/hk-arm64"
mkdir -p "$game_dir/.hk-arm64/logs"
export SteamAppId=367520 SteamGameId=367520 SteamOverlayGameId=367520 SteamEnv=1
export STEAM_COMPAT_APP_ID=367520
export STEAM_COMPAT_DATA_PATH="$prefix"
export STEAM_COMPAT_INSTALL_PATH="$game_dir"
export STEAM_COMPAT_CLIENT_INSTALL_PATH="${HK_ARM64_STEAM_ROOT:-$HOME/.steam/steam}"
[ -d "$STEAM_COMPAT_CLIENT_INSTALL_PATH" ] || die 'Steam client directory is missing; set HK_ARM64_STEAM_ROOT.'
if [ ! -f "$prefix/pfx/system.reg" ]; then
    mkdir -p "$prefix"
    "$proton_dir/proton" run cmd.exe /c exit > "$game_dir/.hk-arm64/logs/prefix-init.log" 2>&1
fi
mkdir -p "$runtime/aarch64-windows" "$runtime/aarch64-unix"
cp -- "$game_dir/.hk-arm64/runtime/aarch64-windows/lsteamclient_a64.dll" "$runtime/aarch64-windows/"
ln -sfn -- "$unix_client" "$runtime/aarch64-unix/lsteamclient_a64.so"
export WINEDLLPATH="$runtime"
export STEAMAPI_ARM64_CLIENT_DLL='C:\hk-arm64\aarch64-windows\lsteamclient_a64.dll'
export WINEDLLOVERRIDES='winhttp=b;d3d11=n;dxgi=n;steam_api64=n'
export STEAMAPI_ARM64_LOG=1
export WINEDEBUG="${HK_ARM64_WINEDEBUG:-+loaddll,+debugstr}"
export DXVK_LOG_PATH="$game_dir/.hk-arm64/logs"
export DISABLE_VULKAN_FDM_INJECTION_LAYER=1
cd -- "$game_dir"
printf 'Starting experimental Hollow Knight; log: %s\n' "$game_dir/.hk-arm64/logs/game.log"
exec "$proton_dir/proton" run "$game_dir/hollow_knight.exe" -force-d3d11 "$@" > "$game_dir/.hk-arm64/logs/game.log" 2>&1
