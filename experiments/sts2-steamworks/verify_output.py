#!/usr/bin/env python3
"""Read-only converted-package verification; never load binaries or call Steam."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import stat
import struct
import subprocess
import sys


MANIFEST = "conversion-manifest.json"


def inspect(path):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Symbolic link refused")
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("Not a regular file")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        header = stream.read(64)
        digest.update(header)
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    after = path.stat()
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(before, k) != getattr(after, k) for k in fields):
        raise ValueError("File changed during verification")
    result = {"sha256": digest.hexdigest(), "size_bytes": after.st_size}
    if header[:4] == b"\x7fELF":
        if len(header) < 20 or header[4:6] != b"\x02\x01":
            raise ValueError("Not ELF64 little-endian")
        result["elf_machine"] = struct.unpack_from("<H", header, 18)[0]
    return result


def verify(root, *, check_modes=False):
    root = Path(os.path.abspath(root))
    errors, verified = [], 0
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError("Symbolic link refused")
    manifest_path = root / MANIFEST
    inspect(manifest_path)
    if manifest_path.stat().st_size > 1024 * 1024:
        raise ValueError("Manifest too large")
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    if (not isinstance(manifest, dict) or manifest.get("manifest_version") != 1
            or not isinstance(manifest.get("files"), list) or len(manifest["files"]) > 10000):
        raise ValueError("Unsupported manifest")
    names = set()
    for item in manifest["files"]:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError("Malformed manifest file record")
        name = item["path"]
        path = PurePosixPath(name)
        if (not name or path.is_absolute() or ".." in path.parts or "\\" in name
                or ":" in name or path.as_posix() != name or name in names or name == MANIFEST):
            raise ValueError("Unsafe or duplicate manifest path")
        names.add(name)
        try:
            actual = inspect(root / Path(*path.parts))
            for field in ("sha256", "size_bytes", "elf_machine"):
                if field in item and actual.get(field) != item[field]:
                    raise ValueError(field + " mismatch")
            if "elf_machine" in actual and actual["elf_machine"] != 183:
                raise ValueError("Non-AArch64 native binary")
            if check_modes and item.get("executable") and not os.access(root / name, os.X_OK):
                raise ValueError("Executable permission missing")
            verified += 1
        except (OSError, ValueError) as error:
            errors.append({"path": name, "error": str(error)})
    # Extra runtime files are excluded from the converter; flag additions too.
    for folder, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(folder) / name
            if path.is_symlink():
                errors.append({"path": path.relative_to(root).as_posix(), "error": "Unexpected symlink"})
        for name in files:
            path = (Path(folder) / name).relative_to(root).as_posix()
            if path not in names | {MANIFEST} and not path.startswith("diagnostics/"):
                errors.append({"path": path, "error": "Unexpected file"})
    return {"diagnostic_version": 1, "errors": errors, "files_verified": verified,
            "files_expected": len(names), "manifest_sha256": hashlib.sha256(raw).hexdigest(),
            "host_architecture": platform.machine(), "release": manifest.get("release"),
            "scope": "Static output integrity only; manifest is not a signature. No execution or Steam calls."}


def diagnostics(root):
    report = verify(root, check_modes=os.name != "nt")
    root = Path(root)
    report["native_dependencies"] = []
    manifest = json.loads((root / MANIFEST).read_bytes())
    for item in manifest["files"]:
        if "elf_machine" not in item:
            continue
        row = {"path": item["path"]}
        try:
            result = subprocess.run(["readelf", "-d", str(root / item["path"])],
                                    capture_output=True, text=True, timeout=10)
            row["exit_code"] = result.returncode
            row["dynamic_entries"] = [line.strip() for line in result.stdout.splitlines()
                                      if any(label in line for label in ("NEEDED", "RPATH", "RUNPATH", "SONAME"))][:80]
        except FileNotFoundError:
            row["unavailable"] = "readelf not installed"
        except (OSError, subprocess.TimeoutExpired) as error:
            row["unavailable"] = type(error).__name__
        report["native_dependencies"].append(row)
    report["steam_environment"] = {name: os.environ.get(name) for name in ("SteamAppId", "SteamGameId")}
    report["display_environment"] = {name: bool(os.environ.get(name)) for name in ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR")}
    report["steamclient_arm64_present"] = (Path.home() / ".local/share/Steam/linuxarm64/steamclient.so").is_file()
    report["scope"] += " Dependency inspection uses readelf, never ldd. No environment dump or save-file access."
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--check-modes", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = diagnostics(args.root) if args.diagnostics else verify(args.root, check_modes=args.check_modes)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {"errors": [str(error)], "scope": "Static verification refused; no binaries executed."}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
