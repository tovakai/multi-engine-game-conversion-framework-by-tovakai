'''Automatic native ARM64 compatibility runtime for custom Godot 3.7 exports.

The first recipe is intentionally narrow. It reproduces the compatibility stack
validated on Steam Frame hardware for a Godot 3.7 development/custom export
with built-in GodotSteam:

- Godot 3.7-dev1 (a117d512...)
- Godot 3.x CanvasItem cast fix from upstream PR #123099
- GodotSteam 3.30 classic C++ Steam API surface
- Steamworks 1.62 headers sourced from ValveSoftware/Proton and normalized back
  to the SDK's anonymous-union/header semantics
- the Steam Frame's installed native ARM64 libsteam_api.so

The original Windows game can report a newer GodotSteam version. The point of
this recipe is game-facing API compatibility while using the classic Steam API
surface exported by the Frame's ARM64 Steam library.
'''

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path

from rpgmframe.elf import read_elf_architecture

ProgressCallback = Callable[[str], None]

RECIPE_ID = "godot-3.7-dev1-godotsteam-3.30-steamworks-1.62-frame-arm64-v1"
GODOT_REF = "a117d512b00f1646db174e703e7e888519b64608"
GODOTSTEAM_REF = "f73d138b56fe971a940dd0498e8b9d0fc8fdcffd"
PROTON_REF = "5b89db940e0ebe3a137a6009a3589232fe084c09"
DEFAULT_STEAM_API = Path("/opt/steamvr/bin/linuxarm64/libsteam_api.so")
DEFAULT_DISTROBOX = "tovakai-godot-build"

_REQUIRED_COMMANDS = ("git", "python3", "scons", "pkg-config", "gcc", "g++")
_REQUIRED_PKG_CONFIG = (
    "x11",
    "xcursor",
    "xinerama",
    "xext",
    "xrandr",
    "xrender",
    "xi",
    "gl",
)


class CustomGodotRuntimeError(RuntimeError):
    '''Raised when the automatic custom Godot compatibility runtime cannot be built.'''


def automatic_recipe_for(
    engine_version: str | None,
    *,
    custom_build: bool,
    godotsteam: bool,
) -> str | None:
    '''Return the supported automatic compatibility recipe, if any.'''
    if engine_version == "3.7.0" and custom_build and godotsteam:
        return RECIPE_ID
    return None


def _steam_api_path() -> Path:
    configured = os.environ.get("TOVAKAI_STEAM_API_ARM64")
    return Path(configured).expanduser().resolve() if configured else DEFAULT_STEAM_API


def _is_linux_arm64() -> bool:
    return (
        platform.system().casefold() == "linux"
        and platform.machine().casefold() in {"aarch64", "arm64"}
    )


def _native_toolchain_available() -> bool:
    if not all(shutil.which(command) for command in _REQUIRED_COMMANDS):
        return False
    pkg_config = shutil.which("pkg-config")
    if not pkg_config:
        return False
    check = subprocess.run(
        [pkg_config, "--exists", *_REQUIRED_PKG_CONFIG],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return check.returncode == 0


def _distrobox_command() -> str | None:
    return shutil.which("distrobox")


def _distrobox_toolchain_available(name: str) -> bool:
    distrobox = _distrobox_command()
    if not distrobox:
        return False

    command_checks = " && ".join(
        f"command -v {command} >/dev/null" for command in _REQUIRED_COMMANDS
    )
    package_checks = " ".join(_REQUIRED_PKG_CONFIG)
    probe = f"{command_checks} && pkg-config --exists {package_checks}"
    try:
        result = subprocess.run(
            [distrobox, "enter", name, "--", "bash", "-lc", probe],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def host_can_build_automatic_runtime() -> bool:
    '''Cheap host capability check used by the umbrella UI/router.'''
    if not _is_linux_arm64():
        return False

    steam_api = _steam_api_path()
    if not steam_api.is_file() or read_elf_architecture(steam_api) != "aarch64":
        return False

    # Do not enter a container during ordinary inspection. The presence of
    # distrobox is enough to expose the route; ensure_runtime performs the
    # authoritative toolchain probe and reports a useful error.
    return _native_toolchain_available() or _distrobox_command() is not None


_WORKER_SCRIPT = r'''#!/usr/bin/env bash
set -euo pipefail

: "${WORK_DIR:?}"
: "${OUTPUT_DIR:?}"
: "${STEAM_API:?}"
: "${GODOT_REF:?}"
: "${GODOTSTEAM_REF:?}"
: "${PROTON_REF:?}"
: "${RECIPE_ID:?}"

case "$(uname -m)" in
    aarch64|arm64) ;;
    *)
        echo "ERROR: custom Godot runtime recipe requires native Linux ARM64." >&2
        exit 2
        ;;
esac

missing=0
for cmd in git python3 scons pkg-config gcc g++; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "ERROR: missing build command: $cmd" >&2
        missing=1
    fi
done
for pkg in x11 xcursor xinerama xext xrandr xrender xi gl; do
    if ! pkg-config --exists "$pkg"; then
        echo "ERROR: missing pkg-config development package: $pkg" >&2
        missing=1
    fi
done
if [[ "$missing" -ne 0 ]]; then
    exit 2
fi

mkdir -p "$WORK_DIR"
GODOT_DIR="$WORK_DIR/godot"
GODOTSTEAM_DIR="$WORK_DIR/godotsteam"
PROTON_DIR="$WORK_DIR/proton"

if [[ ! -d "$GODOT_DIR/.git" ]]; then
    echo "==> Fetching Godot source"
    rm -rf "$GODOT_DIR"
    git init -q "$GODOT_DIR"
    git -C "$GODOT_DIR" remote add origin https://github.com/godotengine/godot.git
fi
echo "==> Checking out Godot 3.7-dev1 base"
git -C "$GODOT_DIR" fetch -q --depth 1 origin "$GODOT_REF"
git -C "$GODOT_DIR" reset -q --hard FETCH_HEAD
git -C "$GODOT_DIR" clean -qfdx

echo "==> Applying Godot 3.x CanvasItem cast fix"
PATCH_FILE="$WORK_DIR/canvas-item-123099.patch"
cat > "$PATCH_FILE" <<'PATCH'
diff --git a/scene/2d/canvas_item.h b/scene/2d/canvas_item.h
--- a/scene/2d/canvas_item.h
+++ b/scene/2d/canvas_item.h
@@ -48,8 +48,6 @@ class CanvasItemMaterial : public Material {
 	GDCLASS(CanvasItemMaterial, Material);
 
 public:
-	static constexpr AncestralClass static_ancestral_class = AncestralClass::CANVAS_ITEM;
-
 	enum BlendMode {
 		BLEND_MODE_MIX,
 		BLEND_MODE_ADD,
@@ -167,6 +165,8 @@ class CanvasItem : public Node {
 	friend class CanvasLayer;
 
public:
+	static constexpr AncestralClass static_ancestral_class = AncestralClass::CANVAS_ITEM;
+
 	enum BlendMode {
 
 		BLEND_MODE_MIX, //default
PATCH
git -C "$GODOT_DIR" apply "$PATCH_FILE"

if [[ ! -d "$GODOTSTEAM_DIR/.git" ]]; then
    echo "==> Fetching GodotSteam source"
    rm -rf "$GODOTSTEAM_DIR"
    git init -q "$GODOTSTEAM_DIR"
    git -C "$GODOTSTEAM_DIR" remote add origin https://codeberg.org/godotsteam/godotsteam.git
fi
echo "==> Checking out GodotSteam 3.30"
git -C "$GODOTSTEAM_DIR" fetch -q --depth 1 origin "$GODOTSTEAM_REF"
git -C "$GODOTSTEAM_DIR" reset -q --hard FETCH_HEAD
git -C "$GODOTSTEAM_DIR" clean -qfdx

if [[ ! -d "$PROTON_DIR/.git" ]]; then
    echo "==> Fetching Valve Proton Steamworks compatibility headers"
    rm -rf "$PROTON_DIR"
    git clone -q --filter=blob:none --no-checkout         https://github.com/ValveSoftware/Proton.git "$PROTON_DIR"
fi
git -C "$PROTON_DIR" sparse-checkout init --cone >/dev/null 2>&1 || true
git -C "$PROTON_DIR" sparse-checkout set lsteamclient/steamworks_sdk_162
git -C "$PROTON_DIR" fetch -q --depth 1 origin "$PROTON_REF"
git -C "$PROTON_DIR" checkout -q --detach FETCH_HEAD

MODULE="$GODOT_DIR/modules/godotsteam"
rm -rf "$MODULE"
mkdir -p "$MODULE"
cp -a "$GODOTSTEAM_DIR/." "$MODULE/"
rm -rf "$MODULE/.git"

echo "==> Staging Steamworks 1.62 headers"
rm -rf "$MODULE/sdk"
mkdir -p "$MODULE/sdk/public/steam"
cp -a "$PROTON_DIR/lsteamclient/steamworks_sdk_162/." "$MODULE/sdk/public/steam/"

echo "==> Normalizing Proton's generated headers to native SDK C++ semantics"
MODULE="$MODULE" python3 - <<'PY'
import os
from pathlib import Path

base = Path(os.environ["MODULE"]) / "sdk/public/steam"

def replace_exact(path: Path, old: str, new: str, expected: int) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != expected:
        raise SystemExit(
            f"Expected {expected} occurrence(s) of {old!r} in {path.name}, found {count}"
        )
    path.write_text(text.replace(old, new))

replace_exact(base / "isteamremoteplay.h", "} data;", "};", 1)
replace_exact(base / "isteaminput.h", "} x;", "};", 1)
replace_exact(base / "steamnetworkingtypes.h", "} data;", "};", 2)
replace_exact(
    base / "steamnetworkingtypes.h",
    "#if 0\ninline void SteamNetworkingIPAddr::Clear()",
    "#if 1\ninline void SteamNetworkingIPAddr::Clear()",
    1,
)
PY

echo "==> Wiring native ARM64 Steam API"
MODULE="$MODULE" python3 - <<'PY'
import os
from pathlib import Path

p = Path(os.environ["MODULE"]) / "SCsub"
text = p.read_text()
old = "sdk/redistributable_bin/linux64"
if old not in text:
    raise SystemExit("Expected GodotSteam linux64 library path was not found in SCsub")
p.write_text(text.replace(old, "sdk/redistributable_bin/linuxarm64"))
PY

mkdir -p "$MODULE/sdk/redistributable_bin/linuxarm64"
cp -a "$STEAM_API" "$MODULE/sdk/redistributable_bin/linuxarm64/libsteam_api.so"

if [[ -z "${JOBS:-}" ]]; then
    if command -v nproc >/dev/null 2>&1; then
        JOBS="$(nproc)"
    else
        JOBS=4
    fi
fi

echo "==> Building Godot 3.7-dev1 ARM64 + GodotSteam 3.30"
(
    cd "$GODOT_DIR"
    scons -j"$JOBS"         platform=x11         target=release         tools=no         arch=arm64         lto=none
)

BINARY="$GODOT_DIR/bin/godot.x11.opt.arm64"
if [[ ! -f "$BINARY" ]]; then
    BINARY="$(find "$GODOT_DIR/bin" -maxdepth 1 -type f -name 'godot.x11.opt*arm64*' | sort | head -n 1)"
fi
if [[ -z "$BINARY" || ! -f "$BINARY" ]]; then
    echo "ERROR: Godot build completed but no ARM64 release binary was found." >&2
    exit 1
fi

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"
cp -a "$BINARY" "$OUTPUT_DIR/godot.arm64"
chmod +x "$OUTPUT_DIR/godot.arm64"
cp -a "$STEAM_API" "$OUTPUT_DIR/libsteam_api.so"

GODOT_SOURCE_SHA="$(git -C "$GODOT_DIR" rev-parse HEAD)"
GODOTSTEAM_SOURCE_SHA="$(git -C "$GODOTSTEAM_DIR" rev-parse HEAD)"
PROTON_SOURCE_SHA="$(git -C "$PROTON_DIR" rev-parse HEAD)"
export GODOT_SOURCE_SHA GODOTSTEAM_SOURCE_SHA PROTON_SOURCE_SHA

OUTPUT_DIR="$OUTPUT_DIR" python3 - <<'PY'
import json
import os
import subprocess
from pathlib import Path

out = Path(os.environ["OUTPUT_DIR"])
env = dict(os.environ)
env["LD_LIBRARY_PATH"] = str(out) + (
    ":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else ""
)
try:
    version = subprocess.run(
        [str(out / "godot.arm64"), "--version"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=20,
        check=False,
    ).stdout.splitlines()[0]
except (OSError, subprocess.TimeoutExpired, IndexError):
    version = ""

manifest = {
    "kind": "godot-custom",
    "recipe_id": os.environ["RECIPE_ID"],
    "architecture": "aarch64",
    "godot_ref": os.environ["GODOT_SOURCE_SHA"],
    "godot_version_output": version,
    "godot_patch": "upstream Godot PR #123099 CanvasItem ancestral-class fix",
    "godotsteam_ref": os.environ["GODOTSTEAM_SOURCE_SHA"],
    "godotsteam_compatibility_version": "3.30",
    "steamworks_headers": (
        "1.62 via ValveSoftware/Proton, normalized to native C++ header semantics"
    ),
    "proton_ref": os.environ["PROTON_SOURCE_SHA"],
    "steamworks_arm64_runtime": "Steam Frame installed libsteam_api.so",
    "notes": (
        "Compatibility runtime for Godot 3.7 custom/development exports with "
        "built-in GodotSteam. It intentionally substitutes GodotSteam 3.30's "
        "classic interface layer for newer flat-API builds."
    ),
}
(out / "runtime.json").write_text(json.dumps(manifest, indent=2) + "\n")
PY

echo "==> Runtime bundle complete: $OUTPUT_DIR"
'''


class CustomGodotRuntimeManager:
    '''Build and cache the Steam Frame Godot 3.7/GodotSteam compatibility runtime.'''

    def __init__(
        self,
        cache_dir: Path | str | None = None,
        *,
        work_dir: Path | str | None = None,
        steam_api: Path | str | None = None,
        distrobox_name: str | None = None,
    ) -> None:
        configured = os.environ.get("RPGMFRAME_CACHE_DIR")
        if cache_dir is not None:
            root = Path(cache_dir)
        elif configured:
            root = Path(configured)
        else:
            root = Path.home() / ".cache" / "rpgmframe"

        self.cache_dir = root.expanduser().resolve() / "runtimes" / "godot-custom"
        if work_dir is not None:
            self.work_dir = Path(work_dir).expanduser().resolve()
        else:
            self.work_dir = self.cache_dir / ".work" / RECIPE_ID
        self.steam_api = (
            Path(steam_api).expanduser().resolve()
            if steam_api is not None
            else _steam_api_path()
        )
        self.distrobox_name = (
            distrobox_name
            or os.environ.get("TOVAKAI_GODOT_DISTROBOX")
            or DEFAULT_DISTROBOX
        )

    def runtime_path(self) -> Path:
        return self.cache_dir / RECIPE_ID

    def _validate_runtime(self, path: Path) -> bool:
        binary = path / "godot.arm64"
        steam = path / "libsteam_api.so"
        manifest = path / "runtime.json"
        if (
            not binary.is_file()
            or read_elf_architecture(binary) != "aarch64"
            or not steam.is_file()
            or read_elf_architecture(steam) != "aarch64"
            or not manifest.is_file()
        ):
            return False
        try:
            value = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return False
        return isinstance(value, dict) and value.get("recipe_id") == RECIPE_ID

    def _build_command(self) -> tuple[list[str], str]:
        worker = self.work_dir / "build-runtime.sh"
        if _distrobox_toolchain_available(self.distrobox_name):
            distrobox = _distrobox_command()
            assert distrobox is not None
            return (
                [
                    distrobox,
                    "enter",
                    self.distrobox_name,
                    "--",
                    "bash",
                    str(worker),
                ],
                f"distrobox {self.distrobox_name}",
            )

        if _native_toolchain_available():
            return (["bash", str(worker)], "native ARM64 host")

        raise CustomGodotRuntimeError(
            "Automatic GodotSteam runtime build needs either the "
            f"{self.distrobox_name!r} distrobox with the Godot/X11 build "
            "toolchain, or the same toolchain installed on the native ARM64 host. "
            "A manual custom runtime override is still supported."
        )

    def ensure_runtime(
        self,
        *,
        progress: ProgressCallback | None = None,
    ) -> Path:
        final = self.runtime_path()
        if self._validate_runtime(final):
            if progress:
                progress(f"Using cached custom Godot compatibility runtime: {final}")
            return final

        if not _is_linux_arm64():
            raise CustomGodotRuntimeError(
                "Automatic custom Godot runtime building is currently supported "
                "only on native Linux ARM64."
            )
        if not self.steam_api.is_file():
            raise CustomGodotRuntimeError(
                f"Native ARM64 Steam API was not found: {self.steam_api}. "
                "Set TOVAKAI_STEAM_API_ARM64 to override the path."
            )
        if read_elf_architecture(self.steam_api) != "aarch64":
            raise CustomGodotRuntimeError(
                f"Steam API runtime is not AArch64: {self.steam_api}"
            )

        self.work_dir.mkdir(parents=True, exist_ok=True)
        worker = self.work_dir / "build-runtime.sh"
        worker.write_text(_WORKER_SCRIPT, encoding="utf-8", newline="\n")
        worker.chmod(worker.stat().st_mode | 0o755)

        final.parent.mkdir(parents=True, exist_ok=True)
        temporary = final.parent / f".{RECIPE_ID}.tmp-{uuid.uuid4().hex[:8]}"
        shutil.rmtree(temporary, ignore_errors=True)

        command, runner = self._build_command()
        if progress:
            progress(
                "Building automatic Godot 3.7/GodotSteam compatibility runtime "
                f"using {runner}"
            )

        env = dict(os.environ)
        env.update(
            {
                "WORK_DIR": str(self.work_dir / "sources"),
                "OUTPUT_DIR": str(temporary),
                "STEAM_API": str(self.steam_api),
                "GODOT_REF": GODOT_REF,
                "GODOTSTEAM_REF": GODOTSTEAM_REF,
                "PROTON_REF": PROTON_REF,
                "RECIPE_ID": RECIPE_ID,
            }
        )

        try:
            process = subprocess.Popen(
                command,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            shutil.rmtree(temporary, ignore_errors=True)
            raise CustomGodotRuntimeError(
                f"Could not start automatic Godot runtime build: {exc}"
            ) from exc

        assert process.stdout is not None
        for line in process.stdout:
            message = line.rstrip()
            if message and progress:
                progress(message)
        return_code = process.wait()

        if return_code != 0:
            shutil.rmtree(temporary, ignore_errors=True)
            raise CustomGodotRuntimeError(
                "Automatic Godot compatibility runtime build failed with exit code "
                f"{return_code}."
            )

        if not self._validate_runtime(temporary):
            shutil.rmtree(temporary, ignore_errors=True)
            raise CustomGodotRuntimeError(
                "Automatic build completed but produced an invalid runtime bundle."
            )

        if final.exists():
            shutil.rmtree(final, ignore_errors=True)
        temporary.rename(final)

        if progress:
            progress(f"Cached custom Godot compatibility runtime: {final}")
        return final
