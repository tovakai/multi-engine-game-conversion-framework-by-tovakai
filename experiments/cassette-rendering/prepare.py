"""Prepare private A/B packages on Linux; never modifies the control package."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import sys

repo_root = Path(__file__).resolve().parents[2]
if (repo_root / "rpgmframe/godot_compatibility.py").is_file():
    sys.path.insert(0, str(repo_root))
try:
    from rpgmframe.godot_compatibility import merge_depth_override
except ModuleNotFoundError:
    # Standalone copies on Frame include this stdlib-only helper beside prepare.py.
    from godot_compatibility import merge_depth_override

VARIANTS = {
    "baseline": "",
    "depth-prepass": "",
    "gles2": "",
    "turnip-sysmem": "export TU_DEBUG=sysmem\n",
    "zink-sync": "export ZINK_DEBUG=sync\n",
    "zink-norp": "export ZINK_DEBUG=norp\n",
    "zink-norp-depth": "export ZINK_DEBUG=norp\n",
}


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def prepare(source, destination, saves, variants=("baseline", "depth-prepass", "gles2")):
    source = source.resolve()
    destination = destination.resolve()
    if destination.exists() or destination == source or source in destination.parents:
        raise ValueError("Use a new destination outside the control package")
    metadata = json.loads((source / "runtime.json").read_text())
    if metadata.get("engine_version") != "3.5.1" or metadata.get("pack_loading") != "main-pack":
        raise ValueError("This experiment requires the 3.5.1 main-pack runtime")
    pack = source / "game/CassetteBeasts.pck"
    if not pack.is_file() or pack.is_symlink():
        raise ValueError("Expected a regular CassetteBeasts.pck")
    # Refuse symlinks so modifying a clone cannot write into the control.
    if any(p.is_symlink() for p in source.rglob("*")):
        raise ValueError("Control contains symlinks; review before copying")
    before = {str(p.relative_to(source)): digest(p) for p in source.rglob("*") if p.is_file()}
    destination.mkdir(parents=True)
    if not variants or any(variant not in VARIANTS for variant in variants):
        raise ValueError("Unknown or empty experiment selection")
    for variant in variants:
        target = destination / variant / "payload"
        shutil.copytree(source, target)
        override = target / "game/override.cfg"
        if variant in {"depth-prepass", "zink-norp-depth"}:
            original = override.read_text(encoding="utf-8-sig") if override.exists() else ""
            override.write_text(merge_depth_override(original), encoding="utf-8", newline="\n")
        data = destination / variant / "profile/data/CassetteBeasts"
        if saves.is_dir():
            shutil.copytree(saves, data)
        else:
            data.mkdir(parents=True)
        # Common pristine starting point; each experiment writes its own saves.
        log_dir = destination / variant / "logs"
        log_dir.mkdir()
        args = " --video-driver GLES2" if variant == "gles2" else " --video-driver GLES3"
        root = shlex.quote(str(destination / variant))
        script = f'''#!/usr/bin/env bash
set -euo pipefail
ROOT={root}
export XDG_DATA_HOME="$ROOT/profile/data"
export XDG_CONFIG_HOME="$ROOT/profile/config"
export XDG_CACHE_HOME="$ROOT/profile/cache"
{VARIANTS[variant]}\
mkdir -p "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME"
LOG="$ROOT/logs/$(date -u +%Y%m%dT%H%M%S)-$$.log"
printf 'Variant: {variant}\\nUTC: %s\\n' "$(date -u --iso-8601=seconds)" | tee "$LOG"
env | sort | grep -E '^(DISPLAY|XAUTHORITY|XDG_|MESA_|GALLIUM_|ZINK_|VK_|TU_|LD_)' >> "$LOG" || true
"$ROOT/payload/launch.sh"{args} --verbose "$@" 2>&1 | tee -a "$LOG"
'''
        launcher = destination / f"launch-{variant}.sh"
        launcher.write_text(script, encoding="utf-8", newline="\n")
        launcher.chmod(0o755)
    after = {str(p.relative_to(source)): digest(p) for p in source.rglob("*") if p.is_file()}
    if before != after:
        raise RuntimeError("Control changed during preparation")
    receipt = {"control": str(source), "control_sha256": before,
               "runtime": metadata, "control_unchanged": True,
               "gameplay_verified": False, "save_load_verified": False}
    (destination / "preparation.json").write_text(json.dumps(receipt, indent=2))
    shutil.copy2(Path(__file__).with_name("probe.gd"), destination / "probe.gd")
    print(json.dumps({"destination": str(destination), "control_unchanged": True}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Control payload folder")
    parser.add_argument("destination", type=Path, help="New experiment folder")
    parser.add_argument("--saves", type=Path, default=Path.home() / ".local/share/CassetteBeasts")
    parser.add_argument("--variants", nargs="+", choices=VARIANTS,
                        default=["baseline", "depth-prepass", "gles2"])
    args = parser.parse_args()
    prepare(args.source, args.destination, args.saves, args.variants)
