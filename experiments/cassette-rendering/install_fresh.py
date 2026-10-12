"""Unpack a private GUI-produced ZIP unchanged and isolate hardware-test saves."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import zipfile


def install(archive_path, destination, saves):
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Use a new hardware-test destination")
    destination.mkdir(parents=True)
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        for info in archive.infolist():
            target = (destination / info.filename).resolve()
            if destination not in target.parents and target != destination:
                raise ValueError("ZIP path escapes destination")
            if info.external_attr >> 16 & 0o170000 == 0o120000:
                raise ValueError("Unexpected ZIP symlink")
        archive.extractall(destination)
        for info in archive.infolist():
            target = destination / info.filename
            if target.is_file() and info.external_attr >> 16 & 0o777:
                target.chmod(info.external_attr >> 16 & 0o777)
    packages = [p.parent for p in destination.glob("*/payload/godot-compatibility.json")]
    assert len(packages) == 1, packages
    payload = packages[0]
    profile = json.loads((payload / "godot-compatibility.json").read_text())
    assert profile["profile_id"] == "cassette-beasts-gles3-zink-norp-depth-v1"
    assert profile["override_path"] == "game/override.cfg"
    override = (payload / "game/override.cfg").read_text()
    assert 'quality/depth_prepass/enable=true' in override
    assert 'quality/depth_prepass/disable_for_vendors=""' in override
    launcher = (payload / "launch.sh").read_text()
    assert 'export ZINK_DEBUG="${ZINK_DEBUG:+${ZINK_DEBUG},}norp"' in launcher
    assert '--video-driver GLES3' in launcher
    with (payload / "godot.arm64").open("rb") as stream:
        header = stream.read(64)
    assert header[:4] == b"\x7fELF" and int.from_bytes(header[18:20], "little") == 183
    data = destination / "profile/data/CassetteBeasts"
    if saves.is_dir():
        shutil.copytree(saves, data)
    else:
        data.mkdir(parents=True)
    wrapper = f'''#!/usr/bin/env bash
set -euo pipefail
export DISPLAY=:0
export XDG_DATA_HOME={shlex.quote(str(destination / "profile/data"))}
export XDG_CONFIG_HOME={shlex.quote(str(destination / "profile/config"))}
export XDG_CACHE_HOME={shlex.quote(str(destination / "profile/cache"))}
mkdir -p "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME"
{shlex.quote(str(payload.parent / "launch.sh"))} --print-fps "$@" 2>&1 | tee {shlex.quote(str(destination / "gameplay.log"))}
'''
    diagnostic = destination / "launch-fresh.sh"
    diagnostic.write_text(wrapper, newline="\n")
    diagnostic.chmod(0o755)
    h = hashlib.sha256()
    with archive_path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    summary = {"zip_sha256": h.hexdigest(), "payload": str(payload), "profile": profile,
               "native_architecture": "aarch64", "package_content_modified": False,
               "save_profile_isolated": True, "gameplay_verified": False}
    (destination / "installation.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--saves", type=Path, default=Path.home() / ".local/share/CassetteBeasts")
    args = parser.parse_args()
    install(args.archive, args.destination, args.saves)
