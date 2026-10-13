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

APP_NAME="$("$PY" -c 'from megcfbt import APP_NAME; print(APP_NAME)')"
"$PY" build/build_identity.py --platform linux-aarch64

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
  --collect-data megcfbt \
  --add-data "megcfbt/steam_library.py:megcfbt" \
  --add-data "megcfbt/steam_client.py:megcfbt" \
  --add-data "megcfbt/asset_dedup.py:megcfbt" \
  --add-data "build/_build_info.json:megcfbt" \
  --add-data "build/_build_info.json:sts2-tools" \
  --collect-data gamemakerframe \
  --collect-data rpgmframe \
  --collect-data monoframe \
  --collect-all unityframe \
  --collect-all celesteframe \
  --add-data "experiments/sts2-steamworks:sts2-tools" \
  app/main.py

RELEASE="dist/linux-aarch64/$APP_NAME"
mkdir -p "$RELEASE"
if [[ -d "dist/$APP_NAME" ]]; then
  cp -a "dist/$APP_NAME/." "$RELEASE/"
fi

chmod +x "$RELEASE/$APP_NAME" 2>/dev/null || true
"$PY" build/release_metadata.py --application "$RELEASE" --platform linux-aarch64
echo "Built: $RELEASE/$APP_NAME"
