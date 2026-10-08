# Read-only packed extension diagnostic

Close STS2, then run this entire Bash block in your existing Frame SSH terminal.
Only Python 3 is required. No cloud files, installation or separate remote
scripts are needed. It prints JSON; paste the output back, including errors.

It reads the three PCK directories and only small `.gdextension` files and the
extension list. It never loads an extension, calls Steam, launches Godot or
writes files. Reads may update access times according to mount policy.
Whole-PCK SHA-256 hashes are not recomputed: sizes must match the supplied
inventory, and file stability is checked. Comparisons use declared resource
size/MD5/flags, not all resource bytes. Extracted configuration SHA-256 hashes
are computed from actual bytes; their table MD5 values are checked separately.

This is an isolated development diagnostic, not a converter patch. It follows
Godot 4.5.1's [PCK reader](https://github.com/godotengine/godot/blob/f62fdbde15035c5576dad93e586201f4d41ef0cb/core/io/file_access_pack.cpp)
and [format flags](https://github.com/godotengine/godot/blob/f62fdbde15035c5576dad93e586201f4d41ef0cb/core/io/file_access_pack.h).
It refuses unsupported encryption/sparse packs, ambiguous paths, excessive
metadata/configuration sizes, out-of-bounds resources and changing files.
No inference about which manifest the running engine loaded is made from
resource presence alone. No proprietary game assets are extracted to disk.

```bash
python3 - <<'PY'
#!/usr/bin/env python3
"""Read unencrypted standalone PCK v2/v3 tables and small extension configs."""

import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys


ROOT = Path("/run/media/steamos/SD512/sts2-arm64-proto")
PACKS = {
    "SlayTheSpire2.pck": 1647627992,
    "SlayTheSpire2.pck.before-fmod-patch": 1647627768,
    "SlayTheSpire2.pck.before-sentry-patch": 1647470256,
}


def stamp(value):
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def inspect_pack(path, expected_size=None):
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("symbolic link refused")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("expected a regular PCK file")
        if expected_size is not None and before.st_size != expected_size:
            raise ValueError("size differs from the received inventory; rerun inventory")

        def take(size):
            data = stream.read(size)
            if len(data) != size:
                raise ValueError("truncated PCK data")
            return data

        def unpack(layout):
            return struct.unpack(layout, take(struct.calcsize(layout)))

        # Layout: Godot f62fdbde15035c5576dad93e586201f4d41ef0cb,
        # core/io/file_access_pack.cpp and .h. No engine code is executed.
        magic, version, major, minor, patch = unpack("<5I")
        if magic != 0x43504447 or version not in (2, 3):
            raise ValueError("expected standalone Godot PCK format 2 or 3")
        pack_flags, file_base = unpack("<IQ")
        if pack_flags & ~2:
            raise ValueError("encrypted, sparse or unknown PCK flags are unsupported")
        directory = unpack("<Q")[0] if version == 3 else 96
        minimum = 40 if version == 3 else 96
        if not minimum <= directory <= before.st_size - 4 or file_base > before.st_size:
            raise ValueError("invalid PCK directory or file base")
        stream.seek(directory)
        count = unpack("<I")[0]
        if count > 200000:
            raise ValueError("PCK entry limit exceeded")
        entries, configs = {}, []
        for _ in range(count):
            if stream.tell() - directory > 64 * 1024 * 1024:
                raise ValueError("PCK directory exceeds inspection limit")
            length = unpack("<I")[0]
            if not 0 < length <= 4096:
                raise ValueError("invalid or excessive PCK path length")
            name = take(length).rstrip(b"\0").decode("utf-8").removeprefix("res://")
            offset, size, md5, entry_flags = unpack("<QQ16sI")
            if not name or "\0" in name or name in entries:
                raise ValueError("empty, ambiguous or duplicate resource path")
            if entry_flags & ~2:
                raise ValueError("encrypted or unknown resource flags are unsupported")
            if not entry_flags and file_base + offset + size > before.st_size:
                raise ValueError("resource range exceeds PCK size")
            entries[name] = {"size_bytes": size, "table_md5": md5.hex(), "flags": entry_flags}
            if entry_flags or not (name.endswith(".gdextension") or name == ".godot/extension_list.cfg"):
                continue
            if size > 65536 or len(configs) >= 64:
                raise ValueError("extension configuration inspection limit exceeded")
            position = stream.tell()
            stream.seek(file_base + offset)
            raw = take(size)
            configs.append({"path": name, "sha256": hashlib.sha256(raw).hexdigest(),
                            "table_md5_matches": hashlib.md5(raw, usedforsecurity=False).digest() == md5,
                            "text": raw.decode("utf-8-sig")})
            stream.seek(position)
        after = os.fstat(stream.fileno())
    if stamp(before) != stamp(after) or stamp(after) != stamp(path.lstat()):
        raise ValueError("PCK changed during inspection; close STS2 and rerun")
    return {"path": path.name, "size_bytes": before.st_size, "format": version,
            "godot_version": [major, minor, patch], "pack_flags": pack_flags,
            "file_base": file_base, "directory_offset": directory, "entry_count": count,
            "extension_configs": configs}, entries


def collect(root, packs=None):
    report = {"diagnostic_version": 1, "packs": [], "comparisons": [], "errors": [],
              "scope": "Read-only PCK directories and small extension configs; no writes, engine execution or Steam calls. Whole-pack hashes are NOT rechecked. Comparisons use declared size/MD5/flags, not all resource bytes."}
    tables = {}
    for name, size in (PACKS if packs is None else packs).items():
        try:
            item, entries = inspect_pack(root / name, size)
            report["packs"].append(item)
            tables[name] = entries
        except (OSError, ValueError) as error:
            message = "read failed: errno=" + str(error.errno) if isinstance(error, OSError) else str(error)
            report["errors"].append({"path": name, "error": message})
    current = tables.get("SlayTheSpire2.pck")
    if current is not None:
        for name, previous in tables.items():
            if name == "SlayTheSpire2.pck":
                continue
            changed = sorted(path for path in current.keys() | previous.keys()
                             if current.get(path) != previous.get(path))
            report["comparisons"].append({"reference": name, "compared_to": "SlayTheSpire2.pck",
                                          "changed_metadata_count": len(changed),
                                          "changed_paths": changed[:100], "list_truncated": len(changed) > 100})
    return report


if __name__ == "__main__":
    result = collect(ROOT)
    print(json.dumps(result, indent=2, sort_keys=True))
    sys.exit(2 if result["errors"] else 0)
PY
```
