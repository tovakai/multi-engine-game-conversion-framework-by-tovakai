#!/usr/bin/env bash
# Build Multi-Engine Game Conversion Framework by Tovakai for Linux aarch64.
# For a native Steam Frame application, run this script on the Frame.
set -euo pipefail

cd "$(dirname "$0")/.."

APP_NAME="Multi-Engine Game Conversion Framework by Tovakai"
ARCH="$(uname -m)"
if [[ "$ARCH" != "aarch64" && "$ARCH" != "arm64" ]]; then
  echo "WARNING: building on $ARCH. Run this script on aarch64 for a native ARM64 application."
fi

PY=python3
if [[ -x .venv/bin/python ]]; then
  PY=.venv/bin/python
fi

"$PY" -m pip install -e ".[gui,build]"

"$PY" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "$APP_NAME" \
  --paths . \
  --hidden-import customtkinter \
  --hidden-import tkinterdnd2 \
  --collect-all customtkinter \
  --collect-all tkinterdnd2 \
  --collect-submodules renframe \
  --collect-submodules renpy_arm \
  --collect-submodules rpgmframe \
  --collect-submodules multi_engine_game_conversion_framework_by_tovakai \
  app/main.py

RELEASE="dist/linux-aarch64/$APP_NAME"
rm -rf "$RELEASE"
mkdir -p "$RELEASE"
if [[ -d "dist/$APP_NAME" ]]; then
  cp -a "dist/$APP_NAME/." "$RELEASE/"
fi

cat > "$RELEASE/README.txt" <<'EOF'
Multi-Engine Game Conversion Framework by Tovakai (Linux aarch64)
=================================================================

Run:
  ./Multi-Engine\ Game\ Conversion\ Framework\ by\ Tovakai

Drop or browse to a supported Ren'Py, RPG Maker, or Godot game and click Convert.

The application resolves the engine-specific Linux ARM64 runtime automatically.
A graphical desktop/session and Tk are required.
EOF

chmod +x "$RELEASE/$APP_NAME" 2>/dev/null || true

ARCHIVE="dist/Multi-Engine-Game-Conversion-Framework-by-Tovakai-linux-aarch64.tar.gz"
rm -f "$ARCHIVE"
tar -C "dist/linux-aarch64" -czf "$ARCHIVE" "$APP_NAME"

echo "Built:"
echo "  $RELEASE/$APP_NAME"
echo "Archive:"
echo "  $ARCHIVE"
