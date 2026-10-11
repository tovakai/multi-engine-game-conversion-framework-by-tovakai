#!/usr/bin/env python3
"""Apply isolated, hash-guarded Steamworks.NET compatibility recipes."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile


DEFAULT_ASSEMBLY = Path("/run/media/steamos/SD512/sts2-arm64-proto/data_sts2_linuxbsd_arm64/Steamworks.NET.dll")
ORIGINAL_SHA256 = "474a2af1328c2a2b32bedf8376ed46a50958423313856659ac05bee677d8fdd3"
PATCHED_SHA256 = "808393ad362ef694e506d6b722bf4357014b1f2cdb19256d0f467c89b9ac02de"
HTTP_PATCHED_SHA256 = "c85f06c0aa27c8e498e4d4bd8c73ed818f810d2ba7e1565bb3c415230eb269af"
CLIENT_PATCHED_SHA256 = "7dd9a985d68666096bdf8941497cc38e911561179998119a151373d9ea928db5"
# File offsets resolved from the uploaded assembly's parsed MethodDef bodies.
PATCHES = (
    (2777, bytes.fromhex("44050006"), "SteamClient.GetISteamGameSearch"),
    (3169, bytes.fromhex("4c050006"), "SteamClient.GetISteamMusicRemote"),
)
GENERIC_TOKEN = bytes.fromhex("3d050006")
CLIENT_STRING_OFFSET = 360466
CLIENT_STRING = "SteamClient021".encode("utf-16-le")
RECIPES = {
    "generic-v1": (ORIGINAL_SHA256, PATCHED_SHA256, PATCHES),
    "http-generic-v2": (
        PATCHED_SHA256, HTTP_PATCHED_SHA256,
        ((2897, bytes.fromhex("48050006"), "SteamClient.GetISteamHTTP"),),
    ),
    "client023-v2": (
        PATCHED_SHA256, CLIENT_PATCHED_SHA256,
        ((CLIENT_STRING_OFFSET, CLIENT_STRING, "Shared context client factory version"),),
    ),
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def patched_bytes(original, recipe="generic-v1"):
    source_hash, target_hash, patches = RECIPES[recipe]
    if sha256(original) != source_hash:
        raise ValueError("Assembly hash differs from this recipe's verified input; refusing to patch")
    patched = bytearray(original)
    for offset, expected, name in patches:
        if recipe == "client023-v2":
            if original[offset - 1] != 29 or original[offset:offset + 28] != expected or original[offset + 28] != 0:
                raise ValueError("Unexpected managed user-string entry for " + name)
            patched[offset:offset + 28] = "SteamClient023".encode("utf-16-le")
        else:
            if original[offset - 1] != 0x28 or original[offset:offset + 4] != expected:
                raise ValueError("Unexpected IL call operand for " + name)
            patched[offset:offset + 4] = GENERIC_TOKEN
    result = bytes(patched)
    if sha256(result) != target_hash:
        raise ValueError("Patched assembly hash does not match the verified result")
    return result


def write_new(path, data, mode):
    with path.open("xb") as stream:
        os.fchmod(stream.fileno(), mode)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def replace_atomically(path, data, mode, expected_current):
    descriptor, temporary = tempfile.mkstemp(prefix=".steamworks-generic-v1-", dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_symlink() or sha256(path.read_bytes()) != expected_current:
            raise ValueError("Assembly changed during preparation; refusing to replace it")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def run(path, output=None, install=False, restore=False, recipe="generic-v1"):
    source_hash, target_hash, patches = RECIPES[recipe]
    if path.is_symlink():
        raise ValueError("Refusing to replace a symbolic-link assembly")
    original = path.read_bytes()
    current_hash = sha256(original)
    mode = stat.S_IMODE(path.stat().st_mode)
    backup = path.with_name(path.name + ".before-" + recipe)
    report = {"assembly": str(path), "sha256_before": current_hash, "recipe": recipe}
    if restore:
        if current_hash == source_hash:
            status = "already-original" if recipe == "generic-v1" else "already-source"
            return {**report, "status": status, "sha256_after": current_hash}
        if current_hash != target_hash:
            raise ValueError("Current assembly is neither the original nor this patch; refusing to restore")
        if backup.is_symlink():
            raise ValueError("Refusing to restore from a symbolic-link backup")
        saved = backup.read_bytes()
        if sha256(saved) != source_hash:
            raise ValueError("Backup hash does not match this recipe's verified input")
        replace_atomically(path, saved, mode, current_hash)
        return {**report, "status": "restored", "sha256_after": source_hash, "backup": str(backup)}
    if install and current_hash == target_hash:
        if backup.is_symlink() or sha256(backup.read_bytes()) != source_hash:
            raise ValueError("Patch is already present but its original backup is missing or invalid")
        return {**report, "status": "already-patched", "sha256_after": current_hash, "backup": str(backup)}
    patched = patched_bytes(original, recipe)
    report["sha256_after"] = target_hash
    report["changed_byte_count"] = sum(a != b for a, b in zip(original, patched))
    change_kind = "updated_factory_versions" if recipe == "client023-v2" else "redirected_calls"
    report[change_kind] = [name for _, _, name in patches]
    if install:
        if backup.is_symlink():
            raise ValueError("Refusing to use a symbolic-link backup")
        if backup.exists():
            if sha256(backup.read_bytes()) != source_hash:
                raise ValueError("Existing backup has a different hash; refusing to overwrite it")
        else:
            write_new(backup, original, mode)
        replace_atomically(path, patched, mode, source_hash)
        report.update(status="installed", backup=str(backup))
    else:
        output = output or path.with_name(path.stem + "." + recipe + ".dll")
        write_new(output, patched, mode)
        report.update(status="generated", output=str(output))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assembly", nargs="?", type=Path, default=DEFAULT_ASSEMBLY)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--recipe", choices=RECIPES, default="generic-v1")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--install", action="store_true")
    actions.add_argument("--restore", action="store_true")
    args = parser.parse_args(argv)
    if args.output and (args.install or args.restore):
        parser.error("--output cannot be combined with --install or --restore")
    try:
        report = run(args.assembly, args.output, args.install, args.restore, args.recipe)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, indent=2))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
