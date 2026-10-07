#!/usr/bin/env bash
# Build Multi-Engine Game Conversion Framework by Tovakai for Linux aarch64.
set -euo pipefail
cd "$(dirname "$0")/.."

ARCH="$(uname -m)"
if [[ "$ARCH" != "aarch64" && "$ARCH" != "arm64" ]]; then
  echo "WARNING: building on $ARCH; run on aarch64 for a native ARM64 binary."
fi

PY=python3
if [[ -x .venv/bin/python ]]; then
  PY=.venv/bin/python
fi

"$PY" -m pip install -e ".[gui,build]"

APP_NAME="Multi-Engine Game Conversion Framework by Tovakai"

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
  app/main.py

RELEASE="dist/linux-aarch64/$APP_NAME"
mkdir -p "$RELEASE"
if [[ -d "dist/$APP_NAME" ]]; then
  cp -a "dist/$APP_NAME/." "$RELEASE/"
fi

cat > "$RELEASE/README.txt" <<'EOF'
Multi-Engine Game Conversion Framework by Tovakai
=================================================

Run:
./Multi-Engine\ Game\ Conversion\ Framework\ by\ Tovakai

The application detects Ren'Py, RPG Maker, and Godot builds and routes each game
to its corresponding Linux ARM64 conversion backend.
EOF

chmod +x "$RELEASE/$APP_NAME" 2>/dev/null || true
echo "Built: $RELEASE/$APP_NAME"
