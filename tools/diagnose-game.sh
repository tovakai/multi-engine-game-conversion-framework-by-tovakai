#!/usr/bin/env bash
# Usage: bash tools/diagnose-game.sh /path/to/launch.sh [args...]
set -uo pipefail
if (( $# < 1 )); then
  echo "Usage: $0 /path/to/launch.sh [args...]" >&2
  exit 2
fi
target=$(realpath -- "$1") || exit 2
shift
if [[ ! -f "$target" ]]; then
  echo "Launcher not found: $target" >&2
  exit 2
fi
game_dir=$(dirname -- "$target")
launcher=$(basename -- "$target")
stamp=$(date +%Y%m%d-%H%M%S)
log_root="${TOVAKAI_DIAGNOSTICS_DIR:-$HOME/tovakai-diagnostics}"
dir="$log_root/$stamp-${launcher%.*}-$$"
mkdir -p -- "$dir" || exit 2
echo "Diagnostics: $dir"
{
  printf 'Date: '; date -Is
  printf 'Launcher: %q\n' "$target"
  printf 'Args:'; printf ' %q' "$@"; printf '\n'
  printf 'Working directory: %s\n' "$game_dir"
  uname -a
  if [[ -r /etc/os-release ]]; then
    grep -E '^(NAME|VERSION|ID|PRETTY_NAME)=' /etc/os-release
  fi
  printf 'Session: %s\n' "${XDG_SESSION_TYPE:-unknown}"
  printf 'Display: %s\n' "${DISPLAY:-unset}"
  printf 'Wayland: %s\n' "${WAYLAND_DISPLAY:-unset}"
  if command -v file >/dev/null; then file -- "$target"; fi
  if command -v glxinfo >/dev/null; then timeout 8s glxinfo -B 2>&1 | head -35; fi
  if command -v vulkaninfo >/dev/null; then timeout 8s vulkaninfo --summary 2>&1 | head -50; fi
} >"$dir/system.txt" 2>&1
start=$(date +%s)
echo "Launch game and reproduce the crash, or close it normally."
(
  cd -- "$game_dir" || exit 2
  if [[ "$launcher" == *.sh ]]; then
    bash "./$launcher" "$@"
  else
    "./$launcher" "$@"
  fi
) > >(tee "$dir/stdout.log") 2> >(tee "$dir/stderr.log" >&2) &
pid=$!
wait "$pid"
code=$?
end=$(date +%s)
{
  echo "Exit code: $code"
  echo "Runtime seconds: $((end-start))"
  if (( code >= 128 )); then
    echo "Possible signal: $((code-128)) (shell convention)"
  fi
} >"$dir/result.txt"
for name in traceback.txt log.txt errors.txt; do
  if [[ -f "$game_dir/$name" ]]; then cp -- "$game_dir/$name" "$dir/game-$name"; fi
done
if command -v coredumpctl >/dev/null; then
  coredumpctl --no-pager --since "@$start" list >"$dir/coredumps.txt" 2>&1 || true
fi
echo "Exit code: $code"
echo "Logs saved to: $dir"
echo "Review logs before sharing: they may include usernames and local paths."
exit "$code"
