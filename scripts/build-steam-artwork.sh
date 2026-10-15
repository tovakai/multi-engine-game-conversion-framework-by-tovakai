#!/usr/bin/env bash
# Run on Linux ARM64 to build the standalone Steam Frame companion.
set -euo pipefail
cd "$(dirname "$0")/.."
case "$(uname -m)" in
  aarch64|arm64) ;;
  *) echo "Build the Frame artwork companion on native Linux ARM64." >&2; exit 1 ;;
esac
PY="${ARTWORK_PYTHON:-python3}"
identity_arguments=()
if [[ -n "${ARTWORK_BUILD_IDENTITY:-}" ]]; then
  test -f "$ARTWORK_BUILD_IDENTITY"
  identity_arguments+=(--add-data "$ARTWORK_BUILD_IDENTITY:steamartwork")
fi
"$PY" -c 'import tkinter, PIL.ImageTk'
"$PY" -m PyInstaller --noconfirm --clean --windowed \
  --name steam-artwork-companion --paths . \
  --specpath build/steam-artwork --workpath build/steam-artwork/work \
  --collect-all PIL --copy-metadata Pillow "${identity_arguments[@]}" app/steam_artwork.py
cp LICENSE THIRD_PARTY_NOTICES.md docs/steam-artwork-companion.md dist/steam-artwork-companion/
SOURCE=dist/steam-artwork-companion/source
mkdir -p "$SOURCE/steamartwork" "$SOURCE/app" "$SOURCE/scripts" "$SOURCE/docs" "$SOURCE/tests"
cp steamartwork/*.py "$SOURCE/steamartwork/"
cp app/steam_artwork.py "$SOURCE/app/"
cp scripts/build-steam-artwork.sh "$SOURCE/scripts/"
cp docs/steam-artwork-companion.md "$SOURCE/docs/"
cp tests/test_steamartwork*.py "$SOURCE/tests/"
cp LICENSE THIRD_PARTY_NOTICES.md "$SOURCE/"
echo "Built: dist/steam-artwork-companion/steam-artwork-companion"
