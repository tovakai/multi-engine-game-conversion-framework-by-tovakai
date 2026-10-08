# Read-only clean source inventory

Run this on the computer holding your clean, legitimate game installation,
not against the patched Frame prototype. Close the game. Choose one block for
your terminal and replace only `REPLACE_WITH_CLEAN_STS2_DIRECTORY` with the
installation directory as seen from that terminal. Do not modify the source.
No cloud files or separate scripts are needed; Python 3.9 or newer is required.

Bash includes Linux, macOS and WSL. In WSL use the mounted path, such as
`/mnt/c/...`, not a Windows drive path. For native Windows PowerShell use the
second block and your normal Windows directory path (without a trailing
backslash in the raw Python string). The Python command there is `python`;
use `py -3 -` instead if that is your installed Python launcher.

The script hashes all regular package files, including large packs and DLLs;
it can take several minutes and prints JSON only at the end. Paste/upload the
JSON output, including errors. It does not execute anything from the game,
load libraries, call Steam, write files or dump launcher/environment contents.
Reads may update access times under the local filesystem policy.
It excludes `.git`, `saves`, `logs` and `userdata` directories explicitly.
Symlinks are recorded but not followed; external targets are redacted.
Review filenames/runtime identifiers before sharing publicly.

`prototype_patch_checks` are expected to be false on a clean installation:
they refer to the known patched prototype, not to source recognition.
We compare individual file hashes/layout with the prototype, not just the
reported release version. This inventory does not itself enable a recipe or
prove that every original managed DLL is portable IL.

This is collector version 2. It avoids comparing Windows handle-stat values
with path-stat values, which can differ even for unchanged files. Both APIs
are still checked before/after reading, along with the actual byte count.
If you save output, place it outside the installation directory. PowerShell
may save JSON as UTF-16; that encoding is accepted for the returned report.

## Bash

```bash
python3 - <<'PY'
#!/usr/bin/env python3
"""Static package inventory; never execute binaries, load libraries, or write files."""

import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys


ROOT = Path(r"REPLACE_WITH_CLEAN_STS2_DIRECTORY")
STAT_FIELDS = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
COMPARE_HANDLE_PATH_STATS = os.name != "nt"
EXCLUDED = {".git", "saves", "logs", "userdata"}
EXPECTED = {
    "data_sts2_linuxbsd_arm64/Steamworks.NET.dll": "e214b36dda06df40901cd5b0fb043045b7aa626475c0154f7ca421bb725fde14",
    "data_sts2_linuxbsd_arm64/sts2.dll": "c27aedddd408500ab05ac3c045f41c3f224e3db19c4a6904b5581cc4f588351c",
    "data_sts2_linuxbsd_arm64/libsteam_api64.so": "9d354c631f01f7318bc00e8fa29842b83678f4293b52d0d5c11806edd76a7f4b",
}


def identity(value):
    return tuple(getattr(value, name) for name in STAT_FIELDS)


def inspect_file(path):
    path_before = path.lstat()
    if not stat.S_ISREG(path_before.st_mode):
        raise ValueError("not a regular file")
    flags = (os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
             | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(os.open(path, flags), "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("not a regular file")
        digest, header, config, bytes_read = hashlib.sha256(), b"", bytearray(), 0
        configuration = path.name.lower().endswith(".runtimeconfig.json") and before.st_size <= 65536
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
            bytes_read += len(block)
            header = (header + block[:64])[:64]
            if configuration:
                config.extend(block)
        after = os.fstat(stream.fileno())
    path_after = path.lstat()
    # Windows handle/path stat APIs can report different IDs or time precision.
    # Check each API against itself; retain the cross-API identity check on POSIX.
    if (identity(before) != identity(after) or identity(path_before) != identity(path_after)
            or bytes_read != before.st_size or bytes_read != path_before.st_size
            or (COMPARE_HANDLE_PATH_STATS and identity(before) != identity(path_before))):
        raise ValueError("file changed; close the game and rerun")
    item = {"kind": "file", "size_bytes": after.st_size,
            "mode": oct(stat.S_IMODE(after.st_mode)), "sha256": digest.hexdigest()}
    differing_fields = [name for name in STAT_FIELDS
                        if getattr(before, name) != getattr(path_before, name)]
    if differing_fields:
        item["stat_api_difference_fields"] = differing_fields
    if header.startswith(b"\x7fELF"):
        if len(header) < 20 or header[4] not in (1, 2) or header[5] not in (1, 2):
            raise ValueError("invalid ELF identification")
        order = "<" if header[5] == 1 else ">"
        item["elf"] = {"class_bits": 32 if header[4] == 1 else 64,
                       "machine": struct.unpack_from(order + "H", header, 18)[0]}
    if configuration:
        options = json.loads(config).get("runtimeOptions", {})
        if not isinstance(options, dict):
            raise ValueError("invalid runtimeOptions")
        frameworks = options.get("frameworks", [])
        if "framework" in options:
            frameworks = [*frameworks, options["framework"]]
        # Only runtime identifiers, not arbitrary configuration/environment values.
        item["dotnet"] = {"tfm": options.get("tfm"), "frameworks": [
            {key: framework.get(key) for key in ("name", "version")}
            for framework in frameworks]}
    return item


def collect(root):
    report = {"inventory_version": 2, "files": [], "errors": [], "excluded": [],
              "collector_platform": sys.platform,
              "collector_python_version": ".".join(map(str, sys.version_info[:3])),
              "stat_validation": "Descriptor and path before/after checks, byte-count checks; cross-API identity additionally checked on POSIX.",
              "scope": "Static hashes and ELF headers only; no execution, Steam calls, IL conclusions, or writes. Symlinks are not followed; configuration contents and personal data are not dumped.",
              "unresolved": ["Clean-source comparison", "Engine/runtime build provenance",
                             "Native dependency provenance and licensing", "Launcher contents and environment",
                             "External runtime or symlink dependencies", "Clean-conversion hardware acceptance"]}
    if root.is_symlink() or not root.is_dir():
        report["errors"].append({"path": ".", "error": "expected an existing non-symlink directory"})
        return report
    root = root.resolve()
    def walk_error(error):
        report["errors"].append({"path": ".", "error": "directory traversal failed: errno=" + str(error.errno)})
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        parent = Path(directory)
        kept = []
        for name in sorted(dirs):
            if name.lower() in EXCLUDED:
                report["excluded"].append((parent / name).relative_to(root).as_posix())
            elif (parent / name).is_symlink():
                files.append(name)
            else:
                kept.append(name)
        dirs[:] = kept
        for name in sorted(files):
            path = parent / name
            relative = path.relative_to(root).as_posix()
            try:
                if path.is_symlink():
                    target = Path(os.path.normpath(os.path.join(parent, os.readlink(path))))
                    item = {"kind": "symlink", "target": target.relative_to(root).as_posix()
                            if target.is_relative_to(root) else "<external; redacted>"}
                elif not stat.S_ISREG(path.lstat().st_mode):
                    raise ValueError("not a regular file or symlink")
                else:
                    item = inspect_file(path)
                report["files"].append({"path": relative, **item})
            except (OSError, ValueError, TypeError, AttributeError) as error:
                message = "filesystem read failed: errno=" + str(error.errno) if isinstance(error, OSError) else str(error)
                report["errors"].append({"path": relative, "error": message})
    report["files"].sort(key=lambda item: item["path"])
    report["excluded"].sort()
    actual = {item["path"]: item.get("sha256") for item in report["files"]}
    report["prototype_patch_checks"] = {path: actual.get(path) == expected for path, expected in EXPECTED.items()}
    report["inventory_complete"] = not report["errors"]
    report["files_hashed"] = sum(item["kind"] == "file" for item in report["files"])
    report["tree_sha256"] = hashlib.sha256(json.dumps(report["files"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return report


def main():
    report = collect(Path(sys.argv[1]) if len(sys.argv) == 2 else ROOT)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
PY
```

## Windows PowerShell

```powershell
@'
#!/usr/bin/env python3
"""Static package inventory; never execute binaries, load libraries, or write files."""

import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys


ROOT = Path(r"REPLACE_WITH_CLEAN_STS2_DIRECTORY")
STAT_FIELDS = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
COMPARE_HANDLE_PATH_STATS = os.name != "nt"
EXCLUDED = {".git", "saves", "logs", "userdata"}
EXPECTED = {
    "data_sts2_linuxbsd_arm64/Steamworks.NET.dll": "e214b36dda06df40901cd5b0fb043045b7aa626475c0154f7ca421bb725fde14",
    "data_sts2_linuxbsd_arm64/sts2.dll": "c27aedddd408500ab05ac3c045f41c3f224e3db19c4a6904b5581cc4f588351c",
    "data_sts2_linuxbsd_arm64/libsteam_api64.so": "9d354c631f01f7318bc00e8fa29842b83678f4293b52d0d5c11806edd76a7f4b",
}


def identity(value):
    return tuple(getattr(value, name) for name in STAT_FIELDS)


def inspect_file(path):
    path_before = path.lstat()
    if not stat.S_ISREG(path_before.st_mode):
        raise ValueError("not a regular file")
    flags = (os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
             | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(os.open(path, flags), "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("not a regular file")
        digest, header, config, bytes_read = hashlib.sha256(), b"", bytearray(), 0
        configuration = path.name.lower().endswith(".runtimeconfig.json") and before.st_size <= 65536
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
            bytes_read += len(block)
            header = (header + block[:64])[:64]
            if configuration:
                config.extend(block)
        after = os.fstat(stream.fileno())
    path_after = path.lstat()
    # Windows handle/path stat APIs can report different IDs or time precision.
    # Check each API against itself; retain the cross-API identity check on POSIX.
    if (identity(before) != identity(after) or identity(path_before) != identity(path_after)
            or bytes_read != before.st_size or bytes_read != path_before.st_size
            or (COMPARE_HANDLE_PATH_STATS and identity(before) != identity(path_before))):
        raise ValueError("file changed; close the game and rerun")
    item = {"kind": "file", "size_bytes": after.st_size,
            "mode": oct(stat.S_IMODE(after.st_mode)), "sha256": digest.hexdigest()}
    differing_fields = [name for name in STAT_FIELDS
                        if getattr(before, name) != getattr(path_before, name)]
    if differing_fields:
        item["stat_api_difference_fields"] = differing_fields
    if header.startswith(b"\x7fELF"):
        if len(header) < 20 or header[4] not in (1, 2) or header[5] not in (1, 2):
            raise ValueError("invalid ELF identification")
        order = "<" if header[5] == 1 else ">"
        item["elf"] = {"class_bits": 32 if header[4] == 1 else 64,
                       "machine": struct.unpack_from(order + "H", header, 18)[0]}
    if configuration:
        options = json.loads(config).get("runtimeOptions", {})
        if not isinstance(options, dict):
            raise ValueError("invalid runtimeOptions")
        frameworks = options.get("frameworks", [])
        if "framework" in options:
            frameworks = [*frameworks, options["framework"]]
        # Only runtime identifiers, not arbitrary configuration/environment values.
        item["dotnet"] = {"tfm": options.get("tfm"), "frameworks": [
            {key: framework.get(key) for key in ("name", "version")}
            for framework in frameworks]}
    return item


def collect(root):
    report = {"inventory_version": 2, "files": [], "errors": [], "excluded": [],
              "collector_platform": sys.platform,
              "collector_python_version": ".".join(map(str, sys.version_info[:3])),
              "stat_validation": "Descriptor and path before/after checks, byte-count checks; cross-API identity additionally checked on POSIX.",
              "scope": "Static hashes and ELF headers only; no execution, Steam calls, IL conclusions, or writes. Symlinks are not followed; configuration contents and personal data are not dumped.",
              "unresolved": ["Clean-source comparison", "Engine/runtime build provenance",
                             "Native dependency provenance and licensing", "Launcher contents and environment",
                             "External runtime or symlink dependencies", "Clean-conversion hardware acceptance"]}
    if root.is_symlink() or not root.is_dir():
        report["errors"].append({"path": ".", "error": "expected an existing non-symlink directory"})
        return report
    root = root.resolve()
    def walk_error(error):
        report["errors"].append({"path": ".", "error": "directory traversal failed: errno=" + str(error.errno)})
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        parent = Path(directory)
        kept = []
        for name in sorted(dirs):
            if name.lower() in EXCLUDED:
                report["excluded"].append((parent / name).relative_to(root).as_posix())
            elif (parent / name).is_symlink():
                files.append(name)
            else:
                kept.append(name)
        dirs[:] = kept
        for name in sorted(files):
            path = parent / name
            relative = path.relative_to(root).as_posix()
            try:
                if path.is_symlink():
                    target = Path(os.path.normpath(os.path.join(parent, os.readlink(path))))
                    item = {"kind": "symlink", "target": target.relative_to(root).as_posix()
                            if target.is_relative_to(root) else "<external; redacted>"}
                elif not stat.S_ISREG(path.lstat().st_mode):
                    raise ValueError("not a regular file or symlink")
                else:
                    item = inspect_file(path)
                report["files"].append({"path": relative, **item})
            except (OSError, ValueError, TypeError, AttributeError) as error:
                message = "filesystem read failed: errno=" + str(error.errno) if isinstance(error, OSError) else str(error)
                report["errors"].append({"path": relative, "error": message})
    report["files"].sort(key=lambda item: item["path"])
    report["excluded"].sort()
    actual = {item["path"]: item.get("sha256") for item in report["files"]}
    report["prototype_patch_checks"] = {path: actual.get(path) == expected for path, expected in EXPECTED.items()}
    report["inventory_complete"] = not report["errors"]
    report["files_hashed"] = sum(item["kind"] == "file" for item in report["files"])
    report["tree_sha256"] = hashlib.sha256(json.dumps(report["files"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return report


def main():
    report = collect(Path(sys.argv[1]) if len(sys.argv) == 2 else ROOT)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
'@ | python -
```

The Bash block is covered by a synthetic local execution test. The Python code
is shared with the tested inventory collector; the native Windows PowerShell
wrapper has not been executed in this Linux development environment.
