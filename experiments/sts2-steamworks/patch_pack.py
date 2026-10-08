"""Out-of-place append patch for the observed standalone Godot 4.5.1 PCK v3.

The original pack is copied verbatim except its eight-byte directory pointer.
New manifests and a copied/updated directory are appended, leaving all existing
asset payloads and their offsets intact. No game or native library is executed.
"""

import hashlib
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import stat
import struct
import tempfile
import sys
import shutil

from adapt_packed_manifests import RECIPES, UNCHANGED, adapt_bundle
from inventory_package import COMPARE_HANDLE_PATH_STATS, identity


SOURCE_SHA256 = "c0c4b951fa6b342d379c4221e2d96eba8a8bbfce5cd7cd2049254a74f6575d41"
SOURCE_SIZE = 1647470256
BLOCK_SIZE = 1024 * 1024


def _safe(path):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Symbolic link refused")


def _take(stream, size):
    raw = stream.read(size)
    if len(raw) != size:
        raise ValueError("Truncated PCK")
    return raw


def _table(stream, size):
    stream.seek(0)
    magic, version, major, minor, patch, flags, base, directory = struct.unpack("<6IQQ", _take(stream, 40))
    if (magic, version, major, minor, patch, flags) != (0x43504447, 3, 4, 5, 1, 2):
        raise ValueError("Only the unencrypted standalone Godot 4.5.1 PCK v3 layout is supported")
    if not 104 <= directory <= size - 4 or not 104 <= base <= size:
        raise ValueError("Invalid directory or file base")
    stream.seek(directory)
    raw = bytearray(_take(stream, 4))
    count = struct.unpack("<I", raw)[0]
    if count > 200000:
        raise ValueError("PCK entry limit exceeded")
    entries = {}
    for _ in range(count):
        length_raw = _take(stream, 4)
        length = struct.unpack("<I", length_raw)[0]
        if not 0 < length <= 4096 or len(raw) + length + 40 > 64 * 1024 * 1024:
            raise ValueError("PCK directory limit exceeded")
        encoded = _take(stream, length)
        name = encoded.rstrip(b"\0").decode("utf-8").removeprefix("res://")
        if (not name or "\0" in name or "\\" in name or ":" in name
                or name.startswith("/") or PurePosixPath(name).as_posix() != name
                or ".." in PurePosixPath(name).parts or name in entries):
            raise ValueError("Ambiguous, unsafe or duplicate resource path")
        raw.extend(length_raw + encoded)
        metadata_at = len(raw)
        fields = _take(stream, 36)
        offset, length, md5, entry_flags = struct.unpack("<QQ16sI", fields)
        if entry_flags not in (0, 2):
            raise ValueError("Encrypted or unknown resource flags")
        absolute = base + offset
        if not entry_flags and (absolute < 104 or absolute + length > size):
            raise ValueError("Resource outside source payload")
        raw.extend(fields)
        entries[name] = {"offset": absolute, "size": length, "md5": md5,
                         "flags": entry_flags, "metadata_at": metadata_at}
    end = directory + len(raw)
    for item in entries.values():
        if not item["flags"] and item["size"] and item["offset"] < end and item["offset"] + item["size"] > directory:
            raise ValueError("Resource overlaps source directory")
    return base, directory, raw, entries


def rewrite_pack(source, destination, *, expected_sha256, expected_size, transform=adapt_bundle, atomic_publication=True):
    """Publish a new pack only after source identity/hash and all edits validate.

    `transform` operates on the four verified extension resources in memory.
    The destination must not exist; source and existing outputs are never edited.
    Publication uses a same-filesystem hard link, not an overwriting rename.
    """
    source, destination = Path(source).absolute(), Path(destination).absolute()
    _safe(source)
    _safe(destination)
    if destination.exists() or not destination.parent.is_dir():
        raise ValueError("Destination exists or its parent is missing")
    if (not isinstance(expected_sha256, str) or len(expected_sha256) != 64
            or any(c not in "0123456789abcdef" for c in expected_sha256)
            or type(expected_size) is not int or expected_size < 104):
        raise ValueError("Exact source size and SHA-256 are required")
    path_before = source.lstat()
    if not stat.S_ISREG(path_before.st_mode) or path_before.st_size != expected_size:
        raise ValueError("Source is not a regular file of the expected size")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
    temporary = None
    try:
        with os.fdopen(os.open(source, flags), "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size != expected_size:
                raise ValueError("Source changed before opening")
            base, old_directory, table, entries = _table(stream, before.st_size)
            required = RECIPES.keys() | UNCHANGED.keys()
            if required - entries.keys():
                raise ValueError("Required extension resources missing")
            resources = {}
            for name in sorted(required):
                entry = entries[name]
                if entry["flags"] or entry["size"] > 65536:
                    raise ValueError("Unsupported extension resource")
                stream.seek(entry["offset"])
                raw = _take(stream, entry["size"])
                if hashlib.md5(raw, usedforsecurity=False).digest() != entry["md5"]:
                    raise ValueError("Extension resource MD5 mismatch")
                resources[name] = raw
            adapted, adaptation = transform(dict(resources))
            if adapted.keys() != resources.keys() or any(not isinstance(raw, bytes) or len(raw) > 65536 for raw in adapted.values()):
                raise ValueError("Unexpected transformed resource set")
            if any(adapted[name] != resources[name] for name in UNCHANGED):
                raise ValueError("Preserved extension configuration changed")
            changes = sorted(name for name in resources if adapted[name] != resources[name])
            cursor, additions = before.st_size, []
            for name in changes:
                padding = -cursor % 16
                cursor += padding
                raw = adapted[name]
                struct.pack_into("<QQ16s", table, entries[name]["metadata_at"], cursor - base, len(raw), hashlib.md5(raw, usedforsecurity=False).digest())
                additions.extend((b"\0" * padding, raw))
                cursor += len(raw)
            new_directory = old_directory
            if changes:
                padding = -cursor % 16
                additions.extend((b"\0" * padding, bytes(table)))
                new_directory = cursor + padding
            fd, name = tempfile.mkstemp(prefix="." + destination.name + ".", suffix=".tmp", dir=destination.parent)
            temporary = Path(name)
            source_hash, output_hash = hashlib.sha256(), hashlib.sha256()
            input_size, output_size = 0, 0
            with os.fdopen(fd, "wb") as output:
                def emit(raw):
                    nonlocal output_size
                    if output.write(raw) != len(raw):
                        raise OSError("Short pack write")
                    output_hash.update(raw)
                    output_size += len(raw)
                stream.seek(0)
                header = _take(stream, 40)
                source_hash.update(header)
                input_size += len(header)
                emit(header[:32] + struct.pack("<Q", new_directory))
                while True:
                    block = stream.read(BLOCK_SIZE)
                    if not block:
                        break
                    source_hash.update(block)
                    input_size += len(block)
                    emit(block)
                after = os.fstat(stream.fileno())
                path_after = source.lstat()
                if (identity(before) != identity(after) or identity(path_before) != identity(path_after)
                        or input_size != expected_size or source_hash.hexdigest() != expected_sha256
                        or (COMPARE_HANDLE_PATH_STATS and identity(before) != identity(path_before))):
                    raise ValueError("Source hash or file identity changed; output refused")
                for raw in additions:
                    emit(raw)
                output.flush()
                os.fsync(output.fileno())
            os.chmod(temporary, 0o644)
            # Private converter staging also supports filesystems without hard links.
            if atomic_publication:
                os.link(temporary, destination)
            else:
                try:
                    with destination.open("xb") as published, temporary.open("rb") as candidate:
                        shutil.copyfileobj(candidate, published, BLOCK_SIZE)
                        published.flush()
                        os.fsync(published.fileno())
                except FileExistsError:
                    raise
                except BaseException:
                    destination.unlink(missing_ok=True)
                    raise
                os.chmod(destination, 0o644)
            return {"source_sha256": source_hash.hexdigest(), "output_sha256": output_hash.hexdigest(),
                    "output_size_bytes": output_size, "entry_count": len(entries), "changed_paths": changes,
                    "source_directory": old_directory, "output_directory": new_directory,
                    "original_prefix_changes": [{"offset": 32, "size_bytes": 8}] if changes else [],
                    "adaptation": adaptation,
                    "scope": "Out-of-place appended manifests/directory; original payload bytes/offsets retained. Not a clean conversion or hardware validation."}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def patch_sts2_pack(source, destination):
    """Accept only the inventory-linked original experiment pack, not newer builds."""
    return rewrite_pack(source, destination, expected_sha256=SOURCE_SHA256, expected_size=SOURCE_SIZE)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create a new PCK from the exact observed STS2 source pack; never modify the input.")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    try:
        result = patch_sts2_pack(args.source.expanduser(), args.destination.expanduser())
    except (OSError, ValueError) as error:
        print(json.dumps({"errors": [str(error)], "scope": "No complete game conversion or device test."}, indent=2))
        return 2
    print(json.dumps({"errors": [], **result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
