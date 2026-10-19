#!/usr/bin/env bash
# Build a native Linux converter; converted game runtimes still target ARM64.
set -euo pipefail
cd "$(dirname "$0")/.."

TARGET="${1:?Specify linux-aarch64 or linux-x64}"
ARCH="$(uname -m)"
case "$TARGET:$ARCH" in
  linux-aarch64:aarch64|linux-aarch64:arm64|linux-x64:x86_64) ;;
  *) echo "Unsupported native build target/host: $TARGET / $ARCH" >&2; exit 1 ;;
esac

PY=python3
if [[ -x .venv/bin/python ]]; then
  PY=.venv/bin/python
fi

"$PY" -m pip install -e ".[gui,build]"

APP_NAME="$("$PY" -c 'from megcfbt import APP_NAME; print(APP_NAME)')"

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
  --collect-data certifi \
  --copy-metadata certifi \
  --collect-data megcfbt \
  --collect-data gamemakerframe \
  --collect-data rpgmframe \
  --collect-data monoframe \
  --add-data "experiments/sts2-steamworks:sts2-tools" \
  app/main.py

RELEASE="dist/$TARGET/$APP_NAME"
mkdir -p "$RELEASE"
if [[ -d "dist/$APP_NAME" ]]; then
  cp -a "dist/$APP_NAME/." "$RELEASE/"
fi

chmod +x "$RELEASE/$APP_NAME" 2>/dev/null || true
"$PY" build/release_metadata.py --application "$RELEASE" --platform "$TARGET"
echo "Built: $RELEASE/$APP_NAME"
