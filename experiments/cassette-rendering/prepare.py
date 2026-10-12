"""Prepare private A/B packages on Linux; never modifies the control package."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def merge_depth_override(text):
    """Keep Godot Variant syntax/comments; change only two rendering keys."""
    lines = text.splitlines(keepends=True)
    if sum(bool(re.match(r"^\s*\[rendering\]\s*(?:;.*)?$", line.strip())) for line in lines) > 1:
        raise ValueError("Duplicate rendering sections; manual review required")
    section = None
    start = None
    end = len(lines)
    for i, line in enumerate(lines):
        match = re.match(r"^\s*\[([^]]+)\]\s*(?:;.*)?$", line.strip())
        if match:
            if section == "rendering":
                end = i
                break
            section = match.group(1)
            if section == "rendering":
                start = i
    values = {
        "quality/depth_prepass/disable_for_vendors": '""',
        "quality/depth_prepass/enable": "true",
    }
    if start is None:
        return text.rstrip("\r\n") + '\n\n[rendering]\n' + "".join(
            f"{key}={value}\n" for key, value in values.items())
    seen = set()
    for i in range(start + 1, end):
        key = lines[i].split("=", 1)[0].strip()
        if key in values:
            if key in seen:
                raise ValueError("Duplicate depth setting; manual review required")
            lines[i] = f"{key}={values[key]}\n"
            seen.add(key)
    if end and not lines[end - 1].endswith("\n"):
        lines[end - 1] += "\n"
    lines[end:end] = [f"{key}={value}\n" for key, value in values.items() if key not in seen]
    return "".join(lines)


def prepare(source, destination, saves):
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
    for variant in ("baseline", "depth-prepass", "gles2"):
        target = destination / variant / "payload"
        shutil.copytree(source, target)
        override = target / "game/override.cfg"
        if variant == "depth-prepass":
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
mkdir -p "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME"
LOG="$ROOT/logs/$(date -u +%Y%m%dT%H%M%S)-$$.log"
printf 'Variant: {variant}\\nUTC: %s\\n' "$(date -u --iso-8601=seconds)" | tee "$LOG"
env | sort | grep -E '^(DISPLAY|XAUTHORITY|XDG_|MESA_|GALLIUM_|VK_|TU_|LD_)' >> "$LOG" || true
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
    args = parser.parse_args()
    prepare(args.source, args.destination, args.saves)
