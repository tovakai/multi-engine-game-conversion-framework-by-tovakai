#!/usr/bin/env bash
# Shared native Linux GUI converter builder; converted games still target ARM64.
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

"$PY" -m pip install -e ".[gui,build,artwork-gui]"

APP_NAME="$("$PY" -c 'from megcfbt import APP_NAME; print(APP_NAME)')"
"$PY" build/build_identity.py --platform "$TARGET"

runtime_arguments=()
for bundle in build/runtime-bundles/*.tar.gz; do
  [[ -f "$bundle" ]] || continue
  "$PY" build/verify_runtime_bundles.py "$bundle"
  runtime_arguments+=(--add-data "$bundle:rpgmframe/runtime_support")
done

"$PY" -m PyInstaller \
  --noconfirm \
  --clean \
  --distpath "dist/$TARGET" \
  --workpath "build/pyinstaller-$TARGET" \
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
  --add-data "megcfbt/controller_support:megcfbt/controller_support" \
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
  "${runtime_arguments[@]}" \
  app/main.py

RELEASE="dist/$TARGET/$APP_NAME"
if [[ "$TARGET" == linux-aarch64 ]]; then
  ARTWORK_PYTHON="$PY" ARTWORK_BUILD_IDENTITY=build/_build_info.json bash scripts/build-steam-artwork.sh
  mkdir -p "$RELEASE/Steam Artwork Companion"
  cp -a dist/steam-artwork-companion/. "$RELEASE/Steam Artwork Companion/"
fi
"$PY" build/release_metadata.py --application "$RELEASE" --platform "$TARGET"
echo "Built: $RELEASE/$APP_NAME"
