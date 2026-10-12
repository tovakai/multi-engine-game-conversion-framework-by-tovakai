"""Verify a fresh frozen-GUI conversion and private ZIP without touching input."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import zipfile


def fingerprints(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        h = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(block)
        result[path.relative_to(root).as_posix()] = [h.hexdigest(), path.stat().st_mtime_ns]
    return result


def verify(exe, source, work):
    if work.exists():
        raise ValueError("Use a new acceptance directory")
    work.mkdir(parents=True)
    output = work / "packages"
    output.mkdir()
    before = fingerprints(source)
    receipt = work / "gui-receipt.json"
    env = os.environ.copy()
    env["RPGMFRAME_CACHE_DIR"] = str(work / "runtime-cache")
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    with (work / "process.log").open("w") as log:
        process = subprocess.Popen([str(exe), "--verify-gui-conversion", str(source),
                                    "--output-dir", str(output), "--receipt", str(receipt)],
                                   env=env, startupinfo=startup, stdout=log, stderr=log)
        deadline = time.monotonic() + 1000
        previous = ""
        while process.poll() is None:
            if time.monotonic() > deadline:
                process.terminate()
                raise RuntimeError("Frozen GUI conversion timed out")
            try:
                data = json.loads(receipt.read_text())
                status = data["state"] + " " + data.get("log", "").splitlines()[-1]
                if status != previous:
                    print(status, flush=True)
                    previous = status
            except (OSError, ValueError, IndexError):
                pass
            time.sleep(2)
    data = json.loads(receipt.read_text())
    assert process.returncode == 0 and data["state"] == "complete", data
    assert data["frozen"] and data["convert_enabled"] and not data["runtime_override"]
    assert data["download_progress"], "Clean-cache download was not observed"
    assert fingerprints(source) == before, "Original game hashes or mtimes changed"
    package = Path(data["package"])
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        def read(suffix):
            return archive.read(next(name for name in names if name.endswith(suffix)))
        config = read("/payload/game/override.cfg").decode("utf-8")
        assert 'quality/depth_prepass/enable=true' in config
        assert 'quality/depth_prepass/disable_for_vendors=""' in config
        assert not any(name.endswith("/payload/override.cfg") for name in names)
        launcher = read("/payload/launch.sh").decode("utf-8")
        assert 'export ZINK_DEBUG="${ZINK_DEBUG:+${ZINK_DEBUG},}norp"' in launcher
        assert '--video-driver GLES3' in launcher
        assert '--main-pack "$ROOT"/game/CassetteBeasts.pck' in launcher
        profile = json.loads(read("/payload/godot-compatibility.json"))
        assert profile["profile_id"] == "cassette-beasts-gles3-zink-norp-depth-v1"
        engine = read("/payload/godot.arm64")
        assert engine[:4] == b"\x7fELF" and int.from_bytes(engine[18:20], "little") == 183
        for suffix in ("/payload/runtime.json", "/payload/LICENSE-Godot.txt",
                       "/payload/libframe_steam_env.so", "/install-to-steam.sh"):
            read(suffix)
        assert not any(name.endswith("/libsteam_api.so") for name in names)
    summary = {"state": data["state"], "frozen": data["frozen"],
               "convert_enabled": data["convert_enabled"], "runtime_override": data["runtime_override"],
               "clean_cache_download": True, "source_hashes_and_mtimes_unchanged": True,
               "zip_crc_passed": True, "profile": profile, "native_runtime_architecture": "aarch64",
               "package": str(package), "elapsed_seconds": data.get("elapsed_seconds")}
    (work / "acceptance.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exe", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    verify(args.exe.resolve(), args.source.resolve(), args.work.resolve())
