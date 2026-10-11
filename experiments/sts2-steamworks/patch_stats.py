#!/usr/bin/env python3
"""Apply or restore the paired, genuine-read stats compatibility adaptation."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile


DATA = Path("/run/media/steamos/SD512/sts2-arm64-proto/data_sts2_linuxbsd_arm64")
LIBRARY_HASH = "9d354c631f01f7318bc00e8fa29842b83678f4293b52d0d5c11806edd76a7f4b"
WRAPPER_SOURCE = "7dd9a985d68666096bdf8941497cc38e911561179998119a151373d9ea928db5"
WRAPPER_TARGET = "e214b36dda06df40901cd5b0fb043045b7aa626475c0154f7ca421bb725fde14"
GAME_SOURCE = "3f41afab3a499e40ddcc017ab672a1efdf236b038ac17b6badfdd825f19f7481"
GAME_TARGET = "c27aedddd408500ab05ac3c045f41c3f224e3db19c4a6904b5581cc4f588351c"
GAME_OFFSET = 356168
GAME_BEFORE = bytes.fromhex(
    "13300200520000000000000028340f00062d012a168060050004168061050004"
    "166a80620500047ea6370004252d132614fe06800f0006732f11000a2580a637"
    "0004283011000a805f050004283111000a26287d0f000628b9770006262a"
)
GAME_AFTER = bytes.fromhex(
    "13300200520000000400001128340f00062d012a168060050004168061050004"
    "166a806205000414fe06800f0006732f11000a283011000a805f05000472874c"
    "00701200283211000a8060050004287d0f000628b977000626000000002a"
)
RECIPES = (
    ("Steamworks.NET.dll", WRAPPER_SOURCE, WRAPPER_TARGET, 360676,
     "STEAMUSERSTATS_INTERFACE_VERSION012".encode("utf-16-le"),
     "STEAMUSERSTATS_INTERFACE_VERSION013".encode("utf-16-le")),
    ("sts2.dll", GAME_SOURCE, GAME_TARGET, GAME_OFFSET, GAME_BEFORE, GAME_AFTER),
)
BACKUP_SUFFIX = ".before-stats013-v3"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def patched_bytes(data, recipe):
    name, source, target, offset, before, after = recipe
    if sha256(data) != source:
        raise ValueError("Unknown input hash for " + name)
    if len(before) != len(after) or data[offset:offset + len(before)] != before:
        raise ValueError("Unexpected patch region for " + name)
    result = data[:offset] + after + data[offset + len(before):]
    if len(result) != len(data) or sha256(result) != target:
        raise ValueError("Candidate hash differs from the verified result for " + name)
    return result


def read_regular(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected a regular, non-symlink file: " + str(path))
    return path.read_bytes()


def write_new(path, data, mode):
    with path.open("xb") as stream:
        os.fchmod(stream.fileno(), mode)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def replace_atomically(path, data, mode, expected):
    descriptor, name = tempfile.mkstemp(prefix=".sts2-stats013-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if sha256(read_regular(path)) != expected:
            raise ValueError("File changed during preparation: " + str(path))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def run(data_dir, action="inspect", output_dir=None):
    if action not in {"inspect", "generate", "install", "restore"}:
        raise ValueError("Unknown action")
    if sha256(read_regular(data_dir / "libsteam_api64.so")) != LIBRARY_HASH:
        raise ValueError("Native library hash differs from the inspected ARM64 library")
    records = []
    for recipe in RECIPES:
        name, source, target, _, _, _ = recipe
        path = data_dir / name
        original = read_regular(path)
        current = sha256(original)
        if current not in {source, target}:
            raise ValueError("Unrecognized assembly hash: " + name)
        backup = path.with_name(path.name + BACKUP_SUFFIX)
        saved = None
        if backup.is_symlink():
            raise ValueError("Refusing symbolic-link backup: " + str(backup))
        if backup.exists():
            saved = read_regular(backup)
            if sha256(saved) != source:
                raise ValueError("Existing backup hash differs: " + str(backup))
        if action in {"install", "restore"} and current == target and saved is None:
            raise ValueError("Patched assembly has no verified backup: " + name)
        desired = source if action == "restore" else target
        candidate = original if current == desired else (
            saved if action == "restore" else patched_bytes(original, recipe)
        )
        records.append({
            "name": name, "path": path, "backup": backup,
            "original": original, "candidate": candidate,
            "current": current, "desired": desired,
            "mode": stat.S_IMODE(path.stat().st_mode), "saved": saved,
        })
    report = {
        "recipe": "stats013-v3", "action": action,
        "native_library_sha256": LIBRARY_HASH,
        "files": [{"assembly": str(r["path"]), "sha256_before": r["current"],
                   "sha256_candidate": r["desired"],
                   "changed_byte_count": sum(a != b for a, b in zip(r["original"], r["candidate"]))}
                  for r in records],
    }
    if action == "inspect":
        return {**report, "status": "inspected-no-writes"}
    if action == "generate":
        if output_dir is None or not output_dir.is_dir():
            raise ValueError("Generation requires an existing output directory")
        outputs = [output_dir / r["name"] for r in records]
        if any(p.exists() or p.is_symlink() for p in outputs):
            raise ValueError("An output already exists; refusing to overwrite")
        for r, path in zip(records, outputs):
            write_new(path, r["candidate"], r["mode"])
        return {**report, "status": "generated", "output_directory": str(output_dir)}
    # Preflight both assemblies and backups before replacing either file.
    for r in records:
        if r["current"] != r["desired"] and r["saved"] is None:
            write_new(r["backup"], r["original"], r["mode"])
    changed = []
    try:
        # Install the matching native interface contract first; restore game first.
        for r in (reversed(records) if action == "restore" else records):
            if r["current"] != r["desired"]:
                replace_atomically(r["path"], r["candidate"], r["mode"], r["current"])
                changed.append(r)
        if any(sha256(read_regular(r["path"])) != r["desired"] for r in records):
            raise ValueError("Post-install pair hash verification failed")
    except (OSError, ValueError) as error:
        rollback_errors = []
        for r in reversed(changed):
            try:
                replace_atomically(r["path"], r["original"], r["mode"], r["desired"])
            except (OSError, ValueError) as rollback_error:
                rollback_errors.append(str(rollback_error))
        raise ValueError(str(error) + "; rollback errors: " + json.dumps(rollback_errors)) from error
    return {**report, "status": "restored" if action == "restore" else "installed",
            "backups": [str(r["backup"]) for r in records]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--action", choices=("inspect", "generate", "install", "restore"), default="inspect")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        result = run(args.data, args.action, args.output_dir)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, indent=2))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
